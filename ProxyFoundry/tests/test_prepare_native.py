"""Render a blue Prepare card with actual pinned CardConjurer frame assets."""
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
    reason='Opt-in real Prepare rendering',
)
ROOT=Path(__file__).resolve().parents[1]

def test_harmonized_trio_native_prepare_frame_is_blue(tmp_path):
    from playwright.sync_api import sync_playwright
    card={
        'object':'card','id':'617208ff-dd9b-44fd-a740-d3188081e5cc',
        'name':'Harmonized Trio // Brainstorm','layout':'prepare','rarity':'rare',
        'colors':['U'],'artist':'Fixture Artist',
        'card_faces':[
            {'name':'Harmonized Trio','type_line':'Creature — Merfolk Bard Wizard',
             'mana_cost':'{U}','oracle_text':'{T}, Tap two untapped creatures you control: This creature becomes prepared. (While it’s prepared, you may cast a copy of its spell. Doing so unprepares it.)',
             'power':'1','toughness':'1','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/prepare-fixture.jpg'}},
            {'name':'Brainstorm','type_line':'Instant','mana_cost':'{U}',
             'oracle_text':'Draw three cards, then put two cards from your hand on top of your library in any order.'},
        ],
    }
    picture=Image.new('RGB',(1200,1600),'#639dc5');buffer=io.BytesIO();picture.save(buffer,'PNG');art=buffer.getvalue()
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(card).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return art,'image/png',{}
        return original(url)
    net.transport=remote;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    asset=ingest_image(store,art)
    deck=app.ws.create({'name':'Blue Prepare frame regression','source':[{'id':card['id']}],
        'settings':{'symbols':rarity_variants(store,asset['id']),'backAsset':asset['id']}})
    deck=app.ws.prepare(deck['id'])
    assert not [f['error'] for c in deck['cards'] for f in c['faces'] if f.get('error')]
    frames=deck['cards'][0]['faces'][0]['compiled']['data']['frames']
    assert all(f['src']=='/img/frames/prepare/regular/u.png' for f in frames
               if '/img/frames/prepare/regular/' in f.get('src',''))
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
            assert '/img/frames/prepare/regular/u.png' in app.runtime.requested
            compiled=ready['cards'][0]['faces'][0]['compiled']
            rendered=store.render_get(compiled['renderKey'])
            image=Image.open(store.asset_path(rendered['asset_id']))
            assert image.size==(2010,2814)
            evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
            image.thumbnail((603,844));image.save(evidence/'prepare_harmonized_trio_blue.png')
            assert not errors,errors
        finally:
            browser.close();server.shutdown();server.server_close();app.close()
