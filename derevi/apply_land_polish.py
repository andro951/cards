import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STYLE = ROOT / 'STYLE_RULES.md'

CROWN_BOUNDS = {'height': 0.1667, 'width': 0.9454, 'x': 0.0274, 'y': 0.0191}

cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
by_name = {x['key']: x['data'] for x in cards}


def replace_base_frame(card, frame_name, frame_src):
    for fr in card.get('frames', []):
        if fr.get('name') == 'Uploaded Image (0)':
            continue
        if 'Crown' in fr.get('name', '') or 'Power/Toughness' in fr.get('name', ''):
            continue
        fr['name'] = frame_name
        fr['src'] = frame_src


def remove_crowns(card):
    card['frames'] = [fr for fr in card.get('frames', []) if 'Crown' not in fr.get('name', '') and '/crowns/' not in fr.get('src', '')]


def ensure_crown(card, crown_name, crown_src):
    frames = [fr for fr in card.get('frames', []) if 'Crown' not in fr.get('name', '') and '/crowns/' not in fr.get('src', '')]
    crown = {'name': crown_name, 'src': crown_src, 'masks': [], 'bounds': CROWN_BOUNDS.copy()}
    insert_at = 1 if frames and frames[0].get('name') == 'Uploaded Image (0)' else 0
    frames.insert(insert_at, crown)
    card['frames'] = frames

# Dual lands: multicolored treatment, no crown, current Scryfall mana reminder text,
# and a more intentional compact/centered rules placement in the otherwise-empty box.
for name, rules in {
    'Savannah': '({T}: Add {G} or {W}.)',
    'Tropical Island': '({T}: Add {G} or {U}.)',
    'Tundra': '({T}: Add {W} or {U}.)',
}.items():
    c = by_name[name]
    remove_crowns(c)
    replace_base_frame(c, 'Multicolored Frame', '/img/frames/m15/regular/m15FrameM.png')
    c['text']['rules']['text'] = rules
    c['text']['rules']['y'] = 0.743
    c['text']['rules']['height'] = 0.10
    c['text']['rules']['size'] = 0.0385

# Gaea's Cradle: green-inflected legendary treatment while preserving its current rules text.
c = by_name["Gaea's Cradle"]
ensure_crown(c, 'Green Legend Crown', '/img/frames/m15/crowns/m15CrownG.png')
replace_base_frame(c, 'Green Frame', '/img/frames/m15/regular/m15FrameG.png')
c['text']['rules']['text'] = '{T}: Add {G} for each creature you control.'
c['text']['rules']['y'] = 0.743
c['text']['rules']['height'] = 0.10
c['text']['rules']['size'] = 0.0375

# Sanity checks: leave Skullclamp/Nyx Lotus untouched and enforce intended land results.
for name in ('Savannah', 'Tropical Island', 'Tundra'):
    c = by_name[name]
    assert not any('Crown' in fr.get('name', '') for fr in c['frames'])
    assert all('/m15FrameM.png' in fr.get('src', '') for fr in c['frames'] if fr.get('name') != 'Uploaded Image (0)')

c = by_name["Gaea's Cradle"]
assert sum('Crown' in fr.get('name', '') for fr in c['frames']) == 1
assert any('/m15CrownG.png' in fr.get('src', '') for fr in c['frames'])

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

style = STYLE.read_text(encoding='utf-8')
land_section = '''\n## Land presentation\n- Savannah, Tropical Island, and Tundra use a multicolored M15 treatment rather than the plain generic land frame.\n- Their current Scryfall parenthetical mana abilities are shown in the rules box.\n- Gaea's Cradle uses a green-inflected frame and green legendary crown.\n- Sparse land rules text may be vertically repositioned/enlarged for intentional visual balance.\n'''
if '## Land presentation' not in style:
    style = style.rstrip() + '\n' + land_section
workflow_rule = '''\n## Repository write rule\n- If `derevi/derevi_cards.cardconjurer` is modified, commit/push the change to GitHub in the same task. A local-only edited copy is not considered completion unless the user explicitly asks for local-only work.\n'''
if '## Repository write rule' not in style:
    style = style.rstrip() + '\n' + workflow_rule
STYLE.write_text(style, encoding='utf-8')

print('Applied land polish to Savannah, Tropical Island, Tundra, and Gaea\'s Cradle.')
