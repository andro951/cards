"""Actual upstream masks and final PNGs for repaired component families."""
import json,os,threading
from pathlib import Path
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants
from tests.test_native_deck import artwork
from tests.test_frame_components import KINDS,example
pytestmark=pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1' or os.environ.get('PF_BROWSER')!='1',reason='Opt-in native rendering')

def test_repaired_native_component_render(tmp_path):
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport;raw=artwork();byid={}
    def transport(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(byid[url.rsplit('/',1)[-1]]).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return raw,'image/png',{}
        return original(url)
    net.transport=transport;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    art=ingest_image(store,raw);symbols=rarity_variants(store,art['id'])
    deck=app.ws.new_deck('Repaired components');cards=[]
    for i,kind in enumerate(KINDS):
        c,face,override=example(kind,['U','R'])
        c['id']=f'11111111-1111-4111-8111-{i:012d}';byid[c['id']]=c
        face['image_uris']={'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/fixture.jpg'}
        cards.append({'id':str(i),'name':c['name'],'quantity':1,'scryfall':c,'faces':[{'id':str(i),'name':face['name'],'index':0,**override}]})
    app.ws.store.put('decks',{**deck,'settings':app.ws.validate_settings({'symbols':symbols,'backAsset':art['id']}),'cards':cards},deck['revision'])
    output=Path(__file__).resolve().parents[1]/'test-results/frame-components';output.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=os.name!='nt');page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#deck/'+deck['id']);page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=480000)
            current=app.ws.deck(deck['id'])
            assert current['status']=='ready',page.locator('#activity-log').text_content()
            for kind,card in zip(KINDS,current['cards']):
                comp=card['faces'][0]['compiled'];render=store.render_get(comp['renderKey']);assert render
                image=Image.open(store.asset_path(render['asset_id']));assert image.size==(comp['data']['width'],comp['data']['height'])
                image.thumbnail((400,560));image.save(output/(kind+'.png'))
            for mask in ('/img/frames/planeswalker/regular/planeswalkerMaskPinline.png','/img/frames/planeswalker/tall/planeswalkerTallMaskPinline.png','/img/frames/proxy-foundry/masks/class-pinline.png','/img/frames/m15/battle/maskPinline.png','/img/frames/m15/flip/pinline.svg'):
                assert mask in app.runtime.requested,mask
            assert not errors,errors
        finally:
            (output/'diagnostics.json').write_text(json.dumps(app.runtime.diagnostic(),indent=2),encoding='utf-8')
            browser.close();server.shutdown();server.server_close();app.close()
