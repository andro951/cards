#!/usr/bin/env python3
"""
scryfall_to_card_data.py

Create semantic card-data JSON for card_data_to_cardconjurer.py from:
  - exact Magic card names,
  - normal Scryfall card-page URLs, or
  - Scryfall API card URLs.

This script does NOT create Card Conjurer layout JSON. It only creates source
card facts. The separate card_data_to_cardconjurer.py compiler owns all visual
frame/layout logic.

Project convention expected by default:

    <project>/
      art/
        card_name.png
      scryfall_art/        # populated when --use-scryfall-art is enabled
      set_symbol/
        common.png
        uncommon.png
        rare.png
        mythic.png

Example:

    python scryfall_to_card_data.py \
      --project derevi \
      --repo andro951/cards \
      --branch main \
      --list cards.txt \
      -o derevi_card_data.json

Or directly from one or more Scryfall links/names:

    python scryfall_to_card_data.py \
      --project derevi \
      "https://scryfall.com/card/c13/186/derevi-empyrial-tactician" \
      "Spellseeker" \
      -o cards.json

Optional custom flavor text:

    python scryfall_to_card_data.py ... \
      --flavor-overrides flavor_overrides.json

Where flavor_overrides.json is a simple object:

    {
      "Derevi, Empyrial Tactician": "Custom flavor here.",
      "Spellseeker": "Another custom line."
    }

Pillow is required only for special Scryfall-art crops (for example Saga Creatures with trailing creature rules text).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

API_ROOT = "https://api.scryfall.com"
DEFAULT_REPO = "andro951/cards"
DEFAULT_BRANCH = "main"
DEFAULT_DELAY = 0.25  # 4 req/sec; conservative enough for full-deck two-lookup runs.
CACHE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60
MANUAL_REFRESH_MIN_AGE_SECONDS = 7 * 24 * 60 * 60

MAIN_TYPES = {
    "Artifact",
    "Battle",
    "Creature",
    "Enchantment",
    "Instant",
    "Kindred",
    "Land",
    "Planeswalker",
    "Sorcery",
    "Tribal",  # accepted for older/custom data; current Oracle normally uses Kindred.
}
SUPERTYPES = {"Basic", "Legendary", "Snow", "World"}
BASIC_LAND_COLORS = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}
RARITIES = {"common", "uncommon", "rare", "mythic"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class DataError(RuntimeError):
    pass


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


SAGA_CREATURE_RULES_ART_TRIM_TOP = 99
SAGA_CREATURE_RULES_ART_TRIM_BOTTOM = 83
SAGA_CREATURE_RULES_ART_TRIM_VERSION = "saga_creature_rules2_trim_99_83_v1"


def saga_creature_trailing_rules_text(type_line: str, oracle_text: str) -> str:
    """Return non-chapter creature rules on an Enchantment Creature — Saga.

    This mirrors the Saga Creature parser in the Card Conjurer compiler: chapter
    lines are consumed by the Saga ability column, while any subsequent ordinary
    rules (for example ``Flying`` on Summon: Bahamut) belong in the normal
    creature-rules box. Those printings need a tighter Scryfall art crop.
    """
    semantic = split_type_line(type_line)
    if not ({"Enchantment", "Creature"} <= set(semantic["types"])):
        return ""
    if "Saga" not in set(semantic["subtypes"]):
        return ""

    seen_chapter = False
    trailing: List[str] = []
    for raw in str(oracle_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if not seen_chapter and line.startswith("(") and line.endswith(")"):
            continue
        if re.match(r"^([IVX]+(?:\s*,\s*[IVX]+)*)\s*[—-]\s*(.*)$", line):
            seen_chapter = True
            continue
        if seen_chapter:
            trailing.append(line)
    return "\n".join(trailing).strip()


def image_file_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if mime is None:
        raise DataError(f"Unsupported cropped art format for embedding: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DataError(f"Could not read cropped Scryfall art {path}: {exc}") from exc
    return f"data:{mime};base64," + __import__("base64").b64encode(raw).decode("ascii")


def load_json_object(path: Optional[Path], label: str) -> Dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataError(f"Could not read {label} from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DataError(f"{label} must be a JSON object mapping card names to values.")
    return value


def snake_slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("Æ", "AE").replace("æ", "ae")
    text = text.replace("Œ", "OE").replace("œ", "oe")
    text = text.replace("’", "'")
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()


def normalized_art_stem(path: Path) -> str:
    stem = snake_slug(path.stem)
    # Common project convention: 12A_card_name.png, 33B_back_face.png, etc.
    stem = re.sub(r"^\d+[a-z]?_", "", stem)
    return stem


def read_sources_from_file(path: Path) -> List[str]:
    sources: List[str] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Accept simple deck-list style leading counts: "1 Spellseeker".
        line = re.sub(r"^\s*\d+\s+x?\s+", "", line, flags=re.I)
        sources.append(line)
    return sources


class ScryfallClient:
    def __init__(
        self,
        delay: float = DEFAULT_DELAY,
        user_agent: str = "CardDataInputBuilder/1.0",
        cache_dir: Optional[Path] = None,
        refresh_card_data: bool = False,
    ):
        self.delay = max(delay, 0.11)
        self.user_agent = user_agent
        self._last_request = 0.0
        self.cache_dir = cache_dir.resolve() if cache_dir is not None else None
        self.refresh_card_data = refresh_card_data
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Preserve the older explicit cache-only environment hook for offline/debug
        # workflows. The new UI-backed cache uses --scryfall-cache-dir instead.
        legacy_cache = os.environ.get("SCRYFALL_HTTP_CACHE") if self.cache_dir is None else None
        self.legacy_cache_dir = Path(legacy_cache).resolve() if legacy_cache else None

    def _wait(self) -> None:
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _cache_key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json"

    def _persistent_cache_path(self, url: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        return self.cache_dir / self._cache_key(url)

    def _legacy_cache_path(self, url: str) -> Optional[Path]:
        if self.legacy_cache_dir is None:
            return None
        # Keep compatibility with the pre-existing extensionless cache format.
        return self.legacy_cache_dir / hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _should_refresh(self, cache_path: Path) -> bool:
        try:
            age = max(0.0, time.time() - cache_path.stat().st_mtime)
        except OSError:
            return True
        if age >= CACHE_MAX_AGE_SECONDS:
            return True
        if self.refresh_card_data and age >= MANUAL_REFRESH_MIN_AGE_SECONDS:
            return True
        return False

    @staticmethod
    def _parse_response(body: str, url: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataError(f"Scryfall returned invalid JSON for {url}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise DataError(f"Unexpected Scryfall response for {url}")
        if parsed.get("object") == "error":
            raise DataError(f"Scryfall error: {parsed.get('details', parsed)}")
        return parsed

    def _fetch_body(self, url: str, retry_429: bool) -> str:
        self._wait()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
            self._last_request = time.monotonic()
            return body
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            detail = ""
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = payload.get("details") or payload.get("code") or ""
            except Exception:
                pass
            if exc.code == 429 and retry_429:
                retry_header = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    retry_after = max(float(retry_header), 1.0) if retry_header else 60.0
                except (TypeError, ValueError):
                    retry_after = 60.0
                warn(f"Scryfall rate limit reached; retrying this request after {retry_after:g} seconds.")
                time.sleep(retry_after)
                return self._fetch_body(url, retry_429=False)
            suffix = f": {detail}" if detail else ""
            raise DataError(f"Scryfall HTTP {exc.code} for {url}{suffix}") from exc
        except urllib.error.URLError as exc:
            self._last_request = time.monotonic()
            raise DataError(f"Could not contact Scryfall: {exc}") from exc

    def fetch_binary(self, url: str, retry_429: bool = True) -> bytes:
        """Fetch non-JSON Scryfall/CDN content using the same pacing rules."""
        self._wait()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "image/*,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read()
            self._last_request = time.monotonic()
            return body
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            if exc.code == 429 and retry_429:
                retry_header = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    retry_after = max(float(retry_header), 1.0) if retry_header else 60.0
                except (TypeError, ValueError):
                    retry_after = 60.0
                warn(f"Scryfall image rate limit reached; retrying after {retry_after:g} seconds.")
                time.sleep(retry_after)
                return self.fetch_binary(url, retry_429=False)
            raise DataError(f"Scryfall image HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            self._last_request = time.monotonic()
            raise DataError(f"Could not download Scryfall art: {exc}") from exc

    def get_json(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        retry_429: bool = True,
    ) -> Dict[str, Any]:
        if params:
            encoded = urllib.parse.urlencode(params, doseq=True)
            url = url + ("&" if "?" in url else "?") + encoded

        # New read-through persistent cache. Cached responses are reused for one
        # year by default. Manual refresh only bypasses entries 7+ days old.
        cache_path = self._persistent_cache_path(url)
        if cache_path is not None and cache_path.is_file() and not self._should_refresh(cache_path):
            try:
                return self._parse_response(cache_path.read_text(encoding="utf-8"), url)
            except OSError as exc:
                raise DataError(f"Could not read Scryfall cache file {cache_path}: {exc}") from exc

        # Legacy cache-only mode remains available when SCRYFALL_HTTP_CACHE is
        # explicitly set and --scryfall-cache-dir is not being used.
        legacy_path = self._legacy_cache_path(url)
        if legacy_path is not None:
            if not legacy_path.is_file():
                raise DataError(f"Scryfall cache miss for {url}")
            try:
                return self._parse_response(legacy_path.read_text(encoding="utf-8"), url)
            except OSError as exc:
                raise DataError(f"Could not read Scryfall cache file {legacy_path}: {exc}") from exc

        body = self._fetch_body(url, retry_429=retry_429)
        parsed = self._parse_response(body, url)

        if cache_path is not None:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
                tmp_path.write_text(body, encoding="utf-8")
                os.replace(tmp_path, cache_path)
            except OSError as exc:
                warn(f"Could not write Scryfall cache file {cache_path}: {exc}")

        return parsed

    def by_exact_name(self, name: str, fuzzy: bool = False) -> Dict[str, Any]:
        try:
            return self.get_json(f"{API_ROOT}/cards/named", {"exact": name})
        except DataError:
            if not fuzzy:
                raise
            warn(f"Exact lookup failed for {name!r}; trying Scryfall fuzzy lookup.")
            return self.get_json(f"{API_ROOT}/cards/named", {"fuzzy": name})

    def by_set_collector(self, set_code: str, collector_number: str) -> Dict[str, Any]:
        set_code = urllib.parse.quote(set_code, safe="")
        collector_number = urllib.parse.quote(collector_number, safe="")
        return self.get_json(f"{API_ROOT}/cards/{set_code}/{collector_number}")

    def by_scryfall_id(self, scryfall_id: str) -> Dict[str, Any]:
        return self.get_json(f"{API_ROOT}/cards/{urllib.parse.quote(scryfall_id, safe='')}")

    def latest_english_paper_printing(self, name: str) -> Optional[Dict[str, Any]]:
        # Exact-name search, newest release first. This is used for the default
        # name-only flavor policy. If it fails, caller falls back to the resolved card.
        safe_name = name.replace("\\", "\\\\").replace('"', '\\"')
        query = f'!"{safe_name}" game:paper lang:en'
        try:
            page = self.get_json(
                f"{API_ROOT}/cards/search",
                {
                    "q": query,
                    "unique": "prints",
                    "order": "released",
                    "dir": "desc",
                },
            )
        except DataError as exc:
            warn(f"Could not search latest printing for {name!r}: {exc}")
            return None

        data = page.get("data")
        if isinstance(data, list) and data:
            return data[0] if isinstance(data[0], dict) else None
        return None


def parse_scryfall_source(source: str) -> Optional[Tuple[str, ...]]:
    """Return ('set', set, collector) or ('id', uuid), else None for a name."""
    try:
        parsed = urllib.parse.urlparse(source)
    except ValueError:
        return None

    host = parsed.netloc.lower()
    if host not in {"scryfall.com", "www.scryfall.com", "api.scryfall.com"}:
        return None

    parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]

    # https://scryfall.com/card/SET/COLLECTOR/slug
    if host.endswith("scryfall.com") and host != "api.scryfall.com":
        if len(parts) >= 3 and parts[0] == "card":
            return ("set", parts[1], parts[2])
        raise DataError(f"Unsupported Scryfall card URL: {source}")

    # https://api.scryfall.com/cards/SET/COLLECTOR
    # https://api.scryfall.com/cards/<Scryfall UUID>
    if host == "api.scryfall.com":
        if len(parts) >= 3 and parts[0] == "cards":
            return ("set", parts[1], parts[2])
        if len(parts) >= 2 and parts[0] == "cards":
            return ("id", parts[1])
        raise DataError(f"Unsupported Scryfall API card URL: {source}")

    return None


def resolve_source(client: ScryfallClient, source: str, fuzzy: bool) -> Tuple[Dict[str, Any], bool]:
    parsed = parse_scryfall_source(source)
    if parsed is None:
        return client.by_exact_name(source, fuzzy=fuzzy), False
    if parsed[0] == "set":
        return client.by_set_collector(parsed[1], parsed[2]), True
    if parsed[0] == "id":
        return client.by_scryfall_id(parsed[1]), True
    raise AssertionError(parsed)


def split_type_line(type_line: str) -> Dict[str, Any]:
    if not type_line:
        raise DataError("Scryfall card/face has no type_line.")

    normalized = str(type_line).replace("—", " - ").replace("–", " - ")
    left, sep, right = normalized.partition(" - ")
    left_tokens = left.strip().split()
    subtypes = right.strip().split() if sep and right.strip() else []

    unknown = [t for t in left_tokens if t not in MAIN_TYPES and t not in SUPERTYPES]
    if unknown:
        raise DataError(
            f"Unknown type/supertype token(s) {unknown} in Scryfall type line {type_line!r}. "
            "Update the semantic schema before generating this card."
        )

    types = [t for t in left_tokens if t in MAIN_TYPES]
    if not types:
        raise DataError(f"No supported main card type found in {type_line!r}.")

    return {
        "types": types,
        "subtypes": subtypes,
        "legendary": "Legendary" in left_tokens,
        "basic": "Basic" in left_tokens,
        "snow": "Snow" in left_tokens,
        "world": "World" in left_tokens,
    }


def face_list(card: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    faces = card.get("card_faces")
    if isinstance(faces, list) and faces:
        return [f for f in faces if isinstance(f, dict)]
    return [card]


def face_value(face: Mapping[str, Any], card: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = face.get(key)
    if value is None:
        value = card.get(key, default)
    return value if value is not None else default


def choose_flavor_source(
    client: ScryfallClient,
    resolved: Mapping[str, Any],
    was_exact_url: bool,
    flavor_policy: str,
) -> Mapping[str, Any]:
    if flavor_policy == "resolved":
        return resolved
    if flavor_policy == "latest" or (flavor_policy == "auto" and not was_exact_url):
        latest = client.latest_english_paper_printing(str(resolved.get("name", "")))
        if latest:
            return latest
    return resolved


def build_land_colors(
    semantic: Mapping[str, Any],
    face: Mapping[str, Any],
    card: Mapping[str, Any],
    oracle_text: str,
) -> List[str]:
    if "Land" not in semantic["types"]:
        return []

    result: List[str] = []

    # Prefer basic-land subtype order: Forest Plains => G,W, etc.
    for subtype in semantic["subtypes"]:
        color = BASIC_LAND_COLORS.get(subtype)
        if color and color not in result:
            result.append(color)

    produced = face_value(face, card, "produced_mana", [])
    if isinstance(produced, list):
        for color in produced:
            if color in "WUBRG" and color not in result:
                result.append(color)

    # Fetch lands don't produce the colors themselves; infer the frame identity
    # from basic land types named by their search ability.
    for subtype, color in BASIC_LAND_COLORS.items():
        if re.search(rf"\b{re.escape(subtype)}\b", oracle_text) and color not in result:
            result.append(color)

    # Last semantic fallback: explicit colored mana symbols in land rules.
    for color in "WUBRG":
        if f"{{{color}}}" in oracle_text and color not in result:
            result.append(color)

    return result


class ScryfallArtCache:
    """Persist exact Scryfall art crops outside the project art folder."""

    MANIFEST_NAME = ".scryfall_art_cache.json"

    def __init__(self, project_dir: Path, client: ScryfallClient):
        self.project_dir = project_dir.resolve()
        self.export_dir = self.project_dir / "scryfall_art"
        try:
            self.export_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DataError(f"Could not create project Scryfall-art folder {self.export_dir}: {exc}") from exc

        self.client = client
        base_cache = client.cache_dir
        if base_cache is not None:
            self.art_dir = (base_cache / "art").resolve()
        else:
            if os.name == "nt":
                root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            else:
                root = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
            self.art_dir = (root / "MTG_Card_Pipeline_Local_UI" / "scryfall_art").resolve()
        self.art_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.art_dir / self.MANIFEST_NAME
        self.manifest: Dict[str, Any] = {}
        if self.manifest_path.is_file():
            try:
                parsed = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    self.manifest = parsed
            except (OSError, json.JSONDecodeError) as exc:
                raise DataError(f"Could not read Scryfall art cache manifest {self.manifest_path}: {exc}") from exc

    @staticmethod
    def _extension_for_url(url: str) -> str:
        suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
        return ".jpg"

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _sha256_file(path: Path) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return None

    def _save_manifest(self) -> None:
        try:
            tmp = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
            tmp.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.manifest_path)
        except OSError as exc:
            warn(f"Could not write Scryfall art cache manifest {self.manifest_path}: {exc}")

    def _has_conventional_art(self, card_name: str) -> bool:
        wanted = snake_slug(card_name)
        for p in self.art_dir.iterdir():
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if normalized_art_stem(p) == wanted:
                return True
        return False

    def _project_copy_path(self, card_name: str, source: Path) -> Path:
        # The project copy is intentionally named conventionally even when the
        # persistent cache uses a crop/version suffix. This makes scryfall_art/
        # a clean, directly usable collection of the art actually used.
        return self.export_dir / f"{snake_slug(card_name)}{source.suffix.lower()}"

    def _ensure_project_copy(self, card_name: str, source: Path, *, overwrite: bool) -> Path:
        target = self._project_copy_path(card_name, source)
        if target.is_file() and not overwrite:
            return target
        try:
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, tmp)
            os.replace(tmp, target)
        except OSError as exc:
            raise DataError(f"Could not copy Scryfall art for {card_name!r} to {target}: {exc}") from exc
        print(f"Scryfall art project copy: {card_name} -> {target}", file=sys.stderr)
        return target

    @staticmethod
    def _crop_art_bytes(data: bytes, *, top: int, bottom: int, extension: str, card_name: str) -> bytes:
        try:
            from PIL import Image
        except ImportError as exc:
            raise DataError(
                f"{card_name}: this Saga Creature Scryfall-art crop requires Pillow. "
                "Install it with: py -3 -m pip install Pillow"
            ) from exc

        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if top < 0 or bottom < 0 or top + bottom >= height:
                    raise DataError(
                        f"{card_name}: cannot trim {top}px top and {bottom}px bottom from "
                        f"a {width}x{height} Scryfall art image."
                    )
                cropped = image.crop((0, top, width, height - bottom))
                output = io.BytesIO()
                ext = extension.lower()
                if ext in {".jpg", ".jpeg"}:
                    if cropped.mode not in {"RGB", "L"}:
                        cropped = cropped.convert("RGB")
                    cropped.save(output, format="JPEG", quality=95, subsampling=0, optimize=True)
                elif ext == ".png":
                    cropped.save(output, format="PNG", optimize=True)
                elif ext == ".webp":
                    cropped.save(output, format="WEBP", quality=95, method=6)
                else:
                    raise DataError(f"{card_name}: unsupported Scryfall art extension {extension!r} for cropping.")
                return output.getvalue()
        except DataError:
            raise
        except Exception as exc:
            raise DataError(f"{card_name}: could not crop downloaded Scryfall art: {exc}") from exc

    def get_or_download(
        self,
        card_name: str,
        url: str,
        *,
        crop_top: int = 0,
        crop_bottom: int = 0,
        crop_version: str = "",
    ) -> Path:
        if not url:
            raise DataError(f"Scryfall did not provide an art_crop URL for {card_name!r}.")

        needs_crop = bool(crop_top or crop_bottom)
        key = unicodedata.normalize("NFKC", card_name).casefold()
        entry = self.manifest.get(key)
        if isinstance(entry, dict):
            filename = str(entry.get("filename") or "")
            cached_url = str(entry.get("url") or "")
            cached_sha = str(entry.get("sha256") or "")
            candidate = self.art_dir / filename if filename else None
            cached_crop_version = str(entry.get("crop_version") or "")
            crop_matches = (not needs_crop) or (cached_crop_version == crop_version)
            if candidate is not None and candidate.is_file() and cached_url == url and crop_matches:
                actual_sha = self._sha256_file(candidate)
                if actual_sha and (not cached_sha or actual_sha == cached_sha):
                    if not cached_sha:
                        entry["sha256"] = actual_sha
                        self._save_manifest()
                    print(f"Scryfall art cache: {card_name} -> {candidate.name}", file=sys.stderr)
                    # Recreate the project copy from cache if the user deleted it,
                    # without rewriting an existing local collection copy.
                    self._ensure_project_copy(card_name, candidate, overwrite=False)
                    return candidate

        ext = self._extension_for_url(url)
        base = snake_slug(card_name)
        crop_suffix = f"__crop_{crop_top}_{crop_bottom}" if needs_crop else ""
        target = self.art_dir / f"{base}{crop_suffix}{ext}"

        print(f"Downloading Scryfall art: {card_name} -> {target.name}", file=sys.stderr)
        body = self.client.fetch_binary(url)
        if needs_crop:
            body = self._crop_art_bytes(
                body,
                top=crop_top,
                bottom=crop_bottom,
                extension=target.suffix,
                card_name=card_name,
            )
            print(
                f"Cropped Scryfall art: {card_name} (-{crop_top}px top, -{crop_bottom}px bottom)",
                file=sys.stderr,
            )
        digest = self._sha256_bytes(body)
        try:
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(body)
            os.replace(tmp, target)
        except OSError as exc:
            raise DataError(f"Could not save Scryfall art for {card_name!r} to {target}: {exc}") from exc

        self.manifest[key] = {
            "filename": target.name,
            "url": url,
            "sha256": digest,
            "crop_version": crop_version if needs_crop else "",
            "crop_top": int(crop_top) if needs_crop else 0,
            "crop_bottom": int(crop_bottom) if needs_crop else 0,
        }
        self._save_manifest()
        # A fresh Scryfall fetch is authoritative, so refresh the project copy.
        # For cropped special cases this copies the post-crop art that the card
        # actually uses, under the normal card filename.
        self._ensure_project_copy(card_name, target, overwrite=True)
        return target


def find_art_file(
    project_dir: Path,
    card_name: str,
    art_map: Mapping[str, Any],
    allow_missing: bool,
) -> str:
    art_dir = project_dir / "art"
    if not art_dir.is_dir():
        raise DataError(f"Expected art folder does not exist: {art_dir}")

    files = sorted(p for p in art_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)

    mapped = art_map.get(card_name)
    if mapped:
        mapped_name = Path(str(mapped)).name
        # Windows filesystems are normally case-insensitive, while GitHub/raw URLs
        # are case-sensitive. Never return the spelling of a guessed Path object;
        # return the actual directory entry so the generated remote URL preserves
        # the filename's real capitalization.
        mapped_matches = [p for p in files if p.name.casefold() == mapped_name.casefold()]
        if len(mapped_matches) == 1:
            return mapped_matches[0].name
        if len(mapped_matches) > 1:
            raise DataError(f"Multiple art files case-insensitively match override {mapped!r}: {[p.name for p in mapped_matches]}")
        raise DataError(f"Art override for {card_name!r} does not exist in {art_dir}: {mapped!r}")

    wanted = snake_slug(card_name)

    # Exact conventional filename, but preserve the actual on-disk spelling.
    # This matters on Windows: `command_tower.png` can resolve a local file named
    # `Command_Tower.png`, but using the lowercase guess in a GitHub URL 404s.
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        wanted_name = (wanted + ext).casefold()
        matches = [p for p in files if p.name.casefold() == wanted_name]
        if len(matches) == 1:
            return matches[0].name
        if len(matches) > 1:
            raise DataError(
                f"Multiple art files case-insensitively match {card_name!r}: {[p.name for p in matches]}. "
                "Use --art-map."
            )

    # Exact normalized match, ignoring numeric face/card prefixes.
    exact = [p for p in files if normalized_art_stem(p) == wanted]
    if len(exact) == 1:
        return exact[0].name
    if len(exact) > 1:
        raise DataError(
            f"Multiple art files match {card_name!r}: {[p.name for p in exact]}. "
            "Use --art-map."
        )

    # Conservative typo-tolerant match (helps with legacy filenames like savana.png).
    stems = {normalized_art_stem(p): p for p in files}
    close = difflib.get_close_matches(wanted, list(stems), n=2, cutoff=0.90)
    if len(close) == 1:
        chosen = stems[close[0]]
        warn(f"Using close art filename match for {card_name!r}: {chosen.name}")
        return chosen.name

    expected = wanted + ".png"
    if allow_missing:
        warn(f"No local art found for {card_name!r}; writing expected filename {expected!r}.")
        return expected

    raise DataError(
        f"No unique art file found for {card_name!r} in {art_dir}. "
        f"Expected something like {expected!r}. Add the art, use --art-map, or pass --allow-missing-art."
    )


def find_github_art_file(
    card_name: str,
    art_map: Mapping[str, Any],
    remote_names: Sequence[str],
) -> Optional[str]:
    """Return the matching custom-art filename already present on GitHub.

    This is deliberately separate from the local art/ resolver.  When Scryfall
    fallback is enabled, GitHub is authoritative for deciding whether custom art
    exists; a stale/local Scryfall cache file must never accidentally win.
    """
    image_names = sorted(
        name for name in remote_names
        if Path(name).suffix.lower() in IMAGE_EXTENSIONS
    )

    mapped = art_map.get(card_name)
    if mapped:
        mapped_name = Path(str(mapped)).name
        matches = [name for name in image_names if name.casefold() == mapped_name.casefold()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise DataError(
                f"Multiple GitHub art files case-insensitively match override {mapped!r}: {matches}"
            )
        raise DataError(
            f"Art override for {card_name!r} does not exist in the GitHub art/ directory: {mapped!r}"
        )

    wanted = snake_slug(card_name)

    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        wanted_name = (wanted + ext).casefold()
        matches = [name for name in image_names if name.casefold() == wanted_name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise DataError(
                f"Multiple GitHub art files case-insensitively match {card_name!r}: {matches}. "
                "Use --art-map."
            )

    exact = [name for name in image_names if normalized_art_stem(Path(name)) == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise DataError(
            f"Multiple GitHub art files match {card_name!r}: {exact}. Use --art-map."
        )

    stems = {normalized_art_stem(Path(name)): name for name in image_names}
    close = difflib.get_close_matches(wanted, list(stems), n=2, cutoff=0.90)
    if len(close) == 1:
        chosen = stems[close[0]]
        warn(f"Using close GitHub art filename match for {card_name!r}: {chosen}")
        return chosen

    return None


def validate_set_symbol(project_dir: Path, rarity: str, allow_missing: bool) -> None:
    symbol_dir = project_dir / "set_symbol"
    if not symbol_dir.is_dir():
        raise DataError(f"Expected set_symbol folder does not exist: {symbol_dir}")
    expected = symbol_dir / f"{rarity}.png"
    if expected.is_file():
        return
    if allow_missing:
        warn(f"Missing set symbol {expected}")
        return
    raise DataError(
        f"Missing expected rarity symbol: {expected}. "
        "The project should contain common.png, uncommon.png, rare.png, and mythic.png."
    )


def override_lookup(mapping: Mapping[str, Any], face_name: str, parent_name: str) -> Any:
    if face_name in mapping:
        return mapping[face_name]
    if parent_name in mapping:
        return mapping[parent_name]
    return None


def scryfall_art_crop_url(card: Mapping[str, Any], face: Mapping[str, Any]) -> str:
    """Return Scryfall's raw art crop for this physical face when available."""
    for source in (face, card):
        image_uris = source.get("image_uris") if isinstance(source, Mapping) else None
        if isinstance(image_uris, Mapping):
            value = image_uris.get("art_crop")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def build_face_record(
    card: Mapping[str, Any],
    face: Mapping[str, Any],
    flavor_face: Mapping[str, Any],
    index: int,
    face_count: int,
    project_dir: Path,
    flavor_overrides: Mapping[str, Any],
    rarity_overrides: Mapping[str, Any],
    art_map: Mapping[str, Any],
    allow_missing_art: bool,
    allow_missing_symbols: bool,
    use_scryfall_art: bool = False,
    scryfall_art_cache: Optional[ScryfallArtCache] = None,
    remote_art_names: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    parent_name = str(card.get("name", ""))
    name = str(face_value(face, card, "name", parent_name))
    type_line = str(face_value(face, card, "type_line", ""))
    semantic = split_type_line(type_line)

    mana_cost = str(face_value(face, card, "mana_cost", ""))
    oracle_text = str(face_value(face, card, "oracle_text", ""))
    raw_colors = face_value(face, card, "colors", [])
    colors = [c for c in raw_colors if c in "WUBRG"] if isinstance(raw_colors, list) else []

    flavor_default = face_value(flavor_face, card, "flavor_text", "")
    flavor_override = override_lookup(flavor_overrides, name, parent_name)
    flavor_text = str(flavor_override if flavor_override is not None else (flavor_default or ""))

    rarity_override = override_lookup(rarity_overrides, name, parent_name)
    rarity = str(rarity_override if rarity_override is not None else card.get("rarity", "")).lower()
    if rarity not in RARITIES:
        raise DataError(
            f"{name}: Scryfall rarity {rarity!r} has no standard project set-symbol file. "
            "Supply a common/uncommon/rare/mythic rarity override."
        )
    validate_set_symbol(project_dir, rarity, allow_missing_symbols)

    local_art_path: Optional[Path] = None

    # Custom GitHub art always gets first refusal.  --use-scryfall-art now means
    # "use Scryfall when custom GitHub art is absent", not "ignore custom art".
    # This lookup intentionally uses the remote GitHub directory rather than the
    # local art/ directory so an old Scryfall cache file cannot masquerade as
    # current custom art.
    github_art_filename: Optional[str] = None
    if use_scryfall_art:
        if remote_art_names is None:
            raise DataError("Internal error: GitHub art listing was not initialized.")
        github_art_filename = find_github_art_file(name, art_map, remote_art_names)

    if github_art_filename:
        art_value = github_art_filename
        print(f"Art source: {name}: custom GitHub art ({github_art_filename})", file=sys.stderr)
        # Do not use a same-named local file for auto-fit in mixed mode: older
        # releases could have put Scryfall pixels in that slot.  Let the compiler
        # read the authoritative GitHub URL so sizing matches the custom image.
    elif use_scryfall_art:
        art_url = scryfall_art_crop_url(card, face)
        if not art_url:
            raise DataError(f"Scryfall did not provide an art_crop URL for {name!r}.")
        if scryfall_art_cache is None:
            raise DataError("Internal error: --use-scryfall-art requires an initialized local art cache.")

        trailing_saga_rules = saga_creature_trailing_rules_text(type_line, oracle_text)
        if trailing_saga_rules:
            local_art_path = scryfall_art_cache.get_or_download(
                name,
                art_url,
                crop_top=SAGA_CREATURE_RULES_ART_TRIM_TOP,
                crop_bottom=SAGA_CREATURE_RULES_ART_TRIM_BOTTOM,
                crop_version=SAGA_CREATURE_RULES_ART_TRIM_VERSION,
            )
            # The cropped bytes are intentionally embedded for the current build.
            # Leaving artSource pointed at Scryfall's original art_crop would
            # discard the post-download trim while only auto-fit used the local file.
            art_value = image_file_data_uri(local_art_path)
        else:
            local_art_path = scryfall_art_cache.get_or_download(name, art_url)
            art_value = art_url
        print(f"Art source: {name}: Scryfall fallback", file=sys.stderr)
    else:
        art_filename = find_art_file(project_dir, name, art_map, allow_missing_art)
        art_value = art_filename
        local_art_path = project_dir / "art" / art_filename

    record: Dict[str, Any] = {
        "name": name,
        "mana_cost": mana_cost,
        "types": semantic["types"],
        "subtypes": semantic["subtypes"],
        "legendary": semantic["legendary"],
        "basic": semantic["basic"],
        "snow": semantic["snow"],
        "oracle_text": oracle_text,
        "colors": colors,
        "art": art_value,
        "rarity": rarity,
    }
    if local_art_path is not None:
        record["art_local_path"] = str(local_art_path.resolve())

    if semantic["world"]:
        record["world"] = True
    if flavor_text:
        record["flavor_text"] = flavor_text

    power = face_value(face, card, "power", None)
    toughness = face_value(face, card, "toughness", None)
    if power is not None or toughness is not None:
        if power is None or toughness is None:
            raise DataError(f"{name}: Scryfall supplied only one of power/toughness.")
        record["power"] = str(power)
        record["toughness"] = str(toughness)

    loyalty = face_value(face, card, "loyalty", None)
    if loyalty is not None:
        record["loyalty"] = str(loyalty)
    defense = face_value(face, card, "defense", None)
    if defense is not None:
        record["defense"] = str(defense)

    land_colors = build_land_colors(semantic, face, card, oracle_text)
    if land_colors:
        record["land_colors"] = land_colors

    # Multi-face relationship is semantic/source metadata, not visual layout data.
    # The Card Conjurer compiler may still reject a DFC layout it has not learned.
    if face_count > 1:
        record["parent_name"] = parent_name
        record["face_index"] = index
        scryfall_layout = card.get("layout")
        if scryfall_layout:
            record["scryfall_layout"] = str(scryfall_layout)

    # Intentionally NO `layout` key here. Layout is an optional manual override
    # for the Card Conjurer compiler and should not be invented by ingestion.
    return record


def select_matching_flavor_face(
    flavor_card: Mapping[str, Any],
    target_face: Mapping[str, Any],
    index: int,
) -> Mapping[str, Any]:
    faces = face_list(flavor_card)
    target_name = str(target_face.get("name", ""))
    for candidate in faces:
        if str(candidate.get("name", "")) == target_name:
            return candidate
    if index < len(faces):
        return faces[index]
    return flavor_card


def raw_base(repo: str, branch: str, repo_project_path: str, child: str) -> str:
    repo_project_path = repo_project_path.strip("/")
    components = [urllib.parse.quote(part) for part in repo_project_path.split("/") if part]
    components.append(urllib.parse.quote(child))
    suffix = "/".join(components)
    return f"https://raw.githubusercontent.com/{repo}/{urllib.parse.quote(branch, safe='')}/{suffix}/"


def github_directory_filenames(repo: str, branch: str, repo_project_path: str, child: str) -> List[str]:
    """Return exact filenames currently present in one GitHub repo directory.

    Custom/local project art is emitted into Card Conjurer as raw GitHub URLs,
    so compilation is only valid if those exact case-sensitive filenames
    already exist remotely. Validate the directory once rather than issuing a
    request for every card image.
    """
    repo_project_path = repo_project_path.strip("/")
    path_parts = [part for part in repo_project_path.split("/") if part] + [child]
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path_parts)
    owner_repo = "/".join(urllib.parse.quote(part, safe="") for part in repo.split("/", 1))
    if "/" not in repo:
        raise DataError(f"GitHub repo must be owner/name, got {repo!r}")
    url = (
        f"https://api.github.com/repos/{owner_repo}/contents/{encoded_path}"
        f"?ref={urllib.parse.quote(branch, safe='')}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CardDataInputBuilder/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = str(payload.get("message") or "")
        except Exception:
            pass
        suffix = f": {detail}" if detail else ""
        raise DataError(
            f"Could not verify GitHub art directory {repo}/{repo_project_path}/{child} "
            f"on branch {branch!r}: GitHub HTTP {exc.code}{suffix}"
        ) from exc
    except urllib.error.URLError as exc:
        raise DataError(f"Could not verify GitHub art directory: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataError(f"GitHub returned invalid JSON while verifying art directory: {exc}") from exc
    if not isinstance(payload, list):
        raise DataError(
            f"GitHub path {repo}/{repo_project_path}/{child} is not a directory or could not be listed."
        )
    out=[]
    for item in payload:
        if isinstance(item, Mapping) and item.get("type") == "file" and isinstance(item.get("name"), str):
            out.append(item["name"])
    return out


def validate_remote_art_files(
    cards: Sequence[Mapping[str, Any]],
    repo: str,
    branch: str,
    repo_project_path: str,
    *,
    allow_missing: bool,
) -> None:
    """Fail before compilation if custom art would resolve to missing GitHub URLs."""
    remote_names = github_directory_filenames(repo, branch, repo_project_path, "art")
    remote_exact = set(remote_names)
    remote_casefold = {}
    for name in remote_names:
        remote_casefold.setdefault(name.casefold(), []).append(name)

    missing=[]
    case_mismatches=[]
    for card in cards:
        art = str(card.get("art") or "").strip()
        if not art or art.startswith("data:") or re.match(r"^https?://", art, re.I):
            continue
        filename = Path(art).name
        if filename in remote_exact:
            continue
        alternatives = remote_casefold.get(filename.casefold()) or []
        if alternatives:
            case_mismatches.append((str(card.get("name") or "<unnamed>"), filename, alternatives))
        else:
            missing.append((str(card.get("name") or "<unnamed>"), filename))

    if not missing and not case_mismatches:
        return

    details=[]
    if missing:
        preview=", ".join(f"{card}: {filename}" for card,filename in missing[:12])
        if len(missing)>12:
            preview += f", ... (+{len(missing)-12} more)"
        details.append(f"missing from GitHub art/: {preview}")
    if case_mismatches:
        preview=", ".join(
            f"{card}: local {filename!r}, GitHub has {alts}" for card,filename,alts in case_mismatches[:8]
        )
        if len(case_mismatches)>8:
            preview += f", ... (+{len(case_mismatches)-8} more)"
        details.append(f"case-sensitive filename mismatch: {preview}")
    message = "GitHub art validation failed; Card Conjurer would not be able to load the generated artSource URLs. " + "; ".join(details)
    if allow_missing:
        warn(message)
        return
    raise DataError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Look up cards on Scryfall and write semantic JSON for card_data_to_cardconjurer.py."
    )
    parser.add_argument("sources", nargs="*", help="Exact card names or Scryfall card URLs")
    parser.add_argument("--list", dest="list_file", type=Path, help="Text file of card names/Scryfall URLs")
    parser.add_argument("--project", required=True, type=Path, help="Local project folder containing art/ and set_symbol/")
    parser.add_argument(
        "--repo-project-path",
        help="Path of that project inside the GitHub repo; defaults to --project as written",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repo (default: {DEFAULT_REPO})")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help=f"GitHub branch (default: {DEFAULT_BRANCH})")
    parser.add_argument("--artist", default="ChatGPT")
    parser.add_argument("-o", "--output", type=Path, default=Path("card_data.json"))
    parser.add_argument("--flavor-overrides", type=Path, help="JSON object: card/face name -> custom flavor text")
    parser.add_argument("--rarity-overrides", type=Path, help="JSON object: card/face name -> common/uncommon/rare/mythic")
    parser.add_argument("--art-map", type=Path, help="JSON object: card/face name -> filename inside art/")
    parser.add_argument("--use-scryfall-art", action="store_true", help="Prefer custom art already present in GitHub art/; use Scryfall art_crop only as a fallback, caching downloaded Scryfall art separately.")
    parser.add_argument(
        "--flavor-policy",
        choices=("auto", "resolved", "latest"),
        default="auto",
        help=(
            "auto: exact Scryfall URL uses that printing; name input uses newest English paper printing. "
            "resolved: always use resolved printing. latest: always seek newest English paper printing."
        ),
    )
    parser.add_argument("--fuzzy", action="store_true", help="Allow fuzzy-name fallback when exact Scryfall name lookup fails")
    parser.add_argument("--allow-missing-art", action="store_true", help="Write expected art filename instead of failing if art is absent")
    parser.add_argument("--allow-missing-symbols", action="store_true", help="Warn instead of failing if rarity symbol file is absent")
    parser.add_argument("--request-delay", type=float, default=DEFAULT_DELAY, help="Minimum seconds between Scryfall API requests")
    parser.add_argument("--scryfall-cache-dir", type=Path, help="Persistent read-through cache for per-card Scryfall JSON responses")
    parser.add_argument("--refresh-card-data", action="store_true", help="Refresh cached Scryfall card data only when the cached response is at least 7 days old")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        sources: List[str] = list(args.sources)
        if args.list_file:
            sources.extend(read_sources_from_file(args.list_file))
        if not sources:
            raise DataError("Provide at least one card name/Scryfall URL or --list file.")

        project_dir = args.project.resolve()
        if not project_dir.is_dir():
            raise DataError(f"Project folder does not exist: {project_dir}")
        if not (project_dir / "art").is_dir():
            raise DataError(f"Expected project art folder: {project_dir / 'art'}")
        if not (project_dir / "set_symbol").is_dir():
            raise DataError(f"Expected project set_symbol folder: {project_dir / 'set_symbol'}")

        flavor_overrides = load_json_object(args.flavor_overrides, "flavor overrides")
        rarity_overrides = load_json_object(args.rarity_overrides, "rarity overrides")
        art_map = load_json_object(args.art_map, "art map")

        client = ScryfallClient(
            delay=args.request_delay,
            cache_dir=args.scryfall_cache_dir,
            refresh_card_data=args.refresh_card_data,
        )
        scryfall_art_cache = ScryfallArtCache(project_dir, client) if args.use_scryfall_art else None
        repo_project_path = args.repo_project_path or args.project.as_posix().strip("./")
        remote_art_names: Optional[List[str]] = None
        if args.use_scryfall_art:
            print(
                f"GitHub-first art check: {args.repo}/{repo_project_path}/art @ {args.branch}",
                file=sys.stderr,
            )
            remote_art_names = github_directory_filenames(
                args.repo, args.branch, repo_project_path, "art"
            )
        output_cards: List[Dict[str, Any]] = []

        for source in sources:
            print(f"Scryfall: {source}", file=sys.stderr)
            resolved, was_exact_url = resolve_source(client, source, fuzzy=args.fuzzy)
            flavor_card = choose_flavor_source(client, resolved, was_exact_url, args.flavor_policy)

            faces = face_list(resolved)
            # Prepared cards contain a spell nested inside one physical host card.
            # Keep that relationship semantic so the compiler can render one
            # physical card instead of incorrectly emitting the prepared spell as
            # a second card in the batch.
            if str(resolved.get("layout", "")) == "prepare":
                if len(faces) != 2:
                    raise DataError(
                        f"{resolved.get('name','<unnamed>')}: prepare layout needs exactly two Scryfall faces"
                    )
                host_face, spell_face = faces
                host_flavor = select_matching_flavor_face(flavor_card, host_face, 0)
                host = build_face_record(
                    resolved, host_face, host_flavor, index=0, face_count=1,
                    project_dir=project_dir, flavor_overrides=flavor_overrides,
                    rarity_overrides=rarity_overrides, art_map=art_map,
                    allow_missing_art=args.allow_missing_art,
                    allow_missing_symbols=args.allow_missing_symbols,
                    use_scryfall_art=args.use_scryfall_art,
                    scryfall_art_cache=scryfall_art_cache,
                    remote_art_names=remote_art_names,
                )
                host["scryfall_layout"] = "prepare"
                spell_semantic = split_type_line(str(spell_face.get("type_line") or resolved.get("type_line") or ""))
                host["prepared_spell"] = {
                    "name": str(spell_face.get("name") or "").strip(),
                    "mana_cost": str(spell_face.get("mana_cost") or ""),
                    "types": spell_semantic["types"],
                    "subtypes": spell_semantic["subtypes"],
                    "legendary": spell_semantic["legendary"],
                    "basic": spell_semantic["basic"],
                    "snow": spell_semantic["snow"],
                    "oracle_text": str(spell_face.get("oracle_text") or ""),
                    "colors": list(spell_face.get("colors") or []),
                }
                if spell_semantic["world"]:
                    host["prepared_spell"]["world"] = True
                output_cards.append(host)
            else:
                for i, face in enumerate(faces):
                    flavor_face = select_matching_flavor_face(flavor_card, face, i)
                    output_cards.append(
                        build_face_record(
                            resolved,
                            face,
                            flavor_face,
                            index=i,
                            face_count=len(faces),
                            project_dir=project_dir,
                            flavor_overrides=flavor_overrides,
                            rarity_overrides=rarity_overrides,
                            art_map=art_map,
                            allow_missing_art=args.allow_missing_art,
                            allow_missing_symbols=args.allow_missing_symbols,
                            use_scryfall_art=args.use_scryfall_art,
                            scryfall_art_cache=scryfall_art_cache,
                            remote_art_names=remote_art_names,
                        )
                    )

        names = [c["name"] for c in output_cards]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise DataError(
                f"Duplicate output card/face names: {duplicates}. "
                "Disambiguate the source list before compiling."
            )

        if not args.use_scryfall_art:
            print(
                f"GitHub art check: {args.repo}/{repo_project_path}/art @ {args.branch}",
                file=sys.stderr,
            )
            validate_remote_art_files(
                output_cards,
                args.repo,
                args.branch,
                repo_project_path,
                allow_missing=args.allow_missing_art,
            )

        document = {
            "schema_version": 2,
            "defaults": {
                "repo": args.repo,
                "branch": args.branch,
                "artist": args.artist,
                "art_base_url": raw_base(args.repo, args.branch, repo_project_path, "art"),
                # Set symbols are authoritative local project assets.  Record
                # the absolute directory so the compiler can embed the PNG
                # directly into the .cardconjurer instead of depending on the
                # project already existing on GitHub.
                "set_symbol_local_dir": str((project_dir / "set_symbol").resolve()),
                # Keep the old remote base as a backwards-compatible fallback
                # for semantic JSON created by older/manual workflows.
                "set_symbol_base_url": raw_base(
                    args.repo, args.branch, repo_project_path, "set_symbol"
                ),
            },
            "cards": output_cards,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(output_cards)} card face(s) to {args.output}")
        return 0

    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
