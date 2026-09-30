"""Render both Scryfall Art Series faces as complete selected-printing scans."""
import io,json,os,threading
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants

pytestmark=pytest.mark.skipif(
    os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',
    reason='Opt-in real Art Series rendering',
)
ROOT=Path(__file__).resolve().parents[1]

def test_art_series_native_renders_both_full_scans(tmp_path):
    from playwright.sync_api import sync_playwright
    card={
        'object':'card','id':'c0b5c6bd-6115-4a91-bbc4-6424cba827ef',
        'name':'Art Card // Art Card','layout':'art_series',
        'type_line':'Card // Card','rarity':'common','artist':'Fixture Artist',
        'card_faces':[
            {'name':'Art Card','type_line':'Card','image_uris':{
                'png':'https://cards.scryfall.io/png/front/art-series-fixture.png'}},
            {'name':'Art Card','type_line':'Card','image_uris':{
                'png':'https://cards.scryfall.io/png/back/art-series-fixture.png'}},
        ],
    }
    def png(color):
        image=Image.new('RGB',(745,1040),color)
        buffer=io.BytesIO();image.save(buffer,'PNG');return buffer.getvalue()
    front=png('#d05a35');back=png('#2974b9')
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(card).encode(),'application/json',{}
        if 'cards.scryfall.io/png/front/' in url:return front,'image/png',{}
        if 'cards.scryfall.io/png/back/' in url:return back,'image/png',{}
        return original(url)
    net.transport=remote;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    symbol=ingest_image(store,front)
    deck=app.ws.create({'name':'Art Series regression','source':[{'id':card['id']}],
        'settings':{'symbols':rarity_variants(store,symbol['id']),'backAsset':symbol['id']}})
    deck=app.ws.prepare(deck['id'])
    assert len(deck['cards'][0]['faces'])==2
    assert not [f['error'] for f in deck['cards'][0]['faces'] if f.get('error')]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1200,'height':900})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(server.origin+'/#deck/'+deck['id'])
            page.locator('#generate-deck').wait_for();page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=180000)
            ready=app.ws.deck(deck['id'])
            assert ready['status']=='ready',{'errors':errors,'activity':page.locator('#activity-log').text_content()}
            evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
            for index,face in enumerate(ready['cards'][0]['faces']):
                compiled=face['compiled'];rendered=store.render_get(compiled['renderKey'])
                output=Image.open(store.asset_path(rendered['asset_id']))
                assert output.size==(2010,2814)
                expected=(208,90,53) if index==0 else (41,116,185)
                assert output.getpixel((1005,1407))[:3]==expected
                output.thumbnail((603,844));output.save(evidence/f'art_series_{index}.png')
            assert not errors,errors
        finally:
            browser.close();server.shutdown();server.server_close();app.close()
