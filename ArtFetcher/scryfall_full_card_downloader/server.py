#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping

APP_DIR = Path(__file__).resolve().parent
INDEX_HTML = APP_DIR / "index.html"
OUTPUT_ROOT = APP_DIR / "output"
HOST = "127.0.0.1"
PORT = 8765
USER_AGENT = "Isaac-Scryfall-Full-Card-Downloader/1.1"
REQUEST_DELAY = 0.12
UUID_RE = re.compile(r"/decks/([0-9a-fA-F-]{36})(?:[/?#]|$)")


class JobState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.success: bool | None = None
        self.logs: list[str] = []
        self.output_dir: Path | None = None
        self.zip_path: Path | None = None

    def reset(self) -> None:
        with self.lock:
            self.running = True
            self.success = None
            self.logs = []
            self.output_dir = None
            self.zip_path = None

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        with self.lock:
            self.logs.append(line)
        print(line, flush=True)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "success": self.success,
                "log": "\n".join(self.logs),
                "output_dir": str(self.output_dir) if self.output_dir else None,
                "zip_name": self.zip_path.name if self.zip_path else None,
            }


STATE = JobState()


def safe_slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "card"


def extract_deck_uuid(deck_url: str) -> str:
    parsed = urllib.parse.urlparse(deck_url.strip())
    if parsed.netloc.lower() not in {"scryfall.com", "www.scryfall.com"}:
        raise ValueError("That is not a Scryfall deck link.")
    match = UUID_RE.search(parsed.path)
    if not match:
        raise ValueError("Could not find a Scryfall deck ID in that link.")
    return match.group(1)


def png_variant_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    path = re.sub(r"/(?:small|normal|large)/", "/png/", parsed.path, count=1)
    path = re.sub(r"\.(?:jpe?g|png)$", ".png", path, flags=re.I)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


class Fetcher:
    def __init__(self) -> None:
        self.last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)

    def bytes(self, url: str) -> bytes:
        while True:
            self._wait()
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json;q=0.9,*/*;q=0.8",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = response.read()
                self.last_request = time.monotonic()
                return data
            except urllib.error.HTTPError as exc:
                self.last_request = time.monotonic()
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 1.0
                    except ValueError:
                        delay = 1.0
                    STATE.log(f"Rate limited; retrying in {delay:g}s…")
                    time.sleep(max(delay, 0.25))
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:800]
                raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc
            except urllib.error.URLError as exc:
                self.last_request = time.monotonic()
                raise RuntimeError(f"Could not reach {url}: {exc}") from exc

    def json(self, url: str) -> dict[str, Any]:
        raw = self.bytes(url)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON returned by Scryfall: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Unexpected Scryfall response.")
        return parsed


def iter_deck_rows(deck: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    entries = deck.get("entries")
    if not isinstance(entries, Mapping):
        raise RuntimeError("Scryfall deck export did not contain deck entries.")
    for section_name, rows in entries.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, Mapping) and row.get("found", True) is not False:
                yield str(section_name), row


def digest_images(digest: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    name = str(digest.get("name") or "card")
    image_uris = digest.get("image_uris")
    if not isinstance(image_uris, Mapping):
        raise RuntimeError(f"No full-card image URLs were present for {name}.")

    front = image_uris.get("front")
    back = image_uris.get("back")
    face_names = [part.strip() for part in name.split(" // ") if part.strip()]
    images: list[tuple[str, str, str]] = []

    if isinstance(front, str) and front.strip():
        front_name = face_names[0] if face_names else name
        images.append((front_name, png_variant_url(front), "front"))

    if isinstance(back, str) and back.strip():
        back_name = face_names[1] if len(face_names) >= 2 else f"{name} back"
        images.append((back_name, png_variant_url(back), "back"))

    if not images:
        raise RuntimeError(f"No full-card image URLs were present for {name}.")
    return images


def unique_filename(display_name: str, face_label: str, used: set[str]) -> str:
    stem = safe_slug(display_name)
    if face_label == "back":
        stem += "__back"
    candidate = f"{stem}.png"
    if candidate not in used:
        used.add(candidate)
        return candidate
    n = 2
    while True:
        candidate = f"{stem}__{n}.png"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


def run_job(deck_url: str) -> None:
    STATE.reset()
    try:
        deck_uuid = extract_deck_uuid(deck_url)
        export_url = f"https://api.scryfall.com/decks/{deck_uuid}/export/json"
        STATE.log(f"Deck: {deck_url}")
        STATE.log("Fetching Scryfall deck export…")

        fetcher = Fetcher()
        deck = fetcher.json(export_url)
        deck_name = str(deck.get("name") or "scryfall_deck")

        rows = list(iter_deck_rows(deck))
        if not rows:
            raise RuntimeError("No cards were found in that Scryfall deck.")

        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        run_dir = OUTPUT_ROOT / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_slug(deck_name)}"
        run_dir.mkdir(parents=True, exist_ok=False)
        with STATE.lock:
            STATE.output_dir = run_dir

        # Exact selected printing/face is identified by the card_digest in the deck export.
        seen_faces: set[tuple[str, str]] = set()
        used_names: set[str] = set()
        image_paths: list[Path] = []

        STATE.log(f"Found {len(rows)} deck entr{'y' if len(rows) == 1 else 'ies'}.")
        for section, row in rows:
            digest = row.get("card_digest")
            if not isinstance(digest, Mapping):
                continue
            scryfall_id = str(digest.get("id") or "").strip()
            card_name = str(digest.get("name") or row.get("raw_text") or "card")
            if not scryfall_id:
                STATE.log(f"WARNING: Skipping {card_name}: no Scryfall card ID.")
                continue

            for display_name, image_url, face_label in digest_images(digest):
                key = (scryfall_id, face_label)
                if key in seen_faces:
                    continue
                seen_faces.add(key)

                filename = unique_filename(display_name, face_label, used_names)
                destination = run_dir / filename
                STATE.log(f"Downloading {card_name}{' [' + face_label + ']' if face_label == 'back' else ''}…")
                destination.write_bytes(fetcher.bytes(image_url))
                image_paths.append(destination)

        if not image_paths:
            raise RuntimeError("No card images were downloaded.")

        zip_path = run_dir / f"{safe_slug(deck_name)}_full_card_images.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in image_paths:
                zf.write(path, arcname=path.name)

        STATE.log(f"Created ZIP with {len(image_paths)} full-card PNG image(s).")
        STATE.log(f"ZIP: {zip_path}")
        STATE.log(f"Output folder: {run_dir}")

        # Save a copy of the log next to the output, but do not add it to the image ZIP.
        log_path = run_dir / "download.log"
        log_path.write_text(STATE.snapshot()["log"] + "\n", encoding="utf-8")

        with STATE.lock:
            STATE.zip_path = zip_path
            STATE.success = True
            STATE.running = False

    except Exception as exc:
        STATE.log(f"ERROR: {exc}")
        with STATE.lock:
            STATE.success = False
            STATE.running = False
        snap = STATE.snapshot()
        if snap.get("output_dir"):
            try:
                Path(snap["output_dir"]).joinpath("download.log").write_text(snap["log"] + "\n", encoding="utf-8")
            except OSError:
                pass


def open_folder(path: Path) -> None:
    path = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Handler(BaseHTTPRequestHandler):
    server_version = "ScryfallFullCardDownloader/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        self.send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            self.send_bytes(INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self.send_json(STATE.snapshot())
            return
        if path == "/api/log.txt":
            text = STATE.snapshot()["log"] or "No logs yet.\n"
            self.send_bytes(
                text.encode("utf-8"),
                "text/plain; charset=utf-8",
                extra_headers={"Content-Disposition": 'attachment; filename="scryfall_downloader.log"'},
            )
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/start":
            if STATE.snapshot()["running"]:
                self.send_json({"error": "A download is already running."}, 409)
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self.send_json({"error": "Invalid JSON request."}, 400)
                return
            deck_url = str(payload.get("deck_url") or "").strip()
            if not deck_url:
                self.send_json({"error": "Scryfall deck link is empty."}, 400)
                return
            try:
                extract_deck_uuid(deck_url)
            except ValueError as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            threading.Thread(target=run_job, args=(deck_url,), daemon=True).start()
            self.send_json({"ok": True})
            return

        if path == "/api/open-output":
            snap = STATE.snapshot()
            output_dir = snap.get("output_dir")
            target = Path(output_dir) if output_dir else OUTPUT_ROOT
            try:
                target.mkdir(parents=True, exist_ok=True)
                open_folder(target)
                self.send_json({"ok": True, "path": str(target)})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return

        self.send_json({"error": "Not found"}, 404)


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print("Scryfall Full Card Image Downloader")
    print(f"Open: {url}")
    print("Press Ctrl+C in this window to stop the app.")
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
