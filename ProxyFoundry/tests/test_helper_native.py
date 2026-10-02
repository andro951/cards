"""Render the reported helper cards using their complete selected-printing scans."""
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
    reason='Opt-in real Helper card rendering',
)
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('custom',[False,True],ids=['scryfall-scans','custom-art'])
def test_helper_trackers_render_all_four_faces(tmp_path,custom):
    from playwright.sync_api import sync_playwright
    cards=[json.loads((ROOT/'tests/fixtures/helper_cards'/(name+'.json')).read_text(encoding='utf-8')) for name in ['experience','poison-counter','day']]
    records={card['id']:card for card in cards}
    image=Image.new('RGB',(1200,1600),'#9d784f')
    buffer=io.BytesIO();image.save(buffer,'PNG');art=buffer.getvalue()
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(records[url.rsplit('/',1)[-1]]).encode(),'application/json',{}
        return original(url)
    net.transport=remote;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    asset=ingest_image(store,art)
    settings={'symbols':rarity_variants(store,asset['id']),'backAsset':asset['id'],'artist':'Fixture Artist'}
    if custom:
        settings['source']={'mode':'local','localFiles':{name:asset['id'] for name in ['119_experience','120_poison_counter','121_day','122_night']}}
    deck=app.ws.create({'name':'Helper tracker regression','source':[{'id':card['id']} for card in cards],
        'settings':settings})
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
            faces=[face for card in ready['cards'] for face in card['faces']]
            from foundry.orders import Orders
            day=ready['cards'][2]
            pair=next(item for item in Orders(app.ws).plan([ready['id']],True)['cards'] if item['name']==day['name'])
            assert pair['frontAsset']==store.render_get(day['faces'][0]['compiled']['renderKey'])['asset_id']
            assert pair['backAsset']==store.render_get(day['faces'][1]['compiled']['renderKey'])['asset_id']
            assert [face['name'] for face in faces]==['Experience','Poison Counter','Day','Night']
            for face in faces:
                compiled=face['compiled']
                assert compiled['recipe']==('helper_full_art' if custom else 'helper_scan')
                assert bool(compiled['data']['frames'])==custom
                if custom:
                    assert compiled['data']['text']['title']['text']==face['name']
                    assert compiled['data']['text']['rules']['text']
                rendered=store.render_get(compiled['renderKey'])
                output=Image.open(store.asset_path(rendered['asset_id']))
                assert output.size==(2010,2814)
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                output.thumbnail((603,844));output.save(evidence/(('helper_custom_' if custom else 'helper_')+face['name'].lower().replace(' ','_')+'.png'))
            assert not errors,errors
        finally:
            browser.close();server.shutdown();server.server_close();app.close()
