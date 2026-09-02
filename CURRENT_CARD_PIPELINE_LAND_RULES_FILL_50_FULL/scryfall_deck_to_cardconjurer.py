#!/usr/bin/env python3
"""
scryfall_deck_to_cardconjurer.py

One-command pipeline:

    Scryfall deck URL
        -> Scryfall deck JSON export
        -> semantic card-data JSON
        -> final .cardconjurer file

This wrapper intentionally delegates the two real jobs to:
    scryfall_to_card_data.py
    card_data_to_cardconjurer.py

That keeps the architecture clean:
- ingestion script owns Scryfall/source-data logic;
- compiler owns all Card Conjurer visual/layout logic;
- this script only orchestrates a whole Scryfall deck.

Typical usage from the repository root:

    python scryfall_deck_to_cardconjurer.py \
      "https://scryfall.com/@andro951/decks/cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d" \
      --project derevi

If you run it from inside a project directory that already contains art/ and
set_symbol/, --project can be omitted:

    cd derevi
    python ../scryfall_deck_to_cardconjurer.py \
      "https://scryfall.com/@andro951/decks/cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d"

No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DEFAULT_REPO = "andro951/cards"
DEFAULT_BRANCH = "main"
USER_AGENT = "CardDataDeckPipeline/1.0"
ACCEPT = "application/json;q=0.9,*/*;q=0.8"

PREFERRED_SECTION_ORDER = (
    "commander",
    "commanders",
    "partner",
    "companion",
    "mainboard",
    "sideboard",
    "maybeboard",
)


class PipelineError(RuntimeError):
    pass


def snake_slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("Æ", "AE").replace("æ", "ae")
    text = text.replace("Œ", "OE").replace("œ", "oe")
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()


def extract_deck_uuid(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise PipelineError(f"Invalid URL: {url}") from exc

    if parsed.netloc.lower() not in {"scryfall.com", "www.scryfall.com"}:
        raise PipelineError("Deck URL must be on scryfall.com.")

    match = re.search(
        r"/decks/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:/|$)",
        parsed.path,
    )
    if not match:
        raise PipelineError(
            "Could not find a Scryfall deck UUID in the URL. "
            "Expected a URL like https://scryfall.com/@user/decks/<uuid>"
        )
    return match.group(1).lower()


def get_json(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": ACCEPT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            if isinstance(payload, dict):
                detail = str(payload.get("details") or payload.get("code") or "")
        except Exception:
            pass
        suffix = f": {detail}" if detail else ""
        raise PipelineError(f"HTTP {exc.code} while fetching {url}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise PipelineError(f"Could not reach Scryfall: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Scryfall returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise PipelineError("Unexpected Scryfall deck-export response.")
    if parsed.get("object") == "error":
        raise PipelineError(str(parsed.get("details") or parsed))
    return parsed


def deck_export_url(deck_uuid: str) -> str:
    return f"https://api.scryfall.com/decks/{deck_uuid}/export/json"


def fetch_deck_export(deck_url: str) -> Dict[str, Any]:
    uuid = extract_deck_uuid(deck_url)
    return get_json(deck_export_url(uuid))


def section_names(entries: Mapping[str, Any]) -> List[str]:
    names = list(entries.keys())
    ordered: List[str] = []
    lowered = {str(name).lower(): name for name in names}

    for preferred in PREFERRED_SECTION_ORDER:
        if preferred in lowered:
            original = lowered[preferred]
            if original not in ordered:
                ordered.append(original)

    for name in names:
        if name not in ordered:
            ordered.append(name)

    return ordered


def extract_card_sources(
    deck: Mapping[str, Any],
    include_maybeboard: bool = False,
    include_sections: Optional[Sequence[str]] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Return exact Scryfall card API URLs plus a small manifest.

    Scryfall deck export entries contain a card_digest with an exact Scryfall
    card UUID. We preserve that exact selected printing for rarity/identity, and
    the ingestion step can separately request latest flavor text.
    """
    entries = deck.get("entries")
    if not isinstance(entries, dict):
        raise PipelineError(
            "Deck export has no entries object. Scryfall's deck-export format "
            "may have changed; update this parser instead of guessing."
        )

    requested = {s.lower() for s in include_sections} if include_sections else None
    excluded_default_sections = {"maybeboard", "sideboard", "outside", "outside the game"}

    sources: List[str] = []
    manifest: List[Dict[str, Any]] = []
    seen_ids = set()

    for section in section_names(entries):
        section_l = str(section).lower()

        if requested is not None and section_l not in requested:
            continue
        if requested is None:
            if section_l in {"sideboard", "outside", "outside the game"}:
                continue
            if section_l == "maybeboard" and not include_maybeboard:
                continue

        rows = entries.get(section)
        if not isinstance(rows, list):
            raise PipelineError(f"Deck section {section!r} is not an array.")

        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("found") is False:
                raw_text=str(row.get("raw_text") or "").strip()
                digest=row.get("card_digest")
                # Scryfall deck exports can contain blank placeholder cells in
                # column layouts. Ignore only truly blank unresolved rows.
                if not raw_text and not isinstance(digest, dict):
                    continue
                raise PipelineError(
                    f"Scryfall deck contains an unresolved entry: {row.get('raw_text')!r}"
                )

            digest = row.get("card_digest")
            if not isinstance(digest, dict):
                raw_text=str(row.get("raw_text") or "").strip()
                if not raw_text:
                    continue
                raise PipelineError(
                    f"Deck entry has no card_digest: {row.get('raw_text')!r}"
                )

            card_id = str(digest.get("id") or "").strip()
            name = str(digest.get("name") or "").strip()
            if not card_id:
                raise PipelineError(f"Deck entry {name or row.get('raw_text')!r} has no Scryfall card id.")

            count = row.get("count", 1)
            try:
                count_i = int(count)
            except (TypeError, ValueError):
                count_i = 1

            manifest.append(
                {
                    "section": str(section),
                    "count": count_i,
                    "name": name,
                    "scryfall_id": card_id,
                    "set": digest.get("set"),
                    "collector_number": digest.get("collector_number"),
                }
            )

            # A Card Conjurer batch needs one card definition per unique printing,
            # not N duplicate definitions for quantity N.
            if card_id in seen_ids:
                continue
            seen_ids.add(card_id)
            sources.append(f"https://api.scryfall.com/cards/{card_id}")

    if not sources:
        raise PipelineError("No usable cards were found in the selected deck sections.")

    return sources, manifest


def looks_like_project(path: Path) -> bool:
    return (path / "art").is_dir() and (path / "set_symbol").is_dir()


def deck_title_candidates(deck: Mapping[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("name", "title", "deck_name"):
        value = deck.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    candidates: List[str] = []
    for value in values:
        variants = [
            value,
            re.sub(r"^\s*proxy\s+", "", value, flags=re.I),
            re.sub(r"\s+proxy\s*$", "", value, flags=re.I),
        ]
        for variant in variants:
            slug = snake_slug(variant)
            if slug and slug not in candidates:
                candidates.append(slug)
    return candidates


def resolve_project_dir(
    explicit: Optional[Path],
    deck: Mapping[str, Any],
    cwd: Path,
) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not looks_like_project(path):
            raise PipelineError(
                f"{path} is not a project folder with both art/ and set_symbol/."
            )
        return path

    if looks_like_project(cwd):
        return cwd

    for slug in deck_title_candidates(deck):
        candidate = cwd / slug
        if looks_like_project(candidate):
            print(f"Inferred project folder: {candidate}", file=sys.stderr)
            return candidate.resolve()

    raise PipelineError(
        "Could not infer the project folder. Run from inside a project directory "
        "that contains art/ and set_symbol/, or pass --project <folder>."
    )


def infer_repo_project_path(project_dir: Path, cwd: Path, explicit: Optional[str]) -> str:
    if explicit:
        return explicit.strip("/")

    try:
        rel = project_dir.relative_to(cwd.resolve())
        if rel == Path("."):
            return project_dir.name
        return rel.as_posix()
    except ValueError:
        return project_dir.name


def find_companion_script(name: str, explicit: Optional[Path]) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
    else:
        path = Path(__file__).resolve().with_name(name)

    if not path.is_file():
        raise PipelineError(f"Required companion script not found: {path}")
    return path


def run_checked(cmd: List[str], label: str) -> None:
    print(f"\n== {label} ==", file=sys.stderr)
    print(" ".join(str(x) for x in cmd), file=sys.stderr)
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise PipelineError(f"{label} failed with exit code {proc.returncode}.")


def write_manifest(path: Path, deck_url: str, manifest: List[Dict[str, Any]]) -> None:
    document = {
        "source_deck_url": deck_url,
        "entries": manifest,
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Turn a public Scryfall deck URL into semantic card-data JSON and, "
            "by default, a final .cardconjurer batch."
        )
    )
    p.add_argument("deck_url", help="Public Scryfall deck URL")
    p.add_argument(
        "--project",
        type=Path,
        help=(
            "Local project folder containing art/ and set_symbol/. "
            "Optional when running from inside the project directory."
        ),
    )
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--branch", default=DEFAULT_BRANCH)
    p.add_argument(
        "--repo-project-path",
        help="Path of the project inside the GitHub repo; normally inferred from --project.",
    )

    p.add_argument(
        "--output-data",
        type=Path,
        help="Semantic JSON output. Default: generated_<project>_card_data.json in current directory.",
    )
    p.add_argument(
        "--output-cardconjurer",
        type=Path,
        help="Final output. Default: generated_<project>_cards.cardconjurer in current directory.",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        help="Optional file recording Scryfall deck sections/counts/selected printings.",
    )

    p.add_argument(
        "--include-maybeboard",
        action="store_true",
        help="Include Scryfall maybeboard entries. Excluded by default.",
    )
    p.add_argument(
        "--section",
        action="append",
        dest="sections",
        help=(
            "Only include this deck section. May be repeated. "
            "When omitted, all sections except maybeboard are included."
        ),
    )

    p.add_argument("--flavor-overrides", type=Path)
    p.add_argument("--rarity-overrides", type=Path)
    p.add_argument("--art-map", type=Path)
    p.add_argument(
        "--flavor-policy",
        choices=("latest", "resolved", "auto"),
        default="latest",
        help=(
            "Default 'latest': use newest English paper flavor text while preserving "
            "the deck's selected printing for rarity. Custom flavor overrides always win."
        ),
    )

    p.add_argument("--allow-missing-art", action="store_true")
    p.add_argument("--allow-missing-symbols", action="store_true")
    p.add_argument("--request-delay", type=float, default=0.25)

    p.add_argument(
        "--no-compile",
        action="store_true",
        help="Stop after creating semantic card-data JSON.",
    )
    p.add_argument(
        "--no-auto-fit",
        action="store_true",
        help="Pass --no-auto-fit to the Card Conjurer compiler.",
    )

    p.add_argument("--source-script", type=Path, help="Path to scryfall_to_card_data.py")
    p.add_argument("--compiler-script", type=Path, help="Path to card_data_to_cardconjurer.py")

    # Offline/reproducible debugging hook.
    p.add_argument(
        "--deck-json",
        type=Path,
        help="Read an already-downloaded Scryfall deck export JSON instead of fetching it.",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    cwd = Path.cwd().resolve()

    try:
        deck_uuid = extract_deck_uuid(args.deck_url)
        export_url = deck_export_url(deck_uuid)
        print(f"Scryfall deck UUID: {deck_uuid}", file=sys.stderr)
        print(f"Deck export: {export_url}", file=sys.stderr)

        if args.deck_json:
            try:
                deck = json.loads(args.deck_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"Could not read --deck-json: {exc}") from exc
            if not isinstance(deck, dict):
                raise PipelineError("--deck-json must contain one Scryfall deck-export JSON object.")
        else:
            deck = fetch_deck_export(args.deck_url)

        project_dir = resolve_project_dir(args.project, deck, cwd)
        repo_project_path = infer_repo_project_path(
            project_dir, cwd, args.repo_project_path
        )

        sources, manifest = extract_card_sources(
            deck,
            include_maybeboard=args.include_maybeboard,
            include_sections=args.sections,
        )

        project_name = project_dir.name
        data_out = (args.output_data or (cwd / f"generated_{project_name}_card_data.json")).resolve()
        cc_out = (
            args.output_cardconjurer
            or (cwd / f"generated_{project_name}_cards.cardconjurer")
        ).resolve()

        source_script = find_companion_script(
            "scryfall_to_card_data.py", args.source_script
        )
        compiler_script = find_companion_script(
            "card_data_to_cardconjurer.py", args.compiler_script
        )

        data_out.parent.mkdir(parents=True, exist_ok=True)
        cc_out.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            prefix="scryfall_deck_sources_",
            delete=False,
        ) as tmp:
            source_list_path = Path(tmp.name)
            for source in sources:
                tmp.write(source + "\n")

        try:
            ingest_cmd = [
                sys.executable,
                str(source_script),
                "--project",
                str(project_dir),
                "--repo-project-path",
                repo_project_path,
                "--repo",
                args.repo,
                "--branch",
                args.branch,
                "--list",
                str(source_list_path),
                "--flavor-policy",
                args.flavor_policy,
                "--request-delay",
                str(args.request_delay),
                "-o",
                str(data_out),
            ]

            if args.flavor_overrides:
                ingest_cmd += ["--flavor-overrides", str(args.flavor_overrides)]
            if args.rarity_overrides:
                ingest_cmd += ["--rarity-overrides", str(args.rarity_overrides)]
            if args.art_map:
                ingest_cmd += ["--art-map", str(args.art_map)]
            if args.allow_missing_art:
                ingest_cmd.append("--allow-missing-art")
            if args.allow_missing_symbols:
                ingest_cmd.append("--allow-missing-symbols")

            run_checked(ingest_cmd, "Build semantic card data")

            if args.manifest:
                args.manifest.parent.mkdir(parents=True, exist_ok=True)
                write_manifest(args.manifest, args.deck_url, manifest)

            if args.no_compile:
                print(
                    f"\nDone: {len(sources)} unique printing(s) -> {data_out}",
                    file=sys.stderr,
                )
                return 0

            compile_cmd = [
                sys.executable,
                str(compiler_script),
                str(data_out),
                "-o",
                str(cc_out),
            ]
            if args.no_auto_fit:
                compile_cmd.append("--no-auto-fit")

            run_checked(compile_cmd, "Compile Card Conjurer batch")

        finally:
            try:
                source_list_path.unlink()
            except OSError:
                pass

        print(
            f"\nComplete.\n"
            f"  Deck entries: {len(manifest)}\n"
            f"  Unique selected printings: {len(sources)}\n"
            f"  Semantic JSON: {data_out}\n"
            f"  Card Conjurer: {cc_out}",
            file=sys.stderr,
        )
        return 0

    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
