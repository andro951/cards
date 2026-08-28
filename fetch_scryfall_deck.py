#!/usr/bin/env python3
"""Fetch a Scryfall deck export into one project folder.

Example:
    python fetch_scryfall_deck.py \
        --deck-id cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d \
        --output-dir derevi
"""

import argparse
import json
import urllib.request
from pathlib import Path

DEFAULT_UA = "andro951-cardconjurer-sync/1.0"


def get_json(url: str, user_agent: str):
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_cards(raw):
    found = {}

    def consider(obj):
        if not isinstance(obj, dict):
            return
        name = obj.get("name")
        if not name:
            return
        if obj.get("object") == "card_digest" or any(
            key in obj for key in ("mana_cost", "type_line", "oracle_id")
        ):
            found.setdefault(
                name,
                {
                    "name": name,
                    "mana_cost": obj.get("mana_cost", ""),
                    "type_line": obj.get("type_line", ""),
                    "oracle_text": obj.get("oracle_text", ""),
                    "power": obj.get("power"),
                    "toughness": obj.get("toughness"),
                    "colors": obj.get("colors", []),
                    "color_identity": obj.get("color_identity", []),
                    "layout": obj.get("layout", ""),
                    "oracle_id": obj.get("oracle_id", ""),
                    "scryfall_uri": obj.get("scryfall_uri", ""),
                },
            )

    def walk(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("card_digest"), dict):
                consider(obj["card_digest"])
            consider(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(raw)
    return list(found.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck-id", required=True, help="Scryfall deck UUID")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Project folder that receives the Scryfall snapshot files",
    )
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://api.scryfall.com/decks/{args.deck_id}/export/json"
    raw = get_json(url, args.user_agent)

    (output_dir / "scryfall_proxy_export.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    cards = collect_cards(raw)
    (output_dir / "scryfall_proxy_cards.json").write_text(
        json.dumps(cards, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "scryfall_proxy_decklist.txt").write_text(
        "\n".join("1 " + card["name"] for card in cards) + "\n",
        encoding="utf-8",
    )

    print(f"Fetched {len(cards)} Scryfall checklist cards into {output_dir}.")


if __name__ == "__main__":
    main()
