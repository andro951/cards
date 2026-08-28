import json
from pathlib import Path

CARD_FILE = Path("derevi/derevi_cards.cardconjurer")

FLAVOR = {
    "Derevi, Empyrial Tactician": "When she falls, another finds their place.",
    "Cloud, Midgar Mercenary": "Identity is complicated. Swords are not.",
    "Oswald Fiddlebender": "Can't see this airship crashing in the near future. Sturdy as a rock.",
    "Delney, Streetwise Lookout": "It's not a matter of what I know. It's a matter of making it worth my while to tell you.",
    "Recruiter of the Guard": "Before a cause can have supporters, it has to have a voice.",
    "Spellseeker": "Not content with mere answers, she hunts for the truth.",
    "Academy Rector": "The final lesson is learned only after the teacher is gone.",
    "Enduring Curiosity": "How many lives until it learns its lesson?",
    "Preston, the Vanisher": "Making a second one is easy. Convincing reality to keep both is harder.",
    "Prime Speaker Vannifar": "All lives end. Some simply deserve less time.",
    "Urza, Lord High Artificer": "When you've eliminated the possible, what remains?",
    "Mox Amber": "A moment in time made tangible, it has the power to realize epic visions.",
    "Mox Opal": "The suns of Mirrodin have shone upon perfection only once.",
    "Skullclamp": "The mind is a beautiful bounty encased in an annoying bone container.",
    "Helm of the Host": "When both claim to be the original, survival settles the matter.",
    "Nyx Lotus": "Are you prepared for your faith to be tested?",
    "Fierce Guardianship": "No good commander stands alone.",
    "Gaea's Cradle": "Mother provides.",
    "Grim Monolith": "Part prison, part home.",
    "Mana Vault": "Some doors are better left unopened.",
    "Mana Drain": "I suppose you've never heard of conservation of energy.",
    "Phyrexian Altar": "The price of a miracle is less than you think.",
    "Survival of the Fittest": "There's always a bigger fish.",
}

NO_FLAVOR = {"Savannah", "Tropical Island", "Tundra"}
EXPECTED = set(FLAVOR) | NO_FLAVOR


def strip_flavor(text: str) -> str:
    cut = len(text)
    for marker in ("{flavor}", "{oldflavor}", "///"):
        pos = text.find(marker)
        if pos != -1:
            cut = min(cut, pos)
    return text[:cut].rstrip()


cards = json.loads(CARD_FILE.read_text(encoding="utf-8"))
keys = [entry["key"] for entry in cards]
if len(keys) != len(set(keys)):
    raise RuntimeError("Duplicate card keys found")
if set(keys) != EXPECTED:
    raise RuntimeError(f"Unexpected card roster. Missing={sorted(EXPECTED-set(keys))}; extra={sorted(set(keys)-EXPECTED)}")

for entry in cards:
    name = entry["key"]
    data = entry["data"]
    rules = data.get("text", {}).get("rules")
    if not rules:
        raise RuntimeError(f"Missing rules text object for {name}")
    oracle_only = strip_flavor(str(rules.get("text", "")))
    if name in FLAVOR:
        rules["text"] = oracle_only + "{flavor}" + FLAVOR[name]
    else:
        rules["text"] = oracle_only
    data["showsFlavorBar"] = True

# Verify exact final state before writing.
for entry in cards:
    name = entry["key"]
    text = entry["data"]["text"]["rules"]["text"]
    if name in FLAVOR:
        expected_suffix = "{flavor}" + FLAVOR[name]
        if not text.endswith(expected_suffix) or text.count("{flavor}") != 1:
            raise RuntimeError(f"Flavor verification failed for {name}")
    else:
        if any(marker in text for marker in ("{flavor}", "{oldflavor}", "///")):
            raise RuntimeError(f"Unexpected flavor marker on {name}")

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"Added finalized flavor text to {len(FLAVOR)} cards; {len(NO_FLAVOR)} cards intentionally remain blank.")
for name in keys:
    print(f"{name}: {FLAVOR.get(name, 'NONE')}")
