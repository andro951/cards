"""Folder/ZIP image comparison. Identical bytes skip pixel decoding."""
from __future__ import annotations

import os
import shutil
import stat
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps

OUTPUT_NAMES = ("diff", "new", "removed")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".ico", ".avif"}
CHUNK_SIZE = 1024 * 1024


class Cancelled(Exception):
    pass


class RecoveryError(OSError):
    """A result workspace contains backups that must not be cleaned up."""


@dataclass(frozen=True)
class Candidate:
    path: Path
    modified: float
    archive: Path | None = None

    @property
    def label(self):
        date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.modified))
        return f"{self.path.name}  |  {date}" + ("  [ZIP]" if self.archive and not self.path.exists() else "")


@dataclass(frozen=True)
class ImageFile:
    path: Path
    relative: Path
    size: int


@dataclass(frozen=True)
class Result:
    changed: int
    added: int
    removed: int
    unchanged: int
    elapsed: float
    older: Path
    newer: Path


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("Comparison cancelled.")


def ignored(name):
    return name.casefold() in OUTPUT_NAMES or name.casefold().startswith(".image-compare-") or name == "__MACOSX"


def image_paths(folder, cancel=None):
    with os.scandir(folder) as entries:
        for entry in entries:
            check_cancel(cancel)
            if entry.is_dir(follow_symlinks=False) and not ignored(entry.name):
                yield from image_paths(Path(entry.path), cancel)
            elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in IMAGE_EXTENSIONS:
                yield Path(entry.path)


def archive_has_images(path):
    with zipfile.ZipFile(path) as archive:
        return any(
            not item.is_dir() and PurePosixPath(item.filename).suffix.lower() in IMAGE_EXTENSIONS
            and not any(ignored(part) for part in PurePosixPath(item.filename.replace("\\", "/")).parts[:-1])
            for item in archive.infolist()
        )


def discover(folder, cancel=None):
    folder = Path(folder).resolve()
    children = [p for p in folder.iterdir() if not ignored(p.name) and not p.is_symlink()]
    directories = {p.name.casefold(): p for p in children if p.is_dir()}
    paired = set()
    candidates = []
    for path in children:
        check_cancel(cancel)
        if path.is_file() and path.suffix.lower() == ".zip" and not ignored(path.stem):
            target = directories.get(path.stem.casefold(), folder / path.stem)
            if target.exists():
                # An extracted folder is authoritative; never extract over it.
                paired.add(target.name.casefold())
                has_images = next(image_paths(target, cancel), None) is not None
            else:
                has_images = archive_has_images(path)
            if has_images:
                candidates.append(Candidate(target, path.stat().st_mtime, path))
    for name, path in directories.items():
        check_cancel(cancel)
        if name not in paired and next(image_paths(path, cancel), None) is not None:
            candidates.append(Candidate(path, path.stat().st_mtime))
    return sorted(candidates, key=lambda item: (item.modified, item.path.name.casefold()))


def cleanup_temporary(path, parent):
    # Only this application's direct temporary children can be removed.
    if path.parent.resolve() != parent.resolve() or not path.name.startswith(".image-compare-") or path.is_symlink():
        raise ValueError("Invalid temporary workspace.")
    if path.exists():
        shutil.rmtree(path)


def extract_missing(candidate, cancel=None, progress=lambda *args: None):
    destination = candidate.path
    if destination.is_dir():
        return destination
    if destination.exists() or not candidate.archive:
        raise ValueError(f"Cannot open image set: {destination}")
    temporary = destination.parent / (".image-compare-extract-" + uuid.uuid4().hex)
    temporary.mkdir()
    try:
        with zipfile.ZipFile(candidate.archive) as archive:
            items = archive.infolist()
            for index, item in enumerate(items):
                check_cancel(cancel)
                parts = PurePosixPath(item.filename.replace("\\", "/"))
                if parts.is_absolute() or ".." in parts.parts or any(":" in part for part in parts.parts):
                    raise ValueError(f"Unsafe ZIP entry: {item.filename}")
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError(f"ZIP contains a symbolic link: {item.filename}")
                if any(ignored(part) for part in parts.parts):
                    continue
                target = temporary.joinpath(*parts.parts)
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, target.open("wb") as output:
                        while chunk := source.read(CHUNK_SIZE):
                            check_cancel(cancel)
                            output.write(chunk)
                progress(f"Extracting {candidate.archive.name}", index + 1, len(items))
        check_cancel(cancel)
        os.replace(temporary, destination)
        os.utime(destination, (candidate.modified, candidate.modified))
    finally:
        cleanup_temporary(temporary, destination.parent)
    return destination


def image_root(folder):
    # Ignore a ZIP's enclosing folder so a wrapped export matches a flat one.
    while True:
        children = [p for p in folder.iterdir() if not ignored(p.name) and not p.is_symlink()]
        if any(p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS for p in children):
            return folder
        directories = [p for p in children if p.is_dir()]
        if len(directories) != 1:
            return folder
        folder = directories[0]


def image_index(folder, cancel=None):
    root = image_root(folder)
    result = {}
    for path in image_paths(root, cancel):
        relative = path.relative_to(root)
        key = relative.as_posix().casefold()
        if key in result:
            raise ValueError(f"Ambiguous matching image path: {relative}")
        result[key] = ImageFile(path, relative, path.stat().st_size)
    return result


def same_image(older, newer, cancel=None):
    check_cancel(cancel)
    if older.size == newer.size:
        with older.path.open("rb") as a, newer.path.open("rb") as b:
            while True:
                check_cancel(cancel)
                chunk = a.read(CHUNK_SIZE)
                if chunk != b.read(CHUNK_SIZE):
                    break
                if not chunk:
                    return True
    # Sizes/bytes can differ solely because of metadata or compression.
    try:
        with Image.open(older.path) as a, Image.open(newer.path) as b:
            count = getattr(a, "n_frames", 1)
            if count != getattr(b, "n_frames", 1):
                return False
            for frame in range(count):
                check_cancel(cancel)
                a.seek(frame)
                b.seek(frame)
                left, right = ImageOps.exif_transpose(a), ImageOps.exif_transpose(b)
                if left.size != right.size:
                    return False
                # BulkProxyForge review exports contain two equal panels and a
                # one-pixel divider. Only the generated card on the right is
                # relevant; reference downloads/resizing can vary slightly.
                width, height = left.size
                if (width >= 3 and width % 2 == 1
                        and older.relative.stem.casefold().endswith("_review")
                        and newer.relative.stem.casefold().endswith("_review")):
                    bounds = (width // 2 + 1, 0, width, height)
                    left, right = left.crop(bounds), right.crop(bounds)
                if left.convert("RGBA").tobytes() != right.convert("RGBA").tobytes():
                    return False
            return True
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not compare {older.relative}: {error}") from error


def existing_outputs(folder):
    existing = []
    for name in OUTPUT_NAMES:
        path = folder / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError(f"The output path must be a normal folder: {path}")
        if path.exists() and next(path.iterdir(), None) is not None:
            existing.append(name)
    return existing


def _result_tree(root):
    """Inventory ordinary result files without following links or junctions."""
    files, directories = [], []
    if not root.exists():
        return files, directories
    pending = [root]
    while pending:
        directory = pending.pop()
        if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)():
            raise ValueError(f"Result folders must not contain links: {directory}")
        directories.append(directory)
        for child in directory.iterdir():
            if child.is_symlink() or getattr(child, "is_junction", lambda: False)():
                raise ValueError(f"Result folders must not contain links: {child}")
            if child.is_dir():
                pending.append(child)
            elif child.is_file():
                files.append(child)
            else:
                raise ValueError(f"Unsupported result entry: {child}")
    return files, directories


def _remove_empty_results(directories, warning):
    for directory in sorted(set(directories), key=lambda path: len(path.parts), reverse=True):
        try:
            if directory.is_dir() and next(directory.iterdir(), None) is None:
                directory.rmdir()
        except OSError as error:
            # Explorer may hold an empty folder open. The published files are
            # complete; retaining an empty directory must not fail the batch.
            warning(f"NOTE: Empty results folder could not be removed: {directory}: {error}")


def _publish_output_files(stage, folder, *, omit_empty, warning):
    """Keep open directories stable and journal file moves for rollback."""
    stage, folder = stage.resolve(), folder.resolve()
    if stage.parent != folder or not stage.name.startswith(".image-compare-"):
        raise ValueError("Invalid result publication workspace.")
    old_files, old_dirs, new_files, new_dirs = [], [], [], []
    for name in OUTPUT_NAMES:
        files, directories = _result_tree(folder / name)
        old_files.extend(files)
        old_dirs.extend(directories)
        source = stage / name
        if source.exists() and (not omit_empty or next(source.iterdir(), None) is not None):
            files, directories = _result_tree(source)
            new_files.extend(files)
            new_dirs.extend(folder / path.relative_to(stage) for path in directories)
    backup_root = stage / "previous-files"
    backup_root.mkdir()
    backups, installed, created = [], [], []
    try:
        # Move backups first. A locked file fails before any new file is installed.
        for source in old_files:
            backup = backup_root / source.relative_to(folder)
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, backup)
            backups.append((backup, source))
        for destination in sorted(new_dirs, key=lambda path: len(path.parts)):
            if not destination.exists():
                destination.mkdir()
                created.append(destination)
        for source in new_files:
            destination = folder / source.relative_to(stage)
            if destination.is_dir():
                destination.rmdir()  # A previous empty directory can become a file.
            os.replace(source, destination)
            installed.append((destination, source))
    except BaseException as original:
        try:
            for destination, source in reversed(installed):
                os.replace(destination, source)
            _remove_empty_results(created, warning)
            for directory in sorted(old_dirs, key=lambda path: len(path.parts)):
                directory.mkdir(parents=True, exist_ok=True)
            for backup, destination in reversed(backups):
                os.replace(backup, destination)
        except OSError as error:
            raise RecoveryError(f"Could not restore previous results. Backup files were kept in {stage}: {error}") from error
        if isinstance(original, PermissionError):
            raise PermissionError(f"Cannot replace a comparison result file: {original}. Close the image viewer using that file and retry; previous results were restored.") from original
        raise
    # All new files are installed. Stale files are in the private backup, and
    # stale empty folders can now be removed without renaming open deck folders.
    needed = set(new_dirs)
    _remove_empty_results([path for path in old_dirs if path not in needed], warning)


def publish_outputs(stage, folder, *, omit_empty=False, allow_in_place=False, warning=lambda text: None):
    """Replace the complete result, rolling back if publication fails."""
    existing_outputs(folder)
    saved_outputs = []
    published = []
    try:
        for name in OUTPUT_NAMES:
            destination = folder / name
            if destination.exists():
                backup = stage / ("previous-" + name)
                os.replace(destination, backup)
                saved_outputs.append((backup, destination))
            source = stage / name
            if source.exists() and (not omit_empty or next(source.iterdir(), None) is not None):
                os.replace(source, destination)
                published.append(destination)
    except OSError as original:
        try:
            for destination in reversed(published):
                os.replace(destination, stage / destination.name)
            for backup, destination in reversed(saved_outputs):
                os.replace(backup, destination)
        except OSError as error:
            raise RecoveryError(f"Could not restore previous results. Backup files were kept in {stage}: {error}") from error
        if allow_in_place and isinstance(original, PermissionError):
            warning("Result folder is in use; replacing its files without renaming the folder.")
            _publish_output_files(stage, folder, omit_empty=omit_empty, warning=warning)
            return
        raise


def compare_sets(folder, older, newer, *, replace_existing=False, cancel=None, progress=lambda *args: None,
                 output_folder=None, omit_empty=False):
    started = time.perf_counter()
    folder = Path(folder).resolve()
    if older.path.resolve() == newer.path.resolve():
        raise ValueError("Choose two different image sets.")
    if any(item.path.parent.resolve() != folder or ignored(item.path.name) for item in (older, newer)):
        raise ValueError("Both image sets must be inside the selected folder.")
    output = Path(output_folder).resolve() if output_folder is not None else folder
    if output_folder is not None:
        output.mkdir(parents=True, exist_ok=True)
    if existing_outputs(output) and not replace_existing:
        raise ValueError("Existing results need your confirmation before replacement.")
    old_root = extract_missing(older, cancel, progress)
    new_root = extract_missing(newer, cancel, progress)
    progress("Finding images…", 0, 0)
    old_files, new_files = image_index(old_root, cancel), image_index(new_root, cancel)
    if not old_files or not new_files:
        raise ValueError("Both sets must contain images.")
    shared = old_files.keys() & new_files.keys()
    added, removed = new_files.keys() - old_files.keys(), old_files.keys() - new_files.keys()
    stage = output / (".image-compare-results-" + uuid.uuid4().hex)
    stage.mkdir()
    preserve_stage = False
    counts = {"diff": 0, "new": 0, "removed": 0}
    unchanged = 0
    try:
        for name in OUTPUT_NAMES:
            (stage / name).mkdir()
        total = len(shared) + len(added) + len(removed)
        completed = 0

        def copy_image(item, category):
            check_cancel(cancel)
            target = stage / category / item.relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.path, target)
            counts[category] += 1

        def compare_one(key):
            return key, same_image(old_files[key], new_files[key], cancel)

        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as executor:
            for key, identical in executor.map(compare_one, sorted(shared)):
                check_cancel(cancel)
                if identical:
                    unchanged += 1
                else:
                    copy_image(new_files[key], "diff")
                completed += 1
                progress(f"Comparing: {new_files[key].relative}", completed, total)
        for keys, index, category in ((added, new_files, "new"), (removed, old_files, "removed")):
            for key in sorted(keys):
                copy_image(index[key], category)
                completed += 1
                progress(f"Copying {category}: {index[key].relative}", completed, total)
        check_cancel(cancel)
        if existing_outputs(output) and not replace_existing:
            raise ValueError("Result folders appeared during comparison; run again to confirm replacement.")
        try:
            publish_outputs(stage, output, omit_empty=omit_empty)
        except RecoveryError:
            preserve_stage = True
            raise
        return Result(counts["diff"], counts["new"], counts["removed"], unchanged,
                      time.perf_counter() - started, old_root, new_root)
    finally:
        if not preserve_stage:
            cleanup_temporary(stage, output)
