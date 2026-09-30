"""Render a Scryfall emblem with CardConjurer's genuine Emblem frame."""
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
    reason='Opt-in real Emblem rendering',
)
ROOT=Path(__file__).resolve().parents[1]

def test_scryfall_emblem_renders_with_native_frame(tmp_path):
    from playwright.sync_api import sync_playwright
    card={
        'object':'card','id':'1c97e5b2-a024-4aa7-a9b8-45f441aad138',
        'name':'Ajani, Adversary of Tyrants Emblem','layout':'emblem',
        'type_line':'Emblem — Ajani','rarity':'common','colors':[],
        'mana_cost':'','artist':'Victor Adame Minguez',
        'oracle_text':'At the beginning of your end step, create three 1/1 white Cat creature tokens with lifelink.',
        'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/1/c/emblem-fixture.jpg'},
    }
    image=Image.new('RGB',(1200,1600),'#9d784f')
    buffer=io.BytesIO();image.save(buffer,'PNG');art=buffer.getvalue()
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(card).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return art,'image/png',{}
        return original(url)
    net.transport=remote;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    asset=ingest_image(store,art)
    deck=app.ws.create({'name':'Emblem regression','source':[{'id':card['id']}],
        'settings':{'symbols':rarity_variants(store,asset['id']),'backAsset':asset['id']}})
    deck=app.ws.prepare(deck['id'])
    assert not [f['error'] for c in deck['cards'] for f in c['faces'] if f.get('error')]
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
            assert '/img/frames/token/emblem/frame.png' in app.runtime.requested
            compiled=ready['cards'][0]['faces'][0]['compiled']
            rendered=store.render_get(compiled['renderKey'])
            output=Image.open(store.asset_path(rendered['asset_id']))
            assert output.size==(2010,2814)
            evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
            output.thumbnail((603,844));output.save(evidence/'emblem_ajani.png')
            assert not errors,errors
        finally:
            browser.close();server.shutdown();server.server_close();app.close()
