import json
from pathlib import Path

CARD_FILE = Path("derevi/derevi_cards.cardconjurer")
BASE = "https://raw.githubusercontent.com/andro951/cards/main/derevi/"

MYTHIC = {
    "Cloud, Midgar Mercenary",
    "Delney, Streetwise Lookout",
    "Derevi, Empyrial Tactician",
    "Mox Amber",
    "Mox Opal",
    "Prime Speaker Vannifar",
    "Urza, Lord High Artificer",
}

UNCOMMON = {
    "Mana Drain",
    "Skullclamp",
}

COMMON = set()

EXPECTED = {
    "Academy Rector",
    "Cloud, Midgar Mercenary",
    "Delney, Streetwise Lookout",
    "Derevi, Empyrial Tactician",
    "Enduring Curiosity",
    "Fierce Guardianship",
    "Gaea's Cradle",
    "Grim Monolith",
    "Helm of the Host",
    "Mana Drain",
    "Mana Vault",
    "Mox Amber",
    "Mox Opal",
    "Nyx Lotus",
    "Oswald Fiddlebender",
    "Phyrexian Altar",
    "Preston, the Vanisher",
    "Prime Speaker Vannifar",
    "Recruiter of the Guard",
    "Savannah",
    "Skullclamp",
    "Spellseeker",
    "Survival of the Fittest",
    "Tropical Island",
    "Tundra",
    "Urza, Lord High Artificer",
}

cards = json.loads(CARD_FILE.read_text(encoding="utf-8"))
actual = {card["key"] for card in cards}
if actual != EXPECTED:
    missing = sorted(EXPECTED - actual)
    extra = sorted(actual - EXPECTED)
    raise SystemExit(f"Card list mismatch. Missing={missing}; Extra={extra}")

counts = {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}
for card in cards:
    name = card["key"]
    if name in MYTHIC:
        rarity = "mythic"
    elif name in UNCOMMON:
        rarity = "uncommon"
    elif name in COMMON:
        rarity = "common"
    else:
        rarity = "rare"
    card["data"]["setSymbolSource"] = BASE + rarity + ".png"
    counts[rarity] += 1

expected_counts = {"mythic": 7, "rare": 17, "uncommon": 2, "common": 0}
if counts != expected_counts:
    raise SystemExit(f"Unexpected rarity counts: {counts}")

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("Updated rarity symbols:", counts)
