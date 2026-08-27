import json, time, urllib.parse, urllib.request
from pathlib import Path

DECK_ID = 'cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d'
UA = 'andro951-cardconjurer-sync/1.0'
HEADERS = {'User-Agent': UA, 'Accept': 'application/json;q=0.9,*/*;q=0.8'}
ROOT = Path(__file__).resolve().parent


def get_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


def get_json(url):
    return json.loads(get_text(url))

# Scryfall deck plaintext gives a stable, easy-to-parse checklist.
text_url = f'https://api.scryfall.com/decks/{DECK_ID}/export/text'
deck_text = get_text(text_url)
(ROOT / 'scryfall_proxy_decklist.txt').write_text(deck_text, encoding='utf-8')

names = []
for raw in deck_text.splitlines():
    line = raw.strip()
    if not line or line.lower() in {'sideboard', 'commander'} or line.startswith('//'):
        continue
    if line.lower().startswith('sideboard'):
        continue
    parts = line.split(' ', 1)
    if len(parts) == 2 and parts[0].rstrip('x').isdigit():
        name = parts[1].strip()
    else:
        name = line
    # Strip common printing annotations when present.
    if ' (' in name and name.rsplit(' (', 1)[1].split(')', 1)[0].isalnum():
        name = name.rsplit(' (', 1)[0].strip()
    if name and name not in names:
        names.append(name)

# Derevi is intentionally an extra proxy outside the Scryfall checklist.
if 'Derevi, Empyrial Tactician' not in names:
    names.append('Derevi, Empyrial Tactician')

cards = []
for name in names:
    url = 'https://api.scryfall.com/cards/named?exact=' + urllib.parse.quote(name)
    card = get_json(url)
    cards.append({
        'name': card.get('name', name),
        'mana_cost': card.get('mana_cost', ''),
        'type_line': card.get('type_line', ''),
        'oracle_text': card.get('oracle_text', ''),
        'power': card.get('power'),
        'toughness': card.get('toughness'),
        'colors': card.get('colors', []),
        'color_identity': card.get('color_identity', []),
        'layout': card.get('layout', ''),
        'oracle_id': card.get('oracle_id', ''),
        'scryfall_uri': card.get('scryfall_uri', ''),
    })
    time.sleep(0.12)

(ROOT / 'scryfall_proxy_cards.json').write_text(json.dumps(cards, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(f'Fetched {len(cards)} cards including Derevi extra.')
