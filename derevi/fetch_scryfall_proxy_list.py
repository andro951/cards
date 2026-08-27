import json, urllib.request
from pathlib import Path

DECK_ID = 'cac4a3fa-84f8-4b8e-b946-0d8a8086fd9d'
UA = 'andro951-cardconjurer-sync/1.0'
HEADERS = {'User-Agent': UA, 'Accept': 'application/json;q=0.9,*/*;q=0.8'}
ROOT = Path(__file__).resolve().parent


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))

# One request only: the deck JSON export contains card digests with the data we need.
url = f'https://api.scryfall.com/decks/{DECK_ID}/export/json'
raw = get_json(url)
(ROOT / 'scryfall_proxy_export.json').write_text(json.dumps(raw, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

found = {}

def consider(obj):
    if not isinstance(obj, dict):
        return
    name = obj.get('name')
    if not name:
        return
    # Scryfall deck exports use card_digest objects. Be permissive about shape changes.
    if obj.get('object') == 'card_digest' or any(k in obj for k in ('mana_cost', 'type_line', 'oracle_id')):
        found.setdefault(name, {
            'name': name,
            'mana_cost': obj.get('mana_cost', ''),
            'type_line': obj.get('type_line', ''),
            'oracle_text': obj.get('oracle_text', ''),
            'power': obj.get('power'),
            'toughness': obj.get('toughness'),
            'colors': obj.get('colors', []),
            'color_identity': obj.get('color_identity', []),
            'layout': obj.get('layout', ''),
            'oracle_id': obj.get('oracle_id', ''),
            'scryfall_uri': obj.get('scryfall_uri', ''),
        })


def walk(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get('card_digest'), dict):
            consider(obj['card_digest'])
        consider(obj)
        for value in obj.values():
            walk(value)
    elif isinstance(obj, list):
        for value in obj:
            walk(value)

walk(raw)
cards = list(found.values())
(ROOT / 'scryfall_proxy_cards.json').write_text(json.dumps(cards, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
(ROOT / 'scryfall_proxy_decklist.txt').write_text('\n'.join('1 ' + c['name'] for c in cards) + '\n', encoding='utf-8')
print(f'Fetched {len(cards)} Scryfall checklist cards. Derevi remains an intentional extra in the Card Conjurer save.')
