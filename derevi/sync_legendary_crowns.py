import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STYLE = ROOT / 'STYLE_RULES.md'
STATUS = ROOT / 'PROXY_SYNC_STATUS.md'

CROWN_BOUNDS = {'height': 0.1667, 'width': 0.9454, 'x': 0.0274, 'y': 0.0191}
CROWNS = {
    'W': ('White Legend Crown', '/img/frames/m15/crowns/m15CrownW.png'),
    'U': ('Blue Legend Crown', '/img/frames/m15/crowns/m15CrownU.png'),
    'B': ('Black Legend Crown', '/img/frames/m15/crowns/m15CrownB.png'),
    'R': ('Red Legend Crown', '/img/frames/m15/crowns/m15CrownR.png'),
    'G': ('Green Legend Crown', '/img/frames/m15/crowns/m15CrownG.png'),
    'M': ('Multicolored Legend Crown', '/img/frames/m15/crowns/m15CrownM.png'),
    'A': ('Artifact Legend Crown', '/img/frames/m15/crowns/m15CrownA.png'),
    'L': ('Land Legend Crown', '/img/frames/m15/crowns/m15CrownL.png'),
}


def frame_code(card):
    srcs = [f.get('src', '') for f in card.get('frames', [])]
    # Order matters: artifact/land before single-color checks.
    for code in ('A', 'L', 'M', 'W', 'U', 'B', 'R', 'G'):
        needle_regular = f'm15Frame{code}.png'
        needle_nyx = f'm15Frame{code}Nyx.png'
        if any(needle_regular in s or needle_nyx in s for s in srcs):
            return code
    raise RuntimeError('Could not infer frame color/type from: ' + repr(srcs))


cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
assert len(cards) == 26, f'Expected 26 cards, found {len(cards)}'

changed = []
legendary_names = []
nonlegendary_names = []

for entry in cards:
    name = entry['key']
    card = entry['data']
    type_line = card['text']['type']['text']
    is_legendary = type_line.startswith('Legendary ') or ' Legendary ' in type_line

    old_frames = card.get('frames', [])
    old_crowns = [f for f in old_frames if '/crowns/' in f.get('src', '') or 'Crown' in f.get('name', '')]
    frames = [f for f in old_frames if f not in old_crowns]

    if is_legendary:
        legendary_names.append(name)
        code = frame_code(card)
        crown_name, crown_src = CROWNS[code]
        crown = {'name': crown_name, 'src': crown_src, 'masks': [], 'bounds': CROWN_BOUNDS.copy()}
        # Keep the custom wing emblem at the very bottom of the stack, then put the crown above it.
        insert_at = 1 if frames and frames[0].get('name') == 'Uploaded Image (0)' else 0
        frames.insert(insert_at, crown)
        if len(old_crowns) != 1 or old_crowns[0].get('src') != crown_src:
            changed.append(f'{name}: set {crown_name}')
    else:
        nonlegendary_names.append(name)
        if old_crowns:
            changed.append(f'{name}: removed legendary crown')

    card['frames'] = frames

# Verify exact crown invariant after modification.
for entry in cards:
    card = entry['data']
    type_line = card['text']['type']['text']
    is_legendary = type_line.startswith('Legendary ') or ' Legendary ' in type_line
    crowns = [f for f in card.get('frames', []) if '/crowns/' in f.get('src', '') or 'Crown' in f.get('name', '')]
    assert len(crowns) == (1 if is_legendary else 0), f"{entry['key']}: crown mismatch"

assert len(legendary_names) == 12, f'Expected 12 legendary cards, found {len(legendary_names)}: {legendary_names}'
assert len(nonlegendary_names) == 14, f'Expected 14 nonlegendary cards, found {len(nonlegendary_names)}'

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

style = STYLE.read_text(encoding='utf-8')
section = '''\n## Legendary crowns\n- Every permanent whose current type line contains `Legendary` uses the appropriate M15 legendary crown.\n- Nonlegendary cards never use a legendary crown, regardless of rarity.\n- Crown color/type follows the active base frame (white, blue, black, red, green, multicolored, artifact, or land).\n- Nyx treatment and legendary crowns are independent: a legendary enchantment would use both.\n'''
if '## Legendary crowns' not in style:
    STYLE.write_text(style.rstrip() + '\n' + section, encoding='utf-8')

status = STATUS.read_text(encoding='utf-8').rstrip()
block = f'''\n\n## Legendary crown audit\n- Legendary cards: **{len(legendary_names)}**; all have exactly one matching crown.\n- Nonlegendary cards: **{len(nonlegendary_names)}**; all have no crown.\n- Crown mismatches remaining: **0**.\n'''
if '## Legendary crown audit' in status:
    status = status.split('## Legendary crown audit')[0].rstrip()
STATUS.write_text(status + block, encoding='utf-8')

print(f'Legendary: {len(legendary_names)}; nonlegendary: {len(nonlegendary_names)}')
for item in changed:
    print('CHANGE', item)
