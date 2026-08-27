import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STYLE_FILE = ROOT / 'STYLE_RULES.md'

cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
removed = 0
for entry in cards:
    frames = entry['data'].get('frames', [])
    kept = []
    for fr in frames:
        src = fr.get('src', '')
        if 'wings_emblem.png' in src:
            removed += 1
            continue
        kept.append(fr)
    entry['data']['frames'] = kept

if removed != len(cards):
    raise RuntimeError(f'Expected to remove one wings emblem from each of {len(cards)} cards; removed {removed}')
if any('wings_emblem.png' in fr.get('src', '') for entry in cards for fr in entry['data'].get('frames', [])):
    raise RuntimeError('A wings emblem frame still remains')

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

style = STYLE_FILE.read_text(encoding='utf-8')
style = style.replace(
    "Shared assets:\n- Set symbol: `https://raw.githubusercontent.com/andro951/cards/main/derevi/derevi_set_symbol.png`\n- Bottom wings emblem: `https://raw.githubusercontent.com/andro951/cards/main/derevi/wings_emblem.png`",
    "Shared assets:\n- Set symbol: `https://raw.githubusercontent.com/andro951/cards/main/derevi/derevi_set_symbol.png`\n- Do not add a bottom wings emblem; it was intentionally removed from all cards."
)
style = style.replace(
    "\nBottom wings emblem bounds:\n- `width = 0.19701492537313434`\n- `height = 0.08443496801705758`\n- `x = 0.4223880597014925`\n- `y = 0.8906183368869937`\n",
    "\n"
)
style = style.replace(
    "Preserve artist/footer/set-symbol/wings/no-metadata conventions.",
    "Preserve artist/footer/set-symbol/no-metadata conventions; do not restore the removed bottom wings emblem."
)
STYLE_FILE.write_text(style, encoding='utf-8')

print(f'Removed bottom wings from {removed}/{len(cards)} cards and updated STYLE_RULES.md.')
