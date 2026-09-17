from __future__ import annotations

import io
import json
import shutil
import sys
import threading
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2] / 'ProxyFoundry'
sys.path.insert(0, str(ROOT))

from foundry.images import ingest_image
from foundry.network import Network
from foundry.server import App, LocalServer
from foundry.storage import Store

OUT = ROOT / 'test-results' / 'frame-symbol-render-v2'
WORKSPACE = ROOT / 'test-results' / 'frame-symbol-workspace-v2'
OUT.mkdir(parents=True, exist_ok=True)
if WORKSPACE.exists():
    shutil.rmtree(WORKSPACE)
WORKSPACE.mkdir(parents=True, exist_ok=True)


def png_image(size=(1200, 900), seed=0):
    im = Image.new('RGB', size, (52 + seed * 11, 74 + seed * 7, 93 + seed * 5))
    d = ImageDraw.Draw(im)
    w, h = size
    d.rectangle((0, int(h * .72), w, h), fill=(36 + seed * 9, 55 + seed * 6, 44 + seed * 8))
    d.ellipse((int(w * .24), int(h * .12), int(w * .76), int(h * .64)), fill=(205, 174 - seed * 6, 112 + seed * 7))
    d.ellipse((int(w * .38), int(h * .25), int(w * .62), int(h * .51)), fill=(59, 43, 31))
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()


def solid_black_square(size=512):
    im = Image.new('RGBA', (size, size), (0, 0, 0, 255))
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()


def back_png(size=(1055, 1491)):
    im = Image.new('RGB', size, (25, 25, 25))
    d = ImageDraw.Draw(im); d.rectangle((70, 70, size[0]-70, size[1]-70), outline=(110, 110, 110), width=8)
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()


BASE = {
    'object': 'card', 'layout': 'normal', 'colors': [], 'mana_cost': '', 'rarity': 'rare',
    'set': 'tst', 'artist': 'Test Artist',
}
CARDS = [
    {**BASE,
     'id': '11111111-1111-4111-8111-000000000001', 'oracle_id': '22222222-2222-4222-8222-000000000001',
     'name': 'Sol Ring', 'collector_number': '1', 'type_line': 'Artifact', 'mana_cost': '{1}',
     'oracle_text': '{T}: Add {C}{C}.',
     'image_uris': {'art_crop': 'https://cards.scryfall.io/art_crop/front/a/b/fixture1.png', 'png': 'https://cards.scryfall.io/png/front/a/b/fixture1.png'}},
    {**BASE,
     'id': '11111111-1111-4111-8111-000000000002', 'oracle_id': '22222222-2222-4222-8222-000000000002',
     'name': 'Azorius Chancery', 'collector_number': '2', 'type_line': 'Land',
     'oracle_text': 'Azorius Chancery enters the battlefield tapped.\nWhen Azorius Chancery enters the battlefield, return a land you control to its owner\'s hand.\n{T}: Add {W}{U}.',
     'image_uris': {'art_crop': 'https://cards.scryfall.io/art_crop/front/a/b/fixture2.png', 'png': 'https://cards.scryfall.io/png/front/a/b/fixture2.png'}},
    {**BASE,
     'id': '11111111-1111-4111-8111-000000000003', 'oracle_id': '22222222-2222-4222-8222-000000000003',
     'name': 'Academy Ruins', 'collector_number': '3', 'type_line': 'Legendary Land',
     'oracle_text': '{T}: Add {C}.\n{1}{U}, {T}: Put target artifact card from your graveyard on top of your library.',
     'image_uris': {'art_crop': 'https://cards.scryfall.io/art_crop/front/a/b/fixture3.png', 'png': 'https://cards.scryfall.io/png/front/a/b/fixture3.png'}},
    {**BASE,
     'id': '11111111-1111-4111-8111-000000000004', 'oracle_id': '22222222-2222-4222-8222-000000000004',
     'name': 'Forest', 'collector_number': '4', 'type_line': 'Basic Land — Forest',
     'oracle_text': '({T}: Add {G}.)',
     'image_uris': {'art_crop': 'https://cards.scryfall.io/art_crop/front/a/b/fixture4.png', 'png': 'https://cards.scryfall.io/png/front/a/b/fixture4.png'}},
    {**BASE,
     'id': '11111111-1111-4111-8111-000000000005', 'oracle_id': '22222222-2222-4222-8222-000000000005',
     'name': 'Tropical Island', 'collector_number': '5', 'type_line': 'Land — Forest Island',
     'oracle_text': '({T}: Add {G} or {U}.)',
     'image_uris': {'art_crop': 'https://cards.scryfall.io/art_crop/front/a/b/fixture5.png', 'png': 'https://cards.scryfall.io/png/front/a/b/fixture5.png'}},
]
BY_ID = {c['id']: c for c in CARDS}
ART_BY_URL = {f'fixture{i}.png': png_image(seed=i) for i in range(1, 6)}

store = Store(WORKSPACE)
net = Network(store)
upstream = net._transport


def transport(url):
    if 'api.scryfall.com/cards/' in url:
        ident = url.rsplit('/', 1)[-1]
        return json.dumps(BY_ID[ident]).encode(), 'application/json', {}
    if 'cards.scryfall.io' in url:
        filename = url.rsplit('/', 1)[-1]
        return ART_BY_URL[filename], 'image/png', {}
    return upstream(url)


net.transport = transport
app = App(store, net)
server = LocalServer(app)
threading.Thread(target=server.serve_forever, daemon=True).start()

try:
    symbol = ingest_image(store, solid_black_square())
    back = ingest_image(store, back_png())
    symbols = {r: symbol['id'] for r in ('common', 'uncommon', 'rare', 'mythic')}
    deck = app.ws.create({
        'name': 'Black square frame tests corrected',
        'source': [{'id': c['id'], 'quantity': 1} for c in CARDS],
        'settings': {'symbols': symbols, 'backAsset': back['id']},
    })
    deck = app.ws.prepare(deck['id'])
    prep_errors = [f"{f['name']}: {f['error']}" for c in deck['cards'] for f in c['faces'] if f.get('error')]
    if prep_errors:
        raise RuntimeError('Prepare errors: ' + '; '.join(prep_errors))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        browser_errors = []
        page.on('pageerror', lambda e: browser_errors.append(str(e)))
        try:
            page.goto(server.origin + '/#deck/' + deck['id'])
            page.locator('#generate-deck').wait_for(timeout=120000)
            page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=480000)
            ready = app.ws.deck(deck['id'])
            if ready['status'] != 'ready':
                raise RuntimeError({'status': ready['status'], 'browserErrors': browser_errors,
                                    'activity': page.locator('#activity-log').text_content()})
            if ready['summary']['rendered'] != 5:
                raise RuntimeError('Expected five rendered faces; got ' + str(ready['summary']))
            if browser_errors:
                raise RuntimeError('Browser errors: ' + repr(browser_errors))
        finally:
            browser.close()

    names = {
        'Sol Ring': '01_sol_ring_artifact.png',
        'Azorius Chancery': '02_normal_land_azorius_chancery.png',
        'Academy Ruins': '03_legendary_land_academy_ruins.png',
        'Forest': '04_basic_land_forest.png',
        'Tropical Island': '05_original_dual_land_tropical_island.png',
    }
    manifest = []
    for c in ready['cards']:
        comp = c['faces'][0]['compiled']
        render = store.render_get(comp['renderKey'])
        if not render:
            raise RuntimeError('Missing completed render for ' + c['name'])
        src = store.asset_path(render['asset_id'])
        out = OUT / names[c['name']]
        shutil.copy2(src, out)
        with Image.open(out) as im:
            if im.size != (comp['data']['width'], comp['data']['height']):
                raise RuntimeError(f"Wrong output size for {c['name']}: {im.size}")
        manifest.append({
            'name': c['name'], 'file': out.name, 'group': comp['group'], 'recipe': comp['recipe'],
            'version': comp['data'].get('version'), 'generationVersion': comp.get('generationVersion'),
            'setSymbolX': comp['data'].get('setSymbolX'), 'setSymbolY': comp['data'].get('setSymbolY'),
            'setSymbolYpx': comp['data'].get('setSymbolY') * comp['data'].get('height'),
            'setSymbolZoom': comp['data'].get('setSymbolZoom'),
        })

    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    zip_path = OUT / 'black-square-frame-tests-corrected.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for item in manifest:
            z.write(OUT / item['file'], item['file'])
    with zipfile.ZipFile(zip_path) as z:
        assert len(z.namelist()) == 5, z.namelist()
    print(json.dumps(manifest, indent=2))
finally:
    server.shutdown(); server.server_close(); app.close()
