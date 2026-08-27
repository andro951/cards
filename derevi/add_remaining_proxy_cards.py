import copy, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAVE = ROOT / 'derevi_cards.cardconjurer'
CHECKLIST = ROOT / 'scryfall_proxy_decklist.txt'
BASE_URL = 'https://raw.githubusercontent.com/andro951/cards/main/derevi'
AUTO_FIT = 'https://cdn.jsdelivr.net/gh/andro951/cards@main/derevi/auto_fit_art.js'
CARD_WIDTH = 2010
TYPE_WIDTH_PX = 1560

CARDS = {
    'Mox Amber': dict(mana='{0}', type='Legendary Artifact', rules='{T}: Add one mana of any color among legendary creatures and planeswalkers you control.', frame='A', legendary=True, art='mox_amber.png', size=0.0348),
    'Mox Opal': dict(mana='{0}', type='Legendary Artifact', rules='Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts.', frame='A', legendary=True, art='mox_opal.png', size=0.0348),
    'Skullclamp': dict(mana='{1}', type='Artifact — Equipment', rules='Equipped creature gets +1/-1.\nWhenever equipped creature dies, draw two cards.\nEquip {1}', frame='A', legendary=False, art='skull_clamp.png', size=0.0348),
    'Helm of the Host': dict(mana='{4}', type='Legendary Artifact — Equipment', rules="At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't legendary. That token gains haste.\nEquip {5}", frame='A', legendary=True, art='helm_of_the_host.png', size=0.0325),
    'Nyx Lotus': dict(mana='{4}', type='Legendary Artifact', rules='Nyx Lotus enters tapped.\n{T}: Choose a color. Add an amount of mana of that color equal to your devotion to that color. (Your devotion to a color is the number of mana symbols of that color in the mana costs of permanents you control.)', frame='A', legendary=True, art='nyx_lotus.png', size=0.0305),
    'Fierce Guardianship': dict(mana='{2}{U}', type='Instant', rules='If you control a commander, you may cast this spell without paying its mana cost.\nCounter target noncreature spell.', frame='U', legendary=False, art='fierce_guardianship.png', size=0.0348),
    "Gaea's Cradle": dict(mana='', type='Legendary Land', rules='{T}: Add {G} for each creature you control.', frame='L', legendary=True, art='gaeas_cradle.png', size=0.0348),
    'Savannah': dict(mana='', type='Land — Forest Plains', rules='', frame='L', legendary=False, art='savana.png', size=0.0348),
    'Tropical Island': dict(mana='', type='Land — Forest Island', rules='', frame='L', legendary=False, art='tropical_island.png', size=0.0348),
    'Tundra': dict(mana='', type='Land — Plains Island', rules='', frame='L', legendary=False, art='tundra.png', size=0.0348),
    'Grim Monolith': dict(mana='{2}', type='Artifact', rules="This artifact doesn't untap during your untap step.\n{T}: Add {C}{C}{C}.\n{4}: Untap this artifact.", frame='A', legendary=False, art='grim_monolith.png', size=0.0340),
    'Mana Vault': dict(mana='{1}', type='Artifact', rules="This artifact doesn't untap during your untap step.\nAt the beginning of your upkeep, you may pay {4}. If you do, untap this artifact.\nAt the beginning of your draw step, if this artifact is tapped, it deals 1 damage to you.\n{T}: Add {C}{C}{C}.", frame='A', legendary=False, art='mana_vault.png', size=0.0285),
    'Mana Drain': dict(mana='{U}{U}', type='Instant', rules="Counter target spell. At the beginning of your next main phase, add an amount of {C} equal to that spell's mana value.", frame='U', legendary=False, art='mana_drain.png', size=0.0348),
    'Phyrexian Altar': dict(mana='{3}', type='Artifact', rules='Sacrifice a creature: Add one mana of any color.', frame='A', legendary=False, art='pyrexian_altar.png', size=0.0348),
    'Survival of the Fittest': dict(mana='{1}{G}', type='Enchantment', rules='{G}, Discard a creature card: Search your library for a creature card, reveal that card, put it into your hand, then shuffle.', frame='G', legendary=False, art='survival_of_the_fittest.png', size=0.0340),
}

FRAME_NAMES = {'W':'White','U':'Blue','B':'Black','R':'Red','G':'Green','M':'Multicolored','A':'Artifact','L':'Land'}
MASKS = [
    ('Pinline','/img/frames/m15/regular/m15MaskPinline.png'),
    ('Type','/img/frames/m15/regular/m15MaskType.png'),
    ('Title','/img/frames/m15/regular/m15MaskTitle.png'),
    ('Rules','/img/frames/m15/regular/m15MaskRules.png'),
    ('Frame','/img/frames/m15/regular/m15MaskFrame.png'),
    ('Border','/img/frames/m15/regular/m15MaskBorder.png'),
]

def count_symbols(mana):
    return len(re.findall(r'\{[^{}]+\}', mana or ''))

def make_frames(existing_wing, key, legendary):
    label = FRAME_NAMES[key]
    frames = [copy.deepcopy(existing_wing)]
    if legendary:
        frames.append({
            'name': f'{label} Legend Crown',
            'src': f'/img/frames/m15/crowns/m15Crown{key}.png',
            'masks': [],
            'bounds': {'height':0.1667,'width':0.9454,'x':0.0274,'y':0.0191},
        })
    src = f'/img/frames/m15/regular/m15Frame{key}.png'
    for mask_name, mask_src in MASKS:
        frames.append({'name': f'{label} Frame', 'src': src, 'masks':[{'src':mask_src,'name':mask_name}]})
    return frames

cards = json.loads(SAVE.read_text(encoding='utf-8'))
by_name = {x['key']: x for x in cards}
# Spellseeker is a clean nonlegendary template with the correct footer and box geometry.
template = copy.deepcopy(by_name['Spellseeker']['data'])
wing = next(f for f in template['frames'] if f.get('name') == 'Uploaded Image (0)')

for name, spec in CARDS.items():
    card = copy.deepcopy(template)
    card['frames'] = make_frames(wing, spec['frame'], spec['legendary'])
    card['artSource'] = f"{BASE_URL}/{spec['art']}"
    card['artX'] = card['artBounds']['x']
    card['artY'] = card['artBounds']['y']
    card['artZoom'] = 1
    card['artRotate'] = '0'
    card['onload'] = AUTO_FIT
    card['setSymbolSource'] = f'{BASE_URL}/derevi_set_symbol.png'
    card['text']['title']['text'] = name
    card['text']['mana']['text'] = spec['mana']
    card['text']['type']['text'] = spec['type']
    card['text']['rules']['text'] = spec['rules']
    card['text']['rules']['size'] = spec['size']
    card['text']['pt']['text'] = ''
    card['text']['type']['width'] = TYPE_WIDTH_PX / CARD_WIDTH
    card['text']['title']['width'] = (1680 - 95 * count_symbols(spec['mana'])) / CARD_WIDTH
    card['infoArtist'] = 'ChatGPT'
    card['infoNumber'] = card['infoRarity'] = card['infoSet'] = card['infoLanguage'] = card['infoNote'] = ''
    item = {'key': name, 'data': card}
    if name in by_name:
        idx = next(i for i,x in enumerate(cards) if x['key'] == name)
        cards[idx] = item
    else:
        cards.append(item)
    by_name[name] = item

# Validate against the Scryfall proxy checklist. Derevi is preserved as an extra/source card too.
check_names = []
for raw in CHECKLIST.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line: continue
    parts = line.split(' ', 1)
    name = parts[1] if len(parts) == 2 and parts[0].isdigit() else line
    if name not in check_names: check_names.append(name)

present = {x['key'] for x in cards}
missing_entries = [n for n in check_names if n not in present]
if missing_entries:
    raise SystemExit('Missing Card Conjurer entries: ' + ', '.join(missing_entries))

missing_art = [n for n,s in CARDS.items() if not (ROOT / s['art']).exists()]
SAVE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',',':')), encoding='utf-8')

status = [
    '# Derevi proxy sync status', '',
    f'- Scryfall checklist entries: **{len(check_names)}**',
    f'- Card Conjurer entries: **{len(cards)}**',
    f'- Checklist entries missing from Card Conjurer: **{len(missing_entries)}**',
    f'- Card entries whose expected custom art PNG is missing: **{len(missing_art)}**', '',
]
if missing_art:
    status += ['## Missing custom art'] + [f'- {n} → `{CARDS[n]["art"]}`' for n in missing_art]
else:
    status += ['All checklist cards have custom art present.']
(ROOT / 'PROXY_SYNC_STATUS.md').write_text('\n'.join(status) + '\n', encoding='utf-8')
print(f'Card Conjurer now has {len(cards)} entries. Missing custom art: {missing_art}')
