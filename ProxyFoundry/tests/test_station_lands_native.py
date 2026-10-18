"""Render both reported Planet lands using real art and native Station frames."""
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
    reason='Opt-in real Station land rendering',
)
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('name',['adagia','susur'])
@pytest.mark.parametrize('custom',[False,True],ids=['scryfall','custom-art'])
def test_station_land_renders_with_normal_station_frame(tmp_path,name,custom):
    from playwright.sync_api import sync_playwright
    card=json.loads((ROOT/'tests/fixtures/station_lands'/(name+'.json')).read_text(encoding='utf-8'))
    image=Image.new('RGB',(1200,1600),'#284050' if custom else '#9d784f')
    if custom:
        from PIL import ImageDraw
        ImageDraw.Draw(image).rectangle((0,0,160,1600),fill='#a06030')
    buffer=io.BytesIO();image.save(buffer,'PNG');art=buffer.getvalue()
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(card).encode(),'application/json',{}
        return original(url)
    net.transport=remote;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    asset=ingest_image(store,art)
    deck=app.ws.create({'name':'Station land regression','source':[{'id':card['id']}],
        'settings':{'symbols':rarity_variants(store,asset['id']),'backAsset':asset['id']}})
    if custom:
        deck['cards'][0]['faces'][0]['artOverride']=asset['id']
        deck['cards'][0]['faces'][0]['artistOverride']='Station test artist'
        deck['cards'][0]['faces'][0]['semanticOverrides']={'nickname':'French Mistake Soundstage'}
        deck=store.put('decks',deck,deck['revision'])
    deck=app.ws.prepare(deck['id'])
    assert not [f['error'] for c in deck['cards'] for f in c['faces'] if f.get('error')]
    with sync_playwright() as playwright:
        # Match the desktop renderer on Windows; hidden headless canvas exports can stall native scripts.
        browser=playwright.chromium.launch(headless=os.name!='nt')
        page=browser.new_page(viewport={'width':1200,'height':900})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(server.origin+'/#deck/'+deck['id'])
            page.locator('#generate-deck').wait_for();page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=180000)
            ready=app.ws.deck(deck['id'])
            assert ready['status']=='ready',{'errors':errors,'activity':page.locator('#activity-log').text_content()}
            assert '/img/frames/station/a.png' in app.runtime.requested
            assert '/img/frames/station/L.png' not in app.runtime.requested
            compiled=ready['cards'][0]['faces'][0]['compiled']
            assert compiled['data']['text']['pt']['text']==''
            rendered=store.render_get(compiled['renderKey'])
            output=Image.open(store.asset_path(rendered['asset_id']))
            assert output.size==(2010,2814)
            if custom:
                assert any(f.get('name')=='Station Textbox Cutout' for f in compiled['data']['frames'])
                #An opaque/doubled textbox washes this dark artwork to white.
                assert output.convert('RGB').getpixel((1800,1860))[0]<220
            evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
            output.thumbnail((603,844));output.save(evidence/('station_land_'+name+('_custom' if custom else '')+'.png'))
            assert not errors,errors
        finally:
            browser.close();server.shutdown();server.server_close();app.close()
