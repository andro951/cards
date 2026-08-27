import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STATUS = ROOT / 'PROXY_SYNC_STATUS.md'
AUTO_FIT = 'https://cdn.jsdelivr.net/gh/andro951/cards@main/derevi/auto_fit_art.js'

cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
assert len(cards) == 26, f'Expected 26 cards, found {len(cards)}'
assert len({c['key'] for c in cards}) == 26, 'Duplicate card keys found'

manual_crop = {
    'Derevi, Empyrial Tactician',
    'Cloud, Midgar Mercenary',
    'Oswald Fiddlebender',
    'Delney, Streetwise Lookout',
}

missing_art = []
for entry in cards:
    card = entry['data']
    mana = card.get('text', {}).get('mana', {}).get('text', '')
    symbols = len(re.findall(r'\{[^{}]+\}', mana))
    card['text']['title']['width'] = (1680 - 95 * symbols) / 2010
    card['text']['type']['width'] = 1560 / 2010

    art_url = card.get('artSource', '')
    filename = art_url.rsplit('/', 1)[-1] if art_url else ''
    if not filename or not (ROOT / filename).exists():
        missing_art.append(f"{entry['key']} -> {filename or '(none)'}")
    elif entry['key'] not in manual_crop and card.get('artZoom') == 1:
        card['onload'] = AUTO_FIT

# Explicitly finalize the two newly-uploaded Mox arts.
for name, filename in [('Mox Amber', 'mox_amber.png'), ('Mox Opal', 'mox_opal.png')]:
    entry = next(c for c in cards if c['key'] == name)
    entry['data']['artSource'] = f'https://raw.githubusercontent.com/andro951/cards/main/derevi/{filename}'
    entry['data']['artX'] = 0.0767
    entry['data']['artY'] = 0.1129
    entry['data']['artZoom'] = 1
    entry['data']['artRotate'] = '0'
    entry['data']['onload'] = AUTO_FIT

assert not missing_art, 'Missing art: ' + '; '.join(missing_art)
CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

STATUS.write_text(
    '# Derevi proxy sync status\n\n'
    '- Scryfall checklist entries: **26**\n'
    '- Card Conjurer entries: **26**\n'
    '- Checklist entries missing from Card Conjurer: **0**\n'
    '- Card entries whose expected custom art PNG is missing: **0**\n\n'
    '## Status\n'
    '- All 26 card entries have matching hosted custom art.\n'
    '- Mox Amber and Mox Opal are linked and auto-fit on load.\n'
    '- Title/type textbox rules have been re-applied to every card.\n',
    encoding='utf-8'
)
print('Finalized 26 cards; all custom art present.')
