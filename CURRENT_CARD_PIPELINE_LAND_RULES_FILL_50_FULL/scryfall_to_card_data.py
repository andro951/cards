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

No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
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
DEFAULT_DELAY = 0.125  # 8 req/sec; below Scryfall's requested <10 req/sec.

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
    def __init__(self, delay: float = DEFAULT_DELAY, user_agent: str = "CardDataInputBuilder/1.0"):
        self.delay = max(delay, 0.11)
        self.user_agent = user_agent
        self._last_request = 0.0

    def _wait(self) -> None:
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)

    def get_json(self, url: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        if params:
            encoded = urllib.parse.urlencode(params, doseq=True)
            url = url + ("&" if "?" in url else "?") + encoded

        self._wait()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json;q=0.9,*/*;q=0.8",
            },
        )
        try:
            cache_dir=os.environ.get("SCRYFALL_HTTP_CACHE")
            if cache_dir:
                import hashlib
                cache_path=Path(cache_dir) / hashlib.sha256(url.encode("utf-8")).hexdigest()
                if not cache_path.is_file():
                    raise DataError(f"Scryfall cache miss for {url}")
                body=cache_path.read_text(encoding="utf-8")
            else:
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = response.read().decode("utf-8")
            self._last_request = time.monotonic()
            parsed = json.loads(body)
        except urllib.error.HTTPError as exc:
            self._last_request = time.monotonic()
            detail = ""
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = payload.get("details") or payload.get("code") or ""
            except Exception:
                pass
            suffix = f": {detail}" if detail else ""
            raise DataError(f"Scryfall HTTP {exc.code} for {url}{suffix}") from exc
        except urllib.error.URLError as exc:
            self._last_request = time.monotonic()
            raise DataError(f"Could not contact Scryfall: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DataError(f"Scryfall returned invalid JSON for {url}: {exc}") from exc

        if not isinstance(parsed, dict):
            raise DataError(f"Unexpected Scryfall response for {url}")
        if parsed.get("object") == "error":
            raise DataError(f"Scryfall error: {parsed.get('details', parsed)}")
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


def find_art_file(
    project_dir: Path,
    card_name: str,
    art_map: Mapping[str, Any],
    allow_missing: bool,
) -> str:
    art_dir = project_dir / "art"
    if not art_dir.is_dir():
        raise DataError(f"Expected art folder does not exist: {art_dir}")

    mapped = art_map.get(card_name)
    if mapped:
        candidate = art_dir / str(mapped)
        if not candidate.is_file():
            raise DataError(f"Art override for {card_name!r} does not exist: {candidate}")
        return candidate.name

    files = sorted(p for p in art_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    wanted = snake_slug(card_name)

    # Exact conventional filename.
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = art_dir / (wanted + ext)
        if candidate.is_file():
            return candidate.name

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
        "art": find_art_file(project_dir, name, art_map, allow_missing_art),
        "rarity": rarity,
    }

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

        client = ScryfallClient(delay=args.request_delay)
        output_cards: List[Dict[str, Any]] = []

        for source in sources:
            print(f"Scryfall: {source}", file=sys.stderr)
            resolved, was_exact_url = resolve_source(client, source, fuzzy=args.fuzzy)
            flavor_card = choose_flavor_source(client, resolved, was_exact_url, args.flavor_policy)

            faces = face_list(resolved)
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
                    )
                )

        names = [c["name"] for c in output_cards]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise DataError(
                f"Duplicate output card/face names: {duplicates}. "
                "Disambiguate the source list before compiling."
            )

        repo_project_path = args.repo_project_path or args.project.as_posix().strip("./")
        document = {
            "schema_version": 2,
            "defaults": {
                "repo": args.repo,
                "branch": args.branch,
                "artist": args.artist,
                "art_base_url": raw_base(args.repo, args.branch, repo_project_path, "art"),
                "set_symbol_base_url": raw_base(
                    args.repo, args.branch, repo_project_path,
                    "set_icon" if (project_dir / "set_icon").is_dir() else "set_symbol"
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
