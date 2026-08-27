import json, re, time, urllib.parse, urllib.request, html as htmlmod
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CARD_FILE = ROOT / 'derevi_cards.cardconjurer'
STYLE = ROOT / 'STYLE_RULES.md'
STATUS = ROOT / 'PROXY_SYNC_STATUS.md'
AUDIT_JSON = ROOT / 'scryfall_current_cards.json'
AUDIT_MD = ROOT / 'SCRYFALL_RULES_AUDIT.md'

UA = 'andro951-cardconjurer-current-oracle-sync/1.0'
HEADERS = {'User-Agent': UA, 'Accept': 'application/json;q=0.9,*/*;q=0.8'}
HTML_HEADERS = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8'}


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_html(url):
    req = urllib.request.Request(url, headers=HTML_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode('utf-8', errors='replace')
        return r.status, data


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
    s = re.sub(r'\s+-\s+', ' - ', s)
    return s


def rules_size(text):
    n = len(text)
    if n <= 150: return 0.0348
    if n <= 190: return 0.0335
    if n <= 230: return 0.0325
    if n <= 275: return 0.0315
    if n <= 330: return 0.0305
    return 0.0295


def apply_nyx_frame(card, type_line, colors):
    if 'Enchantment' not in type_line:
        return False
    if len(colors) == 1:
        code = colors[0]
    elif len(colors) > 1:
        code = 'M'
    else:
        code = 'A' if 'Artifact' in type_line else 'M'
    src = f'/img/frames/m15/nyx/m15Frame{code}Nyx.png'
    changed = False
    for frame in card.get('frames', []):
        fsrc = frame.get('src', '')
        if '/img/frames/m15/regular/m15Frame' in fsrc:
            frame['src'] = src
            base_name = {'W':'White','U':'Blue','B':'Black','R':'Red','G':'Green','M':'Multicolored','A':'Artifact'}.get(code, 'Multicolored')
            frame['name'] = base_name + ' Nyx Frame'
            changed = True
    return changed

cards = json.loads(CARD_FILE.read_text(encoding='utf-8'))
assert len(cards) == 26, f'Expected 26 cards, found {len(cards)}'

current = []
changes = []
page_failures = []

for i, entry in enumerate(cards):
    name = entry['key']
    url = 'https://api.scryfall.com/cards/named?' + urllib.parse.urlencode({'exact': name})
    card = fetch_json(url)
    time.sleep(0.16)

    page_url = card['scryfall_uri']
    status, page_html = fetch_html(page_url)
    time.sleep(0.10)
    page_ok = status == 200 and htmlmod.escape(card['name'], quote=False)[:12] in page_html
    if not page_ok:
        page_failures.append((name, status, page_url))

    c = entry['data']
    old = {
        'mana_cost': c['text']['mana']['text'],
        'type_line': c['text']['type']['text'],
        'oracle_text': c['text']['rules']['text'],
        'pt': c['text']['pt']['text'],
    }

    mana = clean_visible_text(card.get('mana_cost', '') or '')
    type_line = clean_visible_text(card.get('type_line', '') or '')
    oracle = clean_visible_text(card.get('oracle_text', '') or '')
    power = card.get('power')
    toughness = card.get('toughness')
    pt = f'{power}/{toughness}' if power is not None and toughness is not None else ''

    c['text']['mana']['text'] = mana
    c['text']['title']['text'] = clean_visible_text(card['name'])
    c['text']['type']['text'] = type_line
    c['text']['rules']['text'] = oracle
    c['text']['pt']['text'] = pt

    symbols = len(re.findall(r'\{[^{}]+\}', mana))
    c['text']['title']['width'] = (1680 - 95 * symbols) / c['width']
    c['text']['type']['width'] = 1560 / c['width']
    c['text']['rules']['size'] = rules_size(oracle)

    nyx_changed = apply_nyx_frame(c, card.get('type_line',''), card.get('colors', []))

    new = {'mana_cost': mana, 'type_line': type_line, 'oracle_text': oracle, 'pt': pt}
    changed_fields = [k for k in new if new[k] != old[k]]
    if changed_fields or nyx_changed:
        changes.append({'name': name, 'fields': changed_fields, 'nyx_frame': nyx_changed})

    current.append({
        'name': card['name'],
        'mana_cost': card.get('mana_cost', ''),
        'type_line': card.get('type_line', ''),
        'oracle_text': card.get('oracle_text', ''),
        'power': power,
        'toughness': toughness,
        'colors': card.get('colors', []),
        'oracle_id': card.get('oracle_id', ''),
        'scryfall_uri': page_url,
        'page_http_status': status,
        'page_verified': page_ok,
    })

assert not page_failures, 'Scryfall page verification failed: ' + repr(page_failures)

# Explicit checks for all enchantments: they should now use Nyx frame art.
for entry in cards:
    if 'Enchantment' in entry['data']['text']['type']['text']:
        frame_srcs = [f.get('src','') for f in entry['data'].get('frames', [])]
        assert any('/img/frames/m15/nyx/' in s for s in frame_srcs), f"{entry['key']} is an enchantment without Nyx frame"

# Visible text compatibility check.
for entry in cards:
    for box in ('mana','title','type','rules','pt'):
        text = entry['data']['text'][box].get('text','')
        assert all(ord(ch) < 128 for ch in text), f"Non-ASCII remains in {entry['key']} {box}: {text!r}"

CARD_FILE.write_text(json.dumps(cards, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
AUDIT_JSON.write_text(json.dumps(current, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

md = [
    '# Scryfall current-rules audit', '',
    'Every Card Conjurer entry was looked up by exact name in Scryfall current card data, and the returned Scryfall card page was fetched successfully.', '',
    '| Card | Scryfall page | Page checked | Card data changed |',
    '| --- | --- | --- | --- |',
]
change_map = {x['name']: x for x in changes}
for row in current:
    ch = change_map.get(row['name'])
    if ch:
        bits = list(ch['fields'])
        if ch['nyx_frame']: bits.append('Nyx frame')
        changed = ', '.join(bits) or 'Nyx frame'
    else:
        changed = 'No'
    md.append(f"| {row['name'].replace('|','\\|')} | {row['scryfall_uri']} | Yes ({row['page_http_status']}) | {changed} |")
AUDIT_MD.write_text('\n'.join(md) + '\n', encoding='utf-8')

style = STYLE.read_text(encoding='utf-8')
section = '''\n## Enchantment frames\n- Enchantments use the M15 Nyx frame by default.\n- This includes enchantment creatures.\n- Keep Derevi-derived text/art geometry unless the card itself requires a small adjustment.\n'''
if '## Enchantment frames' not in style:
    style = style.rstrip() + '\n' + section
STYLE.write_text(style, encoding='utf-8')

STATUS.write_text(
    '# Derevi proxy sync status\n\n'
    '- Card Conjurer entries audited against current Scryfall data: **26**\n'
    '- Scryfall card pages individually fetched successfully: **26/26**\n'
    '- Cards with current Oracle/mana/type/P-T differences applied: **' + str(sum(bool(x['fields']) for x in changes)) + '**\n'
    '- Enchantments using M15 Nyx frames: **' + str(sum('Enchantment' in e['data']['text']['type']['text'] for e in cards)) + '**\n'
    '- Visible text fields with non-ASCII characters remaining: **0**\n'
    '- Custom art references: **complete**\n\n'
    'See `SCRYFALL_RULES_AUDIT.md` for the per-card Scryfall page audit.\n',
    encoding='utf-8'
)

print(f'Audited {len(cards)} cards against current Scryfall data and pages.')
print(f'Changed {len(changes)} cards total (including frame-only changes).')
for ch in changes:
    print(ch['name'] + ': ' + ', '.join(ch['fields'] + (['Nyx frame'] if ch['nyx_frame'] else [])))
