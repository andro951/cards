"""Render a noncreature token using the genuine CardConjurer token pack."""
import io,json,os,threading
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants
from test_pipeline import workspace

pytestmark=pytest.mark.skipif(
    os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',
    reason='Opt-in real Treasure token rendering',
)
ROOT=Path(__file__).resolve().parents[1]


def test_converted_artifact_tokens_render_with_and_without_crown_and_nickname(workspace):
    from foundry.compiler import semantic
    from playwright.sync_api import sync_playwright
    store,art,settings=workspace;app=App(store)
    app.runtime_assets.update([art,*settings['symbols'].values()])
    card={'name':'Sol Ring','type_line':'Artifact','mana_cost':'{1}',
          'oracle_text':'{T}: Add {C}{C}.','colors':[],'rarity':'uncommon'}
    variants=[]
    for nickname in ('','Ring of Death'):
        for legendary in (False,True):
            sem=semantic(card,card);sem['nickname']=nickname
            comp=app.ws.compiler.compile_face(card,card,0,{'semanticOverrides':{'nickname':nickname}},settings,art)
            comp=app.ws._apply_token_spec(comp,{'force_legendary':legendary,'nonlegendary':not legendary},art,'Converted token',False,sem)
            variants.append(comp['data'])
    server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.goto(server.origin)
                page.set_default_timeout(150000)
                result=page.evaluate('''async ({origin,variants})=>{
                    const frame=document.createElement('iframe');
                    frame.src=origin+'/runtime/host?parent='+encodeURIComponent(location.origin)+'&worker=1';
                    let readyResolve,pending;
                    const ready=new Promise(resolve=>readyResolve=resolve);
                    window.addEventListener('message',event=>{
                        if(event.origin!==origin||event.source!==frame.contentWindow)return;
                        const message=event.data;
                        if(message.type==='ready')readyResolve();
                        if(message.type==='failed')(pending||readyResolve)({error:message.error,stack:message.stack});
                        if(message.type==='rendered')pending({blob:message.blob});
                    });
                    document.body.append(frame);
                    const startup=await ready;
                    if(startup?.error)return [startup];
                    const results=[];
                    for(let index=0;index<variants.length;index++){
                        const rendered=await new Promise(resolve=>{
                            pending=resolve;
                            frame.contentWindow.postMessage({source:'pf-app',type:'render',key:String(index),data:variants[index]},origin);
                        });
                        if(rendered.error){results.push(rendered);continue;}
                        const bitmap=await createImageBitmap(rendered.blob);
                        results.push({width:bitmap.width,height:bitmap.height,bytes:rendered.blob.size});
                        bitmap.close();
                    }
                    frame.remove();return results;
                }''',{'origin':app.runtime_origin,'variants':variants})
                assert len(result)==4,result
                for rendered in result:
                    assert 'error' not in rendered,rendered
                    assert (rendered['width'],rendered['height'])==(2010,2814)
                    assert rendered['bytes']>10000
            finally:browser.close()
    finally:server.shutdown();server.server_close();app.close()

def test_noncreature_token_renders_with_empty_power_toughness(tmp_path):
    from playwright.sync_api import sync_playwright
    card={
        'object':'card','id':'90000000-0000-4000-8000-000000000002',
        'name':'Treasure','layout':'token',
        'type_line':'Token Artifact \u2014 Treasure','rarity':'common','colors':[],
        'mana_cost':'','artist':'Treasure fixture',
        'oracle_text':'{T}, Sacrifice this token: Add one mana of any color.',
        'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/1/c/treasure-fixture.jpg'},
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
    deck=app.ws.create({'name':'Treasure regression','source':[{'id':card['id']}],
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
            assert '/img/frames/token/regular/tokenFrameARegular.png' in app.runtime.requested
            compiled=ready['cards'][0]['faces'][0]['compiled']
            assert compiled['data']['text']['pt']['text']==''
            rendered=store.render_get(compiled['renderKey'])
            output=Image.open(store.asset_path(rendered['asset_id']))
            assert output.size==(2010,2814)
            evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
            output.thumbnail((603,844));output.save(evidence/'token_treasure.png')
            previous_key=compiled['renderKey']
            for choice,label,version in [('token-full-art','Modern full-art token','tokenRegular'),('token-borderless','Modern borderless token','tokenTextlessBorderless')]:
                if page.locator('#modal-close').count():page.locator('#modal-close').click()
                page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
                page.locator('[data-frame-group="token"]').click()
                page.get_by_role('button',name='Select '+label,exact=True).click()
                with page.expect_response(lambda response:response.url.endswith('/api/render-sessions')):
                    page.click('#save-generate')
                page.locator('.badge.ready,.toast.error').first.wait_for(timeout=180000)
                ready=app.ws.deck(deck['id'])
                assert ready['status']=='ready',page.locator('#activity-log').text_content()
                compiled=ready['cards'][0]['faces'][0]['compiled']
                assert ready['settings']['templateRules']['token']==choice
                assert compiled['data']['version']==version and compiled['renderKey']!=previous_key
                rendered=store.render_get(compiled['renderKey'])
                assert rendered is not None
                output=Image.open(store.asset_path(rendered['asset_id']))
                assert output.size==(2010,2814)
                output.thumbnail((603,844));output.save(evidence/('token_treasure_'+choice+'.png'))
                previous_key=compiled['renderKey']
            assert not errors,errors
        finally:
            browser.close();server.shutdown();server.server_close();app.close()


def test_token_style_gallery_renders_native_assets(tmp_path):
    from playwright.sync_api import sync_playwright
    from PIL import ImageDraw
    image=Image.new('RGB',(1200,1600),'#2c6475');draw=ImageDraw.Draw(image)
    for y in range(0,1600,80):draw.rectangle((0,y,1200,y+35),fill=(50+y//20,100,130))
    draw.ellipse((280,250,920,1000),fill='#d6ad68')
    buffer=io.BytesIO();image.save(buffer,'PNG');art=buffer.getvalue()
    cards={};specs=[]
    for style in ('token-classic','token-full-art','token-borderless'):
        for short in (True,False):
            ident=f'90000000-0000-4000-8000-{len(cards)+20:012d}'
            card={'object':'card','id':ident,'name':'Bird' if short else 'Treasure',
                  'layout':'token','type_line':'Token Creature — Bird' if short else 'Token Artifact — Treasure',
                  'rarity':'common','colors':['U'] if short else [],'mana_cost':'','artist':'Token fixture',
                  'oracle_text':'Flying' if short else '{T}, Sacrifice this token: Add one mana of any color.',
                  'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/1/c/token-gallery.jpg'}}
            if short:card.update(power='1',toughness='1')
            cards[ident]=card;specs.append((style,short,ident))
    store=Store(tmp_path/'workspace');net=Network(store);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:
            ident=url.rsplit('/',1)[-1].split('?')[0]
            return json.dumps(cards[ident]).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return art,'image/png',{}
        return original(url)
    net.transport=remote;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    asset=ingest_image(store,art);symbols=rarity_variants(store,asset['id'])
    decks=[]
    for style,short,ident in specs:
        deck=app.ws.create({'name':style+(' short' if short else ' rules'),'source':[{'id':ident}],
            'settings':{'symbols':symbols,'backAsset':asset['id'],'templateRules':{'token':style}}})
        deck=app.ws.prepare(deck['id'])
        assert not [f['error'] for c in deck['cards'] for f in c['faces'] if f.get('error')]
        decks.append((style,short,deck))
    outputs=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1200,'height':900});errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            for style,short,deck in decks:
                page.goto(server.origin+'/#deck/'+deck['id'])
                page.locator('#generate-deck').wait_for();page.click('#generate-deck')
                page.locator('.badge.ready,.toast.error').first.wait_for(timeout=180000)
                ready=app.ws.deck(deck['id'])
                assert ready['status']=='ready',page.locator('#activity-log').text_content()
                compiled=ready['cards'][0]['faces'][0]['compiled']
                rendered=store.render_get(compiled['renderKey'])
                output=Image.open(store.asset_path(rendered['asset_id'])).convert('RGB')
                assert output.size==(2010,2814)
                output.thumbnail((402,563));outputs.append(output.copy())
                if page.locator('#modal-close').count():page.locator('#modal-close').click()
            assert not errors,errors
            gallery=Image.new('RGB',(402*3,563*2))
            for i,output in enumerate(outputs):gallery.paste(output,((i//2)*402,(i%2)*563))
            evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
            gallery.save(evidence/'token_styles_gallery.jpg')
        finally:
            browser.close();server.shutdown();server.server_close();app.close()
