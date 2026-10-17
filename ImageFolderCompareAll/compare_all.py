"""Double-click runner: compare the latest two ZIP exports for every deck."""
from __future__ import annotations

import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Source runs share the same engine as the interactive folder picker.
# PyInstaller bundles the engine so the EXE needs no other app installed.
APP_FOLDER = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(APP_FOLDER.parent / "ImageFolderCompare"))

from compare_core import Candidate, OUTPUT_NAMES, RecoveryError, cleanup_temporary, compare_sets, existing_outputs, publish_outputs

DEFAULT_BLACKLIST = """# Top-level folders inside cards/ to ignore, one name per line.
# Names are case-insensitive. Blank lines and lines starting with # are ignored.
# Decks without a cards/ subfolder or with fewer than two ZIPs are skipped anyway.
.git
.github
ArtFetcher
ImageFolderCompare
ImageFolderCompareAll
ProxyFoundry
ScryfallFullCardImageDownloader
templates
"""


@dataclass
class BatchResult:
    compared: int = 0
    skipped: int = 0
    failed: int = 0
    changed: int = 0
    added: int = 0
    removed: int = 0
    unchanged: int = 0
    published: bool = False


def read_blacklist(path):
    if not path.exists():
        path.write_text(DEFAULT_BLACKLIST, encoding="utf-8")
    return {line.strip().rstrip("/\\").casefold() for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")}


def newest_zip_sets(cards_folder):
    archives = sorted((p for p in cards_folder.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() == ".zip"),
                      key=lambda p: (p.stat().st_mtime_ns, p.name.casefold()))
    if len(archives) < 2:
        return None
    folders = {p.name.casefold(): p for p in cards_folder.iterdir() if p.is_dir() and not p.is_symlink()}
    return tuple(Candidate(folders.get(path.stem.casefold(), cards_folder / path.stem), path.stat().st_mtime, path)
                 for path in archives[-2:])


def run_all(repo, output, *, emit=print):
    started = time.perf_counter()
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if not repo.is_dir() or output.parent != repo:
        raise ValueError("Place ImageFolderCompareAll directly inside your cards repository.")
    blacklist = read_blacklist(output / "blacklist.txt")
    existing_outputs(output)
    result = BatchResult()
    stage = output / (".image-compare-all-results-" + uuid.uuid4().hex)
    stage.mkdir()
    preserve_stage = False
    lines = []

    def log(message):
        lines.append(message)
        emit(message)

    log("IMAGE FOLDER COMPARE ALL")
    log(f"Run: {datetime.now().astimezone().isoformat(timespec='seconds')}")
    log(f"Cards repository: {repo}")
    log("ZIP modification times determine older/newer; extracted folder dates are ignored.")
    log("Review images: compare generated RIGHT panel only. Other images: compare all pixels exactly.")
    log("")
    try:
        for deck in sorted(repo.iterdir(), key=lambda p: p.name.casefold()):
            if not deck.is_dir() or deck.is_symlink():
                continue
            if deck == output or deck.name.casefold() in blacklist:
                result.skipped += 1
                log(f"SKIP {deck.name}: blacklisted")
                continue
            cards = deck / "cards"
            if not cards.is_dir() or cards.is_symlink():
                result.skipped += 1
                log(f"SKIP {deck.name}: no cards subfolder")
                continue
            try:
                pair = newest_zip_sets(cards)
                if pair is None:
                    result.skipped += 1
                    log(f"SKIP {deck.name}: fewer than two ZIP files")
                    continue
                older, newer = pair
                log(f"COMPARE {deck.name}")
                log(f"  Older: {older.archive.name}")
                log(f"  Newer: {newer.archive.name}")
                work = stage / "work" / deck.name
                last_update = 0

                def progress(text, current, total):
                    nonlocal last_update
                    now = time.monotonic()
                    if now - last_update >= 2:
                        suffix = f" ({current}/{total})" if total else ""
                        emit(f"  {text}{suffix}")
                        last_update = now

                compared = compare_sets(cards, older, newer, output_folder=work, omit_empty=True, progress=progress)
                for category in OUTPUT_NAMES:
                    source = work / category
                    if source.exists():
                        target = stage / category / deck.name
                        target.parent.mkdir(exist_ok=True)
                        os.replace(source, target)
                result.compared += 1
                result.changed += compared.changed
                result.added += compared.added
                result.removed += compared.removed
                result.unchanged += compared.unchanged
                log(f"  Changed {compared.changed:,} | New {compared.added:,} | Removed {compared.removed:,} | Unchanged {compared.unchanged:,}")
            except Exception as error:
                result.failed += 1
                if isinstance(error, RecoveryError):
                    preserve_stage = True
                log(f"ERROR {deck.name}: {error}")
        log("")
        if result.failed:
            log("Some decks failed. Previous result folders were kept; this run was not published.")
        else:
            try:
                publish_outputs(stage, output, omit_empty=True)
            except RecoveryError:
                preserve_stage = True
                raise
            result.published = True
            log(f"Results saved in: {output}")
        log(f"Decks compared: {result.compared:,} | Skipped: {result.skipped:,} | Failed: {result.failed:,}")
        log(f"Changed: {result.changed:,} | New: {result.added:,} | Removed: {result.removed:,} | Unchanged: {result.unchanged:,}")
        log(f"Finished in {time.perf_counter() - started:.2f} seconds.")
        return result
    except BaseException as error:
        log("Run interrupted. Previous results were kept." if isinstance(error, KeyboardInterrupt) else f"ERROR: {error}")
        raise
    finally:
        (output / "last-run.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not preserve_stage:
            cleanup_temporary(stage, output)


def main():
    if sys.stdout is not None:
        sys.stdout.reconfigure(errors="replace")
    code = 0
    try:
        result = run_all(APP_FOLDER.parent, APP_FOLDER)
        if result.failed:
            code = 1
    except KeyboardInterrupt:
        print("\nCancelled. Previous results were kept.")
        code = 1
    except Exception as error:
        print(f"\nERROR: {error}")
        code = 1
    if "--no-pause" not in sys.argv:
        try:
            input("\nPress Enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
