#!/usr/bin/env python3
"""
Download the exact selected card images used by a public Scryfall deck,
name them in the project's card_name.png style, and zip the results.

Default behavior:
- uses the exact printings selected in the decklist
- downloads PNG card images from Scryfall
- saves one PNG per unique card/face name using snake_case naming
- writes manifest.json
- creates a ZIP containing all PNGs + manifest.json

Examples:
    python download_scryfall_deck_images_zip.py \
        "https://scryfall.com/@andro951/decks/3316831e-83b5-458c-bf88-1529930e24c8"

    python download_scryfall_deck_images_zip.py \
        "https://scryfall.com/@andro951/decks/3316831e-83b5-458c-bf88-1529930e24c8" \
        --out hulk_pack_scryfall_images

    # Offline deck-metadata mode: use a previously exported Scryfall deck JSON.
    # This skips the deck-export and per-card API requests; only image files are fetched.
    python download_scryfall_deck_images_zip.py \
        --deck-json deck-cad1d1df-d4ee-4859-912f-e39e491e9716.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

USER_AGENT = "scryfall-deck-image-downloader/1.1"
DEFAULT_DELAY = 0.12
UUID_RE = re.compile(r"/decks/([0-9a-fA-F-]{36})(?:[/?#]|$)")

OUTSIDE_GAME_SECTIONS = {"outside", "outside_the_game"}
EXCLUDED_SECTIONS = {"sideboard", "maybeboard"}


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def snake_slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unnamed"


class Fetcher:
    def __init__(self, delay: float = DEFAULT_DELAY):
        self.delay = max(0.0, float(delay))
        self._last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def fetch_bytes(self, url: str) -> bytes:
        while True:
            self._wait()
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json;q=0.9,image/png;q=0.8,*/*;q=0.7",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                self._last_request = time.time()
                return data
            except urllib.error.HTTPError as exc:
                self._last_request = time.time()
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after is not None else 1.0
                    except ValueError:
                        delay = 1.0
                    eprint(f"Rate limited for {url}; retrying in {delay:g}s...")
                    time.sleep(max(delay, 0.25))
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"HTTP {exc.code} for {url}\n{detail}") from exc
            except urllib.error.URLError as exc:
                self._last_request = time.time()
                raise RuntimeError(f"Could not reach {url}: {exc}") from exc

    def fetch_json(self, url: str) -> Dict[str, Any]:
        raw = self.fetch_bytes(url)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Unexpected JSON payload from {url}: expected object")
        return parsed


def extract_deck_uuid(deck_url: str) -> str:
    parsed = urllib.parse.urlparse(deck_url)
    if parsed.netloc.lower() not in {"scryfall.com", "www.scryfall.com"}:
        raise ValueError("Deck URL must be on scryfall.com")
    m = UUID_RE.search(parsed.path)
    if not m:
        raise ValueError("Could not find a deck UUID in the URL")
    return m.group(1)


def deck_export_url(deck_url: str) -> str:
    return f"https://api.scryfall.com/decks/{extract_deck_uuid(deck_url)}/export/json"


def normalize_section_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def iter_entries(
    deck: Mapping[str, Any],
    selected_sections: Optional[set[str]],
    include_outside_the_game: bool,
) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    entries = deck.get("entries")
    if not isinstance(entries, Mapping):
        raise RuntimeError("Deck export has no 'entries' object")
    for raw_section_name, rows in entries.items():
        section_name = str(raw_section_name)
        norm = normalize_section_name(section_name)
        if norm in EXCLUDED_SECTIONS:
            continue
        if norm in OUTSIDE_GAME_SECTIONS and not include_outside_the_game:
            continue
        if selected_sections is not None and norm not in selected_sections:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, Mapping):
                yield section_name, row


def load_deck_json(path: Path) -> Dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Could not read deck JSON {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid deck JSON in {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Deck JSON {path} must contain one JSON object")
    if not isinstance(parsed.get("entries"), Mapping):
        raise RuntimeError(f"Deck JSON {path} has no 'entries' object")
    return parsed


def png_variant_url(url: str) -> str:
    """Convert a Scryfall CDN small/normal/large image URL to its PNG variant."""
    parsed = urllib.parse.urlsplit(url.strip())
    path = parsed.path
    path = re.sub(r"/(?:small|normal|large)/", "/png/", path, count=1)
    path = re.sub(r"\.(?:jpe?g|png)$", ".png", path, flags=re.I)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def choose_digest_png_downloads(digest: Mapping[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Use the compact card_digest embedded in a Scryfall deck export.

    Deck-export JSON already identifies the exact selected printing and includes
    direct front/back image URLs. For double-faced cards, the combined Scryfall
    name is split on ' // ' so each physical face gets its own filename.
    """
    name = str(digest.get("name") or "card")
    image_uris = digest.get("image_uris")
    if not isinstance(image_uris, Mapping):
        raise RuntimeError(f"No downloadable card image found in deck JSON for {name!r}")

    front = image_uris.get("front")
    back = image_uris.get("back")
    face_names = [part.strip() for part in name.split(" // ") if part.strip()]

    results: List[Tuple[str, str, str]] = []
    if isinstance(front, str) and front.strip():
        front_name = face_names[0] if face_names else name
        results.append((front_name, png_variant_url(front), front_name))

    if isinstance(back, str) and back.strip():
        if len(face_names) >= 2:
            back_name = face_names[1]
        else:
            back_name = f"{name} back"
        results.append((back_name, png_variant_url(back), back_name))

    if results:
        return results
    raise RuntimeError(f"No downloadable card image found in deck JSON for {name!r}")


def uniquify_filename(base_name: str, used: set[str]) -> str:
    candidate = f"{base_name}.png"
    if candidate not in used:
        used.add(candidate)
        return candidate
    n = 2
    while True:
        candidate = f"{base_name}__{n}.png"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


def write_zip(zip_path: Path, files: List[Path], base_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.relative_to(base_dir))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the exact selected Scryfall card images from a deck, name them card_name.png style, and zip them."
    )
    parser.add_argument("deck_url", nargs="?", help="Public Scryfall deck URL. Optional when --deck-json is supplied.")
    parser.add_argument(
        "--deck-json",
        type=Path,
        help=(
            "Read an already-exported Scryfall deck JSON instead of fetching the deck export. "
            "In this mode the embedded card_digest image URLs are used directly, so per-card API requests are skipped."
        ),
    )
    parser.add_argument("--out", type=Path, default=Path("downloaded_scryfall_deck_images"), help="Output folder")
    parser.add_argument("--sections", help="Optional comma-separated normalized section names to include after the default section filters.")
    parser.add_argument("--include-outside-the-game", action="store_true", help="Include the deck's Outside The Game section. Off by default.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help=f"Minimum delay between requests (default: {DEFAULT_DELAY})")
    parser.add_argument("--keep-duplicates", action="store_true", help="Download duplicate deck entries separately. Default: one file per unique card/face name.")
    args = parser.parse_args()

    selected_sections: Optional[set[str]] = None
    if args.sections:
        selected_sections = {normalize_section_name(x) for x in args.sections.split(",") if x.strip()}

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    fetcher = Fetcher(delay=args.delay)

    using_deck_json = args.deck_json is not None
    if using_deck_json:
        json_path = args.deck_json.expanduser().resolve()
        eprint(f"Deck JSON: {json_path}")
        deck = load_deck_json(json_path)
        deck_url = str(args.deck_url or deck.get("scryfall_uri") or "")
        deck_id = str(deck.get("id") or "").strip()
        export_url = f"https://api.scryfall.com/decks/{deck_id}/export/json" if deck_id else ""
    else:
        if not args.deck_url:
            raise ValueError("Provide a Scryfall deck URL or --deck-json <file>")
        deck_url = args.deck_url
        export_url = deck_export_url(deck_url)
        eprint(f"Deck export: {export_url}")
        deck = fetcher.fetch_json(export_url)

    deck_name = str(deck.get("name") or out_dir.name)
    manifest_cards: List[Dict[str, Any]] = []
    used_filenames: set[str] = set()
    seen_unique_keys: set[Tuple[str, str]] = set()
    saved_paths: List[Path] = []

    for section_name, row in iter_entries(deck, selected_sections, args.include_outside_the_game):
        digest = row.get("card_digest") if isinstance(row, Mapping) else None
        if not isinstance(digest, Mapping):
            continue
        scryfall_id = str(digest.get("id") or "").strip()
        if not scryfall_id:
            continue
        quantity = int(row.get("quantity") or row.get("count") or 1)

        card = digest
        downloads = choose_digest_png_downloads(digest)
        saved_for_this_card: List[str] = []
        for logical_name, image_url, face_name in downloads:
            unique_key = (scryfall_id, face_name)
            if not args.keep_duplicates and unique_key in seen_unique_keys:
                continue
            seen_unique_keys.add(unique_key)

            file_stem = snake_slug(logical_name)
            filename = uniquify_filename(file_stem, used_filenames)
            path = out_dir / filename
            image_bytes = fetcher.fetch_bytes(image_url)
            path.write_bytes(image_bytes)
            saved_paths.append(path)
            saved_for_this_card.append(filename)

        if saved_for_this_card:
            manifest_cards.append({
                "name": str(digest.get("name") or row.get("raw_text") or scryfall_id),
                "section": section_name,
                "quantity": quantity,
                "scryfall_id": scryfall_id,
                "scryfall_uri": card.get("scryfall_uri") or digest.get("scryfall_uri"),
                "files": saved_for_this_card,
            })

    manifest = {
        "deck_name": deck_name,
        "deck_url": deck_url,
        "deck_export_url": export_url,
        "deck_json": str(args.deck_json.expanduser().resolve()) if args.deck_json else None,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cards": manifest_cards,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    saved_paths.append(manifest_path)

    zip_name = f"{snake_slug(deck_name)}_scryfall_images.zip"
    zip_path = out_dir.parent / zip_name
    write_zip(zip_path, saved_paths, out_dir)

    print(f"Saved {len(saved_paths)-1} PNG file(s) to {out_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"ZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        eprint("Interrupted.")
        raise SystemExit(130)
    except Exception as exc:
        eprint(f"ERROR: {exc}")
        raise SystemExit(1)
