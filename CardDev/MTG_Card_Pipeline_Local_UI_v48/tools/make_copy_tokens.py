#!/usr/bin/env python3
"""
make_copy_tokens.py

Create token-frame copy cards from an existing Card Conjurer JSON file.

Primary use cases:
- Helm of the Host style nonlegendary copies.
- Preston, the Vanisher style copy tokens, including creature-subtype replacement
  (for example replacing the copied creature types with Illusion) while keeping
  the rest of the type line intact.

The script APPENDS generated token cards to the original .cardconjurer file by
default. It uses the user's discovered M15 bordered token frame defaults.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

CARD_WIDTH = 2010
CARD_HEIGHT = 2814
NORMAL_TYPE_WIDTH = 1540 / CARD_WIDTH
TITLE_X = 0.0854
TITLE_Y = 0.0522
TITLE_H = 0.0543
TYPE_X = 0.0854
TYPE_Y = 0.65
TYPE_H = 0.0543
RULES_X = 0.086
RULES_Y = 0.7143
RULES_W = 0.828
RULES_H = 0.2048
PT_X = 0.7928
PT_Y = 0.902
PT_W = 0.1367
PT_H = 0.0372
PT_SIZE = 0.0372
TOKEN_ART_X = -79 / CARD_WIDTH
TOKEN_ART_Y = 351 / CARD_HEIGHT
TOKEN_ART_ZOOM = 1.413
TOKEN_ART_ROTATE = 0
TOKEN_SET_SYMBOL_Y = 0.6535181236673774
TOKEN_SET_SYMBOL_BOUNDS_Y = 0.6743

COLOR_NAMES = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "M": "Multicolored",
    "A": "Artifact",
    "L": "Land",
}
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
    "Tribal",
}
SUPERTYPES = {"Basic", "Legendary", "Snow", "World"}


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(2)


def title_width(mana: str) -> float:
    symbols = len(re.findall(r"\{[^{}]+\}", mana or ""))
    return max(300, 1680 - 95 * symbols) / CARD_WIDTH


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).casefold()


def visible_title(card_entry: Dict[str, Any]) -> str:
    return str(card_entry.get("data", {}).get("text", {}).get("title", {}).get("text", "") or card_entry.get("key", ""))


def find_card(cards: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    target = normalize_name(name)
    exact_key = [c for c in cards if normalize_name(c.get("key", "")) == target]
    if len(exact_key) == 1:
        return exact_key[0]
    exact_title = [c for c in cards if normalize_name(visible_title(c)) == target]
    if len(exact_title) == 1:
        return exact_title[0]
    if not exact_key and not exact_title:
        die(f"Could not find source card {name!r} in input .cardconjurer.")
    die(f"Source card lookup for {name!r} is ambiguous. Use a more specific name/key.")


def detect_frame_code(card_entry: Dict[str, Any]) -> str:
    frames = card_entry.get("data", {}).get("frames", [])
    for frame in frames:
        name = str(frame.get("name", ""))
        for code, cname in COLOR_NAMES.items():
            if name.startswith(cname + " "):
                return code
    for frame in frames:
        src = str(frame.get("src", ""))
        m = re.search(r"m15(?:Frame|PT|Crown)([WUBRGMAL])(?:Floating)?\.png", src)
        if m:
            return m.group(1)
    return "M"


def split_type_line(type_line: str) -> Dict[str, Any]:
    normalized = str(type_line or "").replace("—", " - ").replace("–", " - ")
    left, sep, right = normalized.partition(" - ")
    left_tokens = [t for t in left.strip().split() if t]
    subtypes = [t for t in right.strip().split() if t] if sep else []
    types = [t for t in left_tokens if t in MAIN_TYPES]
    supertypes = [t for t in left_tokens if t in SUPERTYPES]
    other = [t for t in left_tokens if t not in MAIN_TYPES and t not in SUPERTYPES]
    return {
        "left_tokens": left_tokens,
        "types": types,
        "supertypes": supertypes,
        "subtypes": subtypes,
        "other": other,
    }


def join_type_line(supertypes: List[str], types: List[str], subtypes: List[str]) -> str:
    left = " ".join(list(supertypes) + list(types)).strip()
    right = " ".join(subtypes).strip()
    return f"{left} - {right}" if right else left


def apply_type_modifications(type_line: str, spec: Dict[str, Any]) -> str:
    parts = split_type_line(type_line)
    supertypes = list(parts["supertypes"])
    types = list(parts["types"])
    subtypes = list(parts["subtypes"])

    if spec.get("nonlegendary"):
        supertypes = [t for t in supertypes if t != "Legendary"]

    if "replace_creature_subtypes" in spec and spec["replace_creature_subtypes"] not in (None, ""):
        replacement = spec["replace_creature_subtypes"]
        if isinstance(replacement, str):
            repl = replacement.replace("—", " ").replace("-", " ").split()
        elif isinstance(replacement, list):
            repl = [str(x).strip() for x in replacement if str(x).strip()]
        else:
            die("replace_creature_subtypes must be a string or list of strings.")
        # Rule 205.1a: when an effect sets creature subtypes, it replaces the existing creature types,
        # while leaving card types and supertypes alone.
        subtypes = repl

    return join_type_line(supertypes, types, subtypes)


def crown_frame(code: str) -> Dict[str, Any]:
    cname = COLOR_NAMES.get(code, "Multicolored")
    return {
        "name": f"{cname} Legend Crown",
        "src": f"/img/frames/m15/crowns/m15Crown{code}Floating.png",
        "bounds": {"x": 0.0307, "y": 0.0191, "width": 0.9387, "height": 0.1024},
        "complementary": [10],
        "masks": [],
    }


def crown_border_cover() -> Dict[str, Any]:
    return {
        "name": "Legend Crown Border Cover",
        "src": "/img/black.png",
        "bounds": {"x": 0.0394, "y": 0.0277, "width": 0.9214, "height": 0.0177},
        "masks": [],
    }


def pt_frame(code: str) -> Dict[str, Any]:
    cname = COLOR_NAMES.get(code, "Multicolored")
    return {
        "name": f"{cname} Power/Toughness",
        "src": f"/img/frames/m15/regular/m15PT{code}.png",
        "bounds": {"x": 0.7573, "y": 0.8848, "width": 0.188, "height": 0.0733},
        "masks": [],
    }


def token_frame(code: str) -> Dict[str, Any]:
    cname = COLOR_NAMES.get(code, "Multicolored")
    return {
        "name": f"{cname} Frame",
        "src": f"/img/frames/token/m15/regular/{code.lower()}.png",
        "masks": [],
    }


def has_power_toughness(data: Dict[str, Any], spec: Dict[str, Any]) -> bool:
    text = data.get("text", {})
    return bool(spec.get("power_toughness") or str(text.get("pt", {}).get("text", "")).strip())


def apply_token_layout(data: Dict[str, Any], frame_code: str, keep_legendary: bool, spec: Dict[str, Any]) -> None:
    data["version"] = "tokenRegularM15"
    new_frames: List[Dict[str, Any]] = []
    if has_power_toughness(data, spec):
        new_frames.append(pt_frame(frame_code))
    if keep_legendary:
        new_frames.append(crown_frame(frame_code))
        new_frames.append(crown_border_cover())
    new_frames.append(token_frame(frame_code))
    data["frames"] = new_frames

    data["artX"] = TOKEN_ART_X
    data["artY"] = TOKEN_ART_Y
    data["artZoom"] = TOKEN_ART_ZOOM
    data["artRotate"] = TOKEN_ART_ROTATE
    data["setSymbolY"] = TOKEN_SET_SYMBOL_Y
    if isinstance(data.get("setSymbolBounds"), dict):
        data["setSymbolBounds"]["y"] = TOKEN_SET_SYMBOL_BOUNDS_Y

    text = data.setdefault("text", {})
    mana = text.setdefault("mana", {})
    title = text.setdefault("title", {})
    typ = text.setdefault("type", {})
    rules = text.setdefault("rules", {})

    title["x"] = TITLE_X
    title["y"] = TITLE_Y
    title["width"] = title_width(str(mana.get("text", "")))
    title["height"] = TITLE_H
    title["oneLine"] = True
    title["font"] = "belerenbsc"
    title["size"] = 0.0381
    title["align"] = "center"
    title["color"] = "#fde367"

    typ["x"] = TYPE_X
    typ["y"] = TYPE_Y
    typ["width"] = NORMAL_TYPE_WIDTH
    typ["height"] = TYPE_H
    typ["oneLine"] = True
    typ["font"] = "belerenb"
    typ["size"] = 0.0324

    rules["x"] = RULES_X
    rules["y"] = RULES_Y
    rules["width"] = RULES_W
    rules["height"] = RULES_H

    pt = text.setdefault("pt", {})
    pt["name"] = "Power/Toughness"
    pt["x"] = PT_X
    pt["y"] = PT_Y
    pt["width"] = PT_W
    pt["height"] = PT_H
    pt["size"] = PT_SIZE
    pt["font"] = "belerenbsc"
    pt["oneLine"] = True
    pt["align"] = "center"


def build_token(source: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    entry = copy.deepcopy(source)
    data = entry.setdefault("data", {})
    text = data.setdefault("text", {})
    title_text = str(text.get("title", {}).get("text", "") or visible_title(source))
    mana_text = str(text.get("mana", {}).get("text", "") or "")
    type_text = str(text.get("type", {}).get("text", "") or "")

    new_type_line = apply_type_modifications(type_text, spec)
    keep_legendary = new_type_line.startswith("Legendary ") or new_type_line.startswith("Legendary-") or new_type_line == "Legendary"
    frame_code = str(spec.get("frame_color") or detect_frame_code(source)).upper()
    if frame_code not in COLOR_NAMES:
        die(f"Unsupported frame_color {frame_code!r}; use one of {', '.join(COLOR_NAMES)}")

    apply_token_layout(data, frame_code, keep_legendary, spec)

    text.setdefault("title", {})["text"] = title_text if not spec.get("title_override") else str(spec["title_override"])
    text.setdefault("mana", {})["text"] = mana_text
    text.setdefault("type", {})["text"] = new_type_line

    if spec.get("power_toughness"):
        text.setdefault("pt", {})["text"] = str(spec["power_toughness"])

    # Optional color marker for rules-accurate Preston-style tokens if desired later.
    if spec.get("color_override"):
        data["tokenColorOverride"] = str(spec["color_override"])

    suffix = spec.get("token_key_suffix", " — Token")
    entry["key"] = str(spec.get("output_key") or (title_text + suffix))
    return entry


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Append token-frame copy cards to a Card Conjurer file.")
    p.add_argument("input", help="Input .cardconjurer file")
    p.add_argument("output", help="Output .cardconjurer file")
    p.add_argument("--spec", required=True, help="JSON file containing a list of token specs")
    p.add_argument("--tokens-only", action="store_true", help="Write only the generated token cards instead of originals + tokens")
    p.add_argument("--write-sample-spec", help="Write a sample token spec JSON to this path and exit")
    return p


def sample_spec() -> List[Dict[str, Any]]:
    return [
        {
            "source_name": "Cloud, Midgar Mercenary",
            "token_key_suffix": " — Helm Token",
            "nonlegendary": True,
        },
        {
            "source_name": "Some Legendary Creature",
            "token_key_suffix": " — Preston Token",
            "replace_creature_subtypes": "Illusion",
            "power_toughness": "0/1",
            "frame_color": "W",
            "color_override": "white"
        },
    ]


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.write_sample_spec:
        save_json(Path(args.write_sample_spec), sample_spec())
        print(f"Wrote sample token spec to {args.write_sample_spec}")
        return

    input_path = Path(args.input)
    output_path = Path(args.output)
    spec_path = Path(args.spec)
    cards = load_json(input_path)
    if not isinstance(cards, list):
        die("Input .cardconjurer must be a JSON list of card entries.")
    specs = load_json(spec_path)
    if not isinstance(specs, list) or not all(isinstance(x, dict) for x in specs):
        die("Spec file must be a JSON list of objects.")

    built: List[Dict[str, Any]] = []
    for spec in specs:
        source_name = spec.get("source_name")
        if not source_name:
            die("Each token spec needs source_name.")
        source = find_card(cards, str(source_name))
        built.append(build_token(source, spec))

    out_cards = built if args.tokens_only else list(cards) + built
    save_json(output_path, out_cards)
    print(f"Wrote {len(out_cards)} card(s) to {output_path}")
    print(f"Generated {len(built)} token card(s).")


if __name__ == "__main__":
    main()
