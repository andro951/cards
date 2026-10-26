"""Opt-in local review batches. Normal generation never enters this service."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

from .domain import ConflictError, ValidationError, slug

SESSION_PATTERN = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$")
REVIEW_ZIP_PATTERN = re.compile(r"^BulkProxyForge_Review_Images_[A-Za-z0-9_.-]+_[0-9a-f]{8}\.zip$")
MAX_ZIP_BYTES = 2 * 1024 ** 3
MAX_UPLOAD_CHUNK = 8 * 1024 ** 2


class DeveloperBatchReview:
    def __init__(self, app_root: Path, workspace, *, checker=None, process_runner=None):
        self.cards_root = Path(app_root).resolve().parent
        self.folder_mapping_path = Path(app_root).resolve() / "batch-review-folders.json"
        self.workspace = workspace
        self.checker = Path(checker or self.cards_root / "ImageFolderCompareAll" / "ImageFolderCompareAll.exe").resolve()
        self.process_runner = process_runner or subprocess.run
        self._lock = threading.Lock()
        self._sessions_lock = threading.RLock()
        self._sessions = {}
        self._stage_prefix = ".proxyfoundry-batch-review-"

    def available(self):
        return self.checker.is_file() and self.cards_root.is_dir()

    def candidates(self, download_all=False):
        decks, skipped = [], []
        for deck in self.workspace.list_decks():
            if self._eligible(deck, download_all):
                decks.append({key: deck.get(key) for key in ("id", "name", "status", "printStatus")})
            elif deck.get("printStatus") == "tokens-not-ready":
                skipped.append({"name": deck["name"], "reason": "Token assignments need attention"})
            elif deck.get("status") == "attention":
                skipped.append({"name": deck["name"], "reason": "Needs attention before generation"})
            elif deck.get("status") == "draft":
                skipped.append({"name": deck["name"], "reason": "Empty deck"})
        return {"available": self.available(), "decks": decks, "skipped": skipped}

    def eligible(self):
        return [deck for deck in self.workspace.list_decks() if self._eligible(deck)]

    def _eligible(self, deck, download_all=False):
        statuses = {"draft", "prepared", "ready"} if download_all else {"draft", "prepared"}
        if deck.get("status") not in statuses or deck.get("printStatus") == "tokens-not-ready":
            return False
        return (deck.get("summary") or {}).get("faces", 0) > 0

    def start(self, deck_ids, download_all=False):
        if not isinstance(deck_ids, list) or not deck_ids or len(deck_ids) > 500:
            raise ValidationError("Choose at least one deck for the review batch.")
        if any(not isinstance(value, str) for value in deck_ids) or len(set(deck_ids)) != len(deck_ids):
            raise ValidationError("The review batch contains an invalid or duplicate deck ID.")
        if not self.available():
            raise ValidationError(f"The all-check program was not found: {self.checker}")
        self._expire_sessions()
        if not self._lock.acquire(blocking=False):
            raise ConflictError("A review batch is already running.")

        stage = None
        try:
            current = {deck["id"]: deck for deck in self.workspace.list_decks()}
            folder_mapping = self._folder_mapping()
            selected, used_cards = [], set()
            for ident in deck_ids:
                deck = current.get(ident)
                if not deck or not self._eligible(deck, download_all):
                    raise ConflictError("A selected deck's status changed; refresh the deck list and run again.")
                cards = self._cards_folder(deck["name"], folder_mapping)
                if cards in used_cards:
                    raise ValidationError("Two selected decks map to the same Cards folder.")
                used_cards.add(cards)
                selected.append({"id": ident, "name": deck["name"], "cards": cards})

            stage = self.cards_root / (self._stage_prefix + uuid.uuid4().hex)
            stage.mkdir()
            session_id = str(uuid.uuid4())
            with self._sessions_lock:
                self._sessions[session_id] = {"stage": stage, "decks": selected, "files": {}, "uploads": {},
                                              "committing": False, "created": time.time(), "mutex": threading.RLock()}
            return {"id": session_id}
        except Exception:
            if stage:
                self._remove_stage(stage)
            self._lock.release()
            raise

    def begin_upload(self, session_id, deck_id, filename, size, revision):
        session = self._session(session_id)
        with session["mutex"]:
            self._editable(session)
            current = self._ready(session, deck_id, revision)
            self._filename(session, deck_id, filename)
            if type(size) is not int or not 0 < size <= MAX_ZIP_BYTES:
                raise ValidationError("Review ZIPs must be between 1 byte and 2 GB.")
            if deck_id in session["uploads"]:
                raise ConflictError("This deck already has an upload in the batch.")
            path = session["stage"] / filename
            path.touch(exist_ok=False)
            session["uploads"][deck_id] = {"path": path, "size": size, "offset": 0, "revision": current.get("revision")}
            return {"offset": 0}

    def upload_chunk(self, session_id, deck_id, offset, raw):
        session = self._session(session_id)
        with session["mutex"]:
            self._editable(session)
            upload = session["uploads"].get(deck_id)
            if not upload or deck_id in session["files"]:
                raise ValidationError("Start a review ZIP upload first.")
            if type(offset) is not int or offset != upload["offset"]:
                raise ConflictError("Review ZIP upload offset changed. Start the batch again.")
            if not raw or len(raw) > MAX_UPLOAD_CHUNK or offset + len(raw) > upload["size"]:
                raise ValidationError("Invalid review ZIP chunk size.")
            with upload["path"].open("ab") as stream:
                stream.write(raw)
            upload["offset"] += len(raw)
            return {"offset": upload["offset"]}

    def finish_upload(self, session_id, deck_id):
        session = self._session(session_id)
        with session["mutex"]:
            self._editable(session)
            upload = session["uploads"].get(deck_id)
            if not upload or upload["offset"] != upload["size"]:
                raise ValidationError("The review ZIP upload is incomplete.")
            self._ready(session, deck_id, upload["revision"])
            self._validate_zip(upload["path"])
            session["files"][deck_id] = {"path": upload["path"], "revision": upload["revision"]}
            return {"filename": upload["path"].name, "bytes": upload["size"]}

    def stage_review(self, session_id, deck_id, token, filename, revision=None):
        # Older browsers retain the normal exporter's existing fallback.
        session = self._session(session_id)
        with session["mutex"]:
            self._editable(session)
            current = self._ready(session, deck_id, revision)
            self._filename(session, deck_id, filename)
            if not isinstance(token, str) or not SESSION_PATTERN.fullmatch(token):
                raise ValidationError("Invalid review export token.")
            source = self.workspace.review_download_file(token, filename)
            if not source.is_file() or source.is_symlink():
                raise ValidationError("The completed review export is missing.")
            self._validate_zip(source)
            staged = session["stage"] / filename
            shutil.copyfile(source, staged)
            session["files"][deck_id] = {"path": staged, "revision": current.get("revision")}
            return {"filename": filename, "bytes": staged.stat().st_size}

    def commit(self, session_id, progress=lambda *args: None, cancel=lambda: False):
        session = self._session(session_id)
        with session["mutex"]:
            self._editable(session)
            if set(session["files"]) != {row["id"] for row in session["decks"]}:
                raise ValidationError("Not every selected deck has a completed review export. Nothing was copied.")
            for row in session["decks"]:
                self._ready(session, row["id"], session["files"][row["id"]]["revision"])
            session["committing"] = True

        placed, keep_stage = [], False
        try:
            for row in session["decks"]:
                if cancel():
                    raise ValidationError("Review batch cancelled before comparison.")
                source = session["files"][row["id"]]["path"]
                target = row["cards"] / source.name
                # An exclusive hard link publishes without copying or overwriting an old ZIP.
                os.link(source, target)
                placed.append((target, source))
                latest = max((path.stat().st_mtime for path in row["cards"].glob("*.zip")), default=0)
                stamp = max(time.time(), latest + 1)
                os.utime(target, (stamp, stamp))
                progress(len(placed), len(session["decks"]), f"Saved review ZIP for {row['name']}")

            if cancel():
                raise ValidationError("Review batch cancelled before comparison.")
            progress(0, 0, "Running ImageFolderCompareAll; waiting for its complete report")
            options = {"cwd": str(self.checker.parent), "capture_output": True, "text": True,
                       "encoding": "utf-8", "errors": "replace", "timeout": 3600}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = self.process_runner([str(self.checker), "--no-pause"], **options)
            if result.returncode:
                detail = ((result.stdout or "") + "\n" + (result.stderr or ""))[-4000:].strip()
                raise ValidationError("All-check failed; the previous comparison results were kept. " + detail)
            report = result.stdout or ""
            matches = re.findall(r"Changed: ([\d,]+) \| New: ([\d,]+) \| Removed: ([\d,]+) \| Unchanged: ([\d,]+)", report)
            counts = dict(zip(("changed", "new", "removed", "unchanged"),
                              (int(value.replace(",", "")) for value in matches[-1]))) if matches else None
            return {"decks": len(session["decks"]), "files": [path.name for path, _ in placed],
                    "report": report[-12000:], "counts": counts}
        except Exception as error:
            keep_stage = True
            for target, source in reversed(placed):
                if target.exists():
                    if not source.exists() or not os.path.samefile(target, source):
                        raise ValidationError(f"A published ZIP changed externally. Recovery files are in {session['stage']}.") from error
                    target.unlink()
            raise ValidationError(f"{error} New review ZIPs were kept in {session['stage']}; previous ZIPs are unchanged.") from error
        finally:
            self._finish(session_id, session, keep_stage=keep_stage)

    def abort(self, session_id):
        self._validate_session_id(session_id)
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session:
            with session["mutex"]:
                self._editable(session)
                self._finish(session_id, session)
        return {"ok": True}

    def _validate_session_id(self, session_id):
        if not isinstance(session_id, str) or not SESSION_PATTERN.fullmatch(session_id):
            raise ValidationError("Invalid review batch ID.")

    def _session(self, session_id):
        self._validate_session_id(session_id)
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if not session:
            raise ValidationError("The review batch expired. Start it again.")
        return session

    def _expire_sessions(self):
        # Only explicit batch starts check for abandoned tabs; startup and generation do no cleanup work.
        with self._sessions_lock:
            sessions = list(self._sessions.items())
        for session_id, session in sessions:
            with session["mutex"]:
                if not session["committing"] and time.time() - session["created"] > 12 * 60 * 60:
                    self._finish(session_id, session, keep_stage=True)

    def _editable(self, session):
        if session["committing"]:
            raise ConflictError("Comparison is in progress. Wait for its report.")
        with self._sessions_lock:
            if not any(value is session for value in self._sessions.values()):
                raise ConflictError("This batch has already finished.")

    def _ready(self, session, deck_id, revision=None):
        if not any(row["id"] == deck_id for row in session["decks"]):
            raise ValidationError("That deck is not part of this review batch.")
        current = self.workspace.deck(deck_id)
        if current.get("status") != "ready" or current.get("printStatus") != "ready":
            raise ConflictError(f"{current.get('name', 'Deck')}: status changed; generation did not reach Ready to print.")
        if revision is not None and current.get("revision") != revision:
            raise ConflictError(f"{current.get('name', 'Deck')}: changed after the review export. Start the batch again.")
        return current

    def _filename(self, session, deck_id, filename):
        if not isinstance(filename, str) or not REVIEW_ZIP_PATTERN.fullmatch(filename):
            raise ValidationError("Invalid review export filename.")
        if deck_id in session["files"] or (session["stage"] / filename).exists():
            raise ConflictError("This deck or ZIP already has a review export in the batch.")

    def _validate_zip(self, path):
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if not infos or any(not re.fullmatch(r"[A-Za-z0-9_.-]+\.png", item.filename) for item in infos):
                    raise ValidationError("The review ZIP must contain PNG review images.")
                if len({item.filename for item in infos}) != len(infos):
                    raise ValidationError("The review ZIP contains duplicate filenames.")
        except zipfile.BadZipFile as error:
            raise ValidationError("The review export is not a valid ZIP file.") from error

    def _folder_mapping(self):
        # Read once per batch, so editing the aliases needs no server restart.
        try:
            raw = self.folder_mapping_path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return {}
        except OSError as error:
            raise ValidationError(f"Cannot read {self.folder_mapping_path}: {error}") from error
        try:
            configured = json.loads(raw)
        except ValueError as error:
            raise ValidationError(f"Invalid JSON in {self.folder_mapping_path}: {error}") from error
        if not isinstance(configured, dict):
            raise ValidationError(f"{self.folder_mapping_path.name} must map deck names to folder names.")
        mapping = {}
        for name, folder in configured.items():
            if (not slug(name) or not isinstance(folder, str) or not folder.strip()
                    or folder != folder.strip() or folder.endswith(".")
                    or re.search(r'[<>:"/\\|?*\x00-\x1f]', folder) or folder in {".", ".."}):
                raise ValidationError(f"Invalid folder mapping for {name!r}; use a single folder name inside Cards.")
            key = slug(name)
            if key in mapping:
                raise ValidationError(f"Duplicate deck name in {self.folder_mapping_path.name}: {name}.")
            mapping[key] = folder
        return mapping

    def _cards_folder(self, deck_name, folder_mapping=None):
        mapping = self._folder_mapping() if folder_mapping is None else folder_mapping
        mapped_name = mapping.get(slug(deck_name))
        candidates = []
        for folder in self.cards_root.iterdir():
            matches = (folder.name.casefold() == mapped_name.casefold() if mapped_name is not None
                       else slug(folder.name) == slug(deck_name))
            if not folder.is_dir() or folder.is_symlink() or not matches:
                continue
            cards = folder / "cards"
            if cards.is_dir() and not cards.is_symlink() and cards.resolve().parent.parent == self.cards_root:
                candidates.append(cards.resolve())
        if len(candidates) != 1:
            hint = (f" Mapping points to {mapped_name}/cards." if mapped_name is not None else
                    f" Add an alias in {self.folder_mapping_path.name} if its folder has a different name.")
            raise ValidationError(f"{deck_name}: expected one matching Cards folder; found {len(candidates)}.{hint}")
        return candidates[0]

    def _finish(self, session_id, session, *, keep_stage=False):
        with self._sessions_lock:
            if self._sessions.get(session_id) is not session:
                return
            self._sessions.pop(session_id)
            try:
                if not keep_stage:
                    self._remove_stage(session["stage"])
            finally:
                self._lock.release()

    def _remove_stage(self, stage):
        if stage.parent != self.cards_root or not stage.name.startswith(self._stage_prefix) or stage.is_symlink():
            raise ValueError("Refusing to remove an unrelated review-batch folder.")
        if stage.exists():
            shutil.rmtree(stage)
