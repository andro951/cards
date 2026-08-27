import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STYLE_FILE = ROOT / 'STYLE_RULES.md'

WIDTH_PX = 1540
CARD_WIDTH = 2010
WIDTH_NORM = WIDTH_PX / CARD_WIDTH

cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
count = 0
for entry in cards:
    t = entry['data']['text']['type']
    t['width'] = WIDTH_NORM
    count += 1

assert count == len(cards)
assert all(entry['data']['text']['type']['width'] == WIDTH_NORM for entry in cards)
CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

style = STYLE_FILE.read_text(encoding='utf-8')
old = "Type text box width is always exactly **1560 px**:\n\n`1560 / 2010 = 0.7761194029850746`"
new = f"Type text box width is always exactly **{WIDTH_PX} px**:\n\n`{WIDTH_PX} / {CARD_WIDTH} = {WIDTH_NORM}`"
if old not in style:
    raise RuntimeError('Expected old type-width rule not found in STYLE_RULES.md')
style = style.replace(old, new)
STYLE_FILE.write_text(style, encoding='utf-8')

print(f'Updated {count} cards to type width {WIDTH_PX}px ({WIDTH_NORM}).')
