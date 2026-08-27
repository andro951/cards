import copy, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STATUS = ROOT / 'PROXY_SYNC_STATUS.md'
STYLE = ROOT / 'STYLE_RULES.md'
AUTO_FIT = 'https://cdn.jsdelivr.net/gh/andro951/cards@main/derevi/auto_fit_art.js'

cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
by_name = {c['key']: c for c in cards}
derevi = by_name['Derevi, Empyrial Tactician']['data']

# Cards whose art framing was deliberately hand-tuned and should not be changed.
MANUAL_CROP = {
    'Derevi, Empyrial Tactician',
    'Cloud, Midgar Mercenary',
    'Oswald Fiddlebender',
    'Delney, Streetwise Lookout',
}

# Visible card text should stay in the safe ASCII punctuation set used reliably by Card Conjurer.
def clean_visible_text(s):
    if not isinstance(s, str):
        return s
    replacements = {
        '\u2014': '-', '\u2013': '-', '\u2212': '-',
        '\u2018': "'", '\u2019': "'", '\u201a': "'", '\u201b': "'",
        '\u201c': '"', '\u201d': '"', '\u201e': '"', '\u201f': '"',
        '\u00a0': ' ', '\u202f': ' ', '\u2007': ' ',
        '\u2026': '...', '\ufffd': '', '\u25a1': '', '\u25a0': '',
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    # Type lines / ability labels should use a plain, normally-sized hyphen with spaces.
    s = re.sub(r'\s+-\s+', ' - ', s)
    return s

# These values are project-wide and should be literally inherited from Derevi.
TOP_LEVEL_FROM_DEREVI = [
    'width','height','marginX','marginY','setSymbolSource','setSymbolX','setSymbolY','setSymbolZoom',
    'watermarkSource','watermarkX','watermarkY','watermarkZoom','watermarkLeft','watermarkRight','watermarkOpacity',
    'version','manaSymbols','infoYear','margins','bottomInfoTranslate','bottomInfoRotate','bottomInfoZoom',
    'bottomInfoColor','hideBottomInfoBorder','showsFlavorBar','bottomInfo','artBounds','setSymbolBounds','watermarkBounds',
    'infoNumber','infoRarity','infoSet','infoLanguage','infoArtist','infoNote','serialNumber','serialTotal',
    'serialX','serialY','serialScale','noCorners'
]

changes = []
unicode_before = []

for entry in cards:
    name = entry['key']
    card = entry['data']

    # Preserve card-specific data before resetting shared template values.
    specific = {
        'frames': copy.deepcopy(card.get('frames', [])),
        'artSource': card.get('artSource'),
        'artX': card.get('artX'), 'artY': card.get('artY'), 'artZoom': card.get('artZoom'),
        'artRotate': card.get('artRotate', '0'), 'onload': card.get('onload'),
        'text': copy.deepcopy(card.get('text', {})),
    }

    for k in TOP_LEVEL_FROM_DEREVI:
        card[k] = copy.deepcopy(derevi[k])

    # Restore only genuinely card-specific top-level values.
    card['frames'] = specific['frames']
    card['artSource'] = specific['artSource']
    card['artX'], card['artY'], card['artZoom'], card['artRotate'] = specific['artX'], specific['artY'], specific['artZoom'], specific['artRotate']
    card['onload'] = None if name in MANUAL_CROP else AUTO_FIT

    # Every text box begins as an exact copy of Derevi's geometry/style.
    old_text = specific['text']
    new_text = {}
    for box in ('mana','title','type','rules','pt'):
        new_text[box] = copy.deepcopy(derevi['text'][box])
        raw = old_text.get(box, {}).get('text', '')
        cleaned = clean_visible_text(raw)
        if raw != cleaned:
            changes.append(f'{name}: normalized punctuation in {box}')
        for ch in raw:
            if ord(ch) > 127:
                unicode_before.append((name, box, ch, f'U+{ord(ch):04X}'))
        new_text[box]['text'] = cleaned

    # Allowed minor text-box differences.
    mana_count = len(re.findall(r'\{[^{}]+\}', new_text['mana']['text']))
    new_text['title']['width'] = (1680 - 95 * mana_count) / card['width']
    new_text['type']['width'] = 1560 / card['width']
    # Rules font size is allowed to shrink for longer rules; all other rules-box numbers come from Derevi.
    if 'size' in old_text.get('rules', {}):
        new_text['rules']['size'] = old_text['rules']['size']

    card['text'] = new_text

# Specific Academy Rector sanity checks requested by the user.
academy = by_name['Academy Rector']['data']
assert academy['text']['type']['text'] == 'Creature - Human Cleric', academy['text']['type']['text']
assert '\u2014' not in academy['text']['type']['text'] and '\u2013' not in academy['text']['type']['text']

# Verify all visible text is ASCII now. The footer intentionally retains its project bullet/artist glyph from Derevi.
remaining_non_ascii = []
for entry in cards:
    for box in ('mana','title','type','rules','pt'):
        text = entry['data']['text'][box].get('text', '')
        for ch in text:
            if ord(ch) > 127:
                remaining_non_ascii.append((entry['key'], box, ch, f'U+{ord(ch):04X}'))
assert not remaining_non_ascii, f'Non-ASCII visible text remains: {remaining_non_ascii[:20]}'

# Verify text geometry is Derevi-derived except for the two explicit width rules and rules font size.
for entry in cards:
    card = entry['data']
    for box in ('mana','title','type','rules','pt'):
        for key, value in derevi['text'][box].items():
            if key == 'text':
                continue
            if box == 'title' and key == 'width':
                continue
            if box == 'type' and key == 'width':
                continue
            if box == 'rules' and key == 'size':
                continue
            assert card['text'][box].get(key) == value, f"{entry['key']} {box}.{key} differs from Derevi"

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

# Persist the typography rule alongside the other project rules.
style = STYLE.read_text(encoding='utf-8')
section = """
## Typography / character safety
- Use Derevi's text-box geometry as the canonical template for every card; only card-specific text, title width, and rules font size should normally differ.
- Visible card text must use ASCII punctuation for Card Conjurer compatibility.
- Use a normal hyphen with spaces (` - `) instead of em/en dashes in type lines and ability labels.
- Use straight apostrophes (`'`) and straight double quotes (`\"`), not smart/curly quotes.
- Do not allow replacement/square characters in title, mana, type, rules, or power/toughness text.
"""
if '## Typography / character safety' not in style:
    STYLE.write_text(style.rstrip() + '\n' + section, encoding='utf-8')

# Add audit results to sync status.
STATUS.write_text(
    '# Derevi proxy sync status\n\n'
    f'- Card Conjurer entries audited: **{len(cards)}**\n'
    '- Visible text fields with non-ASCII characters remaining: **0**\n'
    '- Cards whose text-box geometry is not Derevi-derived: **0**\n'
    '- Custom art references checked by prior sync: **complete**\n\n'
    '## Typography normalization\n'
    '- Em/en/minus dashes in visible text were normalized to a plain hyphen.\n'
    '- Smart quotes/apostrophes and unusual spaces were normalized to ASCII equivalents.\n'
    '- Academy Rector type line is now `Creature - Human Cleric`.\n'
    f'- Visible non-ASCII characters found before normalization: **{len(unicode_before)}**.\n'
    f'- Text fields changed by punctuation normalization: **{len(changes)}**.\n',
    encoding='utf-8'
)

print(f'Normalized {len(cards)} cards against Derevi.')
print(f'Found {len(unicode_before)} non-ASCII visible characters before normalization.')
for row in unicode_before:
    print('UNICODE', *row)
print(f'Changed {len(changes)} text fields.')
for c in changes:
    print('CHANGE', c)
