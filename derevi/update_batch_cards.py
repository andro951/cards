import json, copy, re
from pathlib import Path

PATH = Path('derevi/derevi_cards.cardconjurer')
BASE_URL = 'https://raw.githubusercontent.com/andro951/cards/main/derevi'
AUTOFIT = 'https://cdn.jsdelivr.net/gh/andro951/cards@main/derevi/auto_fit_art.js'
CARD_WIDTH = 2010
TYPE_WIDTH_PX = 1560

data = json.loads(PATH.read_text(encoding='utf-8'))
by_key = {item['key']: item for item in data}

# Use Spellseeker as the clean general template because it already has the desired footer,
# set symbol, wings emblem, M15 regular layout, and auto-fit setup.
template = copy.deepcopy(by_key['Spellseeker']['data'])

COLOR_META = {
    'W': ('White', 'W'),
    'U': ('Blue', 'U'),
    'M': ('Multicolored', 'M'),
}

def mana_symbol_count(mana):
    return len(re.findall(r'\{[^{}]+\}', mana or ''))

def recolor_frames(card, color_code, legendary):
    color_name, code = COLOR_META[color_code]
    new_frames = []
    uploaded = None
    for frame in card.get('frames', []):
        name = frame.get('name', '')
        src = frame.get('src', '')
        if name == 'Uploaded Image (0)':
            uploaded = frame
            continue
        if 'Legend Crown' in name or '/crowns/' in src:
            continue
        if 'Power/Toughness' in name or '/regular/m15PT' in src:
            frame['name'] = f'{color_name} Power/Toughness'
            frame['src'] = f'/img/frames/m15/regular/m15PT{code}.png'
        elif '/img/frames/m15/regular/m15Frame' in src:
            frame['name'] = f'{color_name} Frame'
            frame['src'] = f'/img/frames/m15/regular/m15Frame{code}.png'
        new_frames.append(frame)

    rebuilt = []
    if uploaded is not None:
        uploaded['src'] = f'{BASE_URL}/wings_emblem.png'
        rebuilt.append(uploaded)
    if legendary:
        rebuilt.append({
            'name': f'{color_name} Legend Crown',
            'src': f'/img/frames/m15/crowns/m15Crown{code}.png',
            'masks': [],
            'bounds': {'height': 0.1667, 'width': 0.9454, 'x': 0.0274, 'y': 0.0191},
        })
    rebuilt.extend(new_frames)
    card['frames'] = rebuilt

def build_card(name, filename, mana, type_line, rules, pt, color_code, legendary, rules_size):
    card = copy.deepcopy(template)
    recolor_frames(card, color_code, legendary)

    card['artSource'] = f'{BASE_URL}/{filename}'
    card['artX'] = card['artBounds']['x']
    card['artY'] = card['artBounds']['y']
    card['artZoom'] = 1
    card['artRotate'] = '0'
    card['onload'] = AUTOFIT
    card['setSymbolSource'] = f'{BASE_URL}/derevi_set_symbol.png'

    card['text']['title']['text'] = name
    card['text']['mana']['text'] = mana
    card['text']['type']['text'] = type_line
    card['text']['rules']['text'] = rules
    card['text']['rules']['size'] = rules_size
    card['text']['pt']['text'] = pt

    card['text']['type']['width'] = TYPE_WIDTH_PX / CARD_WIDTH
    card['text']['title']['width'] = (1680 - 95 * mana_symbol_count(mana)) / CARD_WIDTH

    card['infoArtist'] = 'ChatGPT'
    card['infoNumber'] = ''
    card['infoRarity'] = ''
    card['infoSet'] = ''
    card['infoLanguage'] = ''
    card['infoNote'] = ''
    card['bottomInfo']['bottomLeft']['text'] = 'Custom Proxy • Personal Use Only'
    card['bottomInfo']['wizards']['text'] = ''
    card['bottomInfo']['bottomRight']['text'] = ''

    return {'key': name, 'data': card}

cards = [
    build_card(
        'Academy Rector',
        'academy_rector.png',
        '{3}{W}',
        'Creature — Human Cleric',
        'When this creature dies, you may exile it. If you do, search your library for an enchantment card, put that card onto the battlefield, then shuffle.',
        '1/2',
        'W',
        False,
        0.0348,
    ),
    build_card(
        'Enduring Curiosity',
        'enduring_curiosity.png',
        '{2}{U}{U}',
        'Enchantment Creature — Cat Glimmer',
        "Flash\nWhenever a creature you control deals combat damage to a player, draw a card.\nWhen Enduring Curiosity dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
        '4/3',
        'U',
        False,
        0.0315,
    ),
    build_card(
        'Preston, the Vanisher',
        'preston_the_vanisher.png',
        '{3}{W}',
        'Legendary Creature — Rabbit Wizard',
        "Whenever another nontoken creature you control enters, if it wasn't cast, create a token that's a copy of that creature, except it's a 0/1 white Illusion.\n{1}{W}, Sacrifice five Illusions: Exile target nonland permanent.",
        '2/5',
        'W',
        True,
        0.0325,
    ),
    build_card(
        'Prime Speaker Vannifar',
        'prime_speaker_vannifar.png',
        '{2}{G}{U}',
        'Legendary Creature — Elf Ooze Wizard',
        "{T}, Sacrifice another creature: Search your library for a creature card with mana value equal to 1 plus the sacrificed creature's mana value, put that card onto the battlefield, then shuffle. Activate only as a sorcery.",
        '2/4',
        'M',
        True,
        0.0315,
    ),
    build_card(
        'Urza, Lord High Artificer',
        'urza_lord_high_artificer.png',
        '{2}{U}{U}',
        'Legendary Creature — Human Artificer',
        'When Urza enters, create a 0/0 colorless Construct artifact creature token with "This token gets +1/+1 for each artifact you control."\nTap an untapped artifact you control: Add {U}.\n{5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost.',
        '1/4',
        'U',
        True,
        0.0295,
    ),
]

for new_item in cards:
    key = new_item['key']
    if key in by_key:
        idx = next(i for i, item in enumerate(data) if item['key'] == key)
        data[idx] = new_item
    else:
        data.append(new_item)

PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print('Updated cards:', ', '.join(item['key'] for item in cards))
print('Total cards:', len(data))
