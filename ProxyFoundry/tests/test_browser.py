"""Real HTTP/browser tests. Opt in with PF_BROWSER=1 (CI installs Chromium)."""
from __future__ import annotations
import io,json,os,threading,time,zipfile
from pathlib import Path
import pytest
from playwright.sync_api import expect
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in real Chromium tests')
ROOT=Path(__file__).resolve().parents[1]

def png(size=(900,650),color='#478868'):
    b=io.BytesIO();Image.new('RGB',size,color).save(b,'PNG');return b.getvalue()

def sf(name='A Test Creature',id='11111111-1111-4111-8111-111111111111'):
    return {'object':'card','id':id,'oracle_id':'22222222-2222-4222-8222-222222222222','name':name,'layout':'normal','type_line':'Creature — Elf','colors':['G'],'mana_cost':'{1}{G}',
        'oracle_text':'Vigilance','rarity':'rare','power':'2','toughness':'2','artist':'Original Artist','set':'tst','collector_number':'1',
        'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/test.jpg','png':'https://cards.scryfall.io/png/front/a/b/test.png'}}

@pytest.fixture
def browser_app(tmp_path,request):
    from playwright.sync_api import sync_playwright
    store=Store(tmp_path/'workspace')
    def transport(url):
        if 'api.scryfall.com' in url:
            d=sf()
            if '/search?' in url:d={'data':[d],'has_more':False}
            return json.dumps(d).encode(),'application/json',{}
        return png(),'image/png',{}
    app=App(store,Network(store,transport=transport,sleeper=lambda _:None));server=LocalServer(app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        executable=os.environ.get('PF_BROWSER_EXECUTABLE')
        browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
        context=browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(server.origin);page.locator('#import-deck').wait_for()
        yield app,server,page,errors
        (ROOT/'test-results').mkdir(exist_ok=True)
        name=request.node.name
        page.screenshot(path=str(ROOT/'test-results'/(name+'.png')),full_page=True)
        (ROOT/'test-results'/(name+'.json')).write_text(json.dumps({'url':page.url,'body':page.locator('body').inner_text(),'errors':errors,'jobs':app.jobs.jobs},default=str,indent=2))
        (ROOT/'test-results'/(name+'.log')).write_text((app.store.home/'logs/app.log').read_text())
        browser.close()
    server.shutdown();server.server_close();app.close()

def test_browser_import_setup_edit_template_and_mobile(browser_app):
    app,server,page,errors=browser_app
    page.click('#import-deck');page.fill('#import-name','Browser deck');page.fill('#import-source','2 A Test Creature');page.click('#do-import')
    assert page.locator('#modal-host .modal').count()==0
    page.locator('#deck-name,.form-error,#retry-page').first.wait_for()
    assert page.locator('#deck-name').count(),page.locator('body').inner_text()
    assert page.input_value('#deck-name')=='Browser deck'
    with page.expect_file_chooser() as chooser:page.click('#generate-symbols')
    chooser.value.set_files({'name':'symbol.png','mimeType':'image/png','buffer':png((160,160))})
    expect(page.locator('.symbol-upload img')).to_have_count(4)
    with page.expect_file_chooser() as chooser:page.click('[data-back-action=custom]')
    chooser.value.set_files({'name':'back.png','mimeType':'image/png','buffer':png((300,420))})
    expect(page.locator('#back-designer [data-back-preview]')).to_have_count(1)
    page.fill('#deck-artist','Deck Artist');page.click('#save-setup');expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    page.click('[data-tab=cards]');page.locator('[data-card]').first.click();page.fill('#card-qty','3');page.click('#save-card')
    expect(page.locator('.quantity-pill')).to_have_text('3×')
    page.locator('a[data-nav=templates]').click();page.click('#new-template');page.fill('#template-name','Browser frame');page.click('#save-template')
    page.get_by_text('Browser frame',exact=True).wait_for()
    page.locator('a[data-nav=settings]').click();page.locator('#global-refresh').check();page.wait_for_timeout(300)
    assert app.ws.global_settings()['refreshData'] is True
    page.set_viewport_size({'width':390,'height':844});page.locator('a[data-nav=decks]').click();page.locator('#import-deck').wait_for()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    assert not errors,errors

def test_browser_symbol_folder_upload(browser_app,tmp_path):
    app,server,page,errors=browser_app
    d=app.ws.new_deck('Folder symbols')
    page.goto(server.origin+'/#deck/'+d['id']+'/setup');page.locator('#symbol-folder-button').wait_for()
    folder=tmp_path/'symbols';folder.mkdir()
    colors={'common':'#34383e','uncommon':'#8aa4ba','rare':'#d8ad39','mythic':'#e65318'}
    for rarity,color in colors.items():(folder/(rarity+'.png')).write_bytes(png((140,140),color))
    (folder/'notes.txt').write_text('Non-image files are intentionally ignored.')
    with page.expect_file_chooser() as chooser:page.click('#symbol-folder-button')
    chooser.value.set_files(str(folder))
    expect(page.locator('.symbol-upload img')).to_have_count(4,timeout=15000)
    expect(page.locator('#symbol-folder-status')).to_contain_text('Loaded common, uncommon, rare, and mythic')
    page.click('#save-setup');expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    saved=app.ws.deck(d['id']);assert set(saved['settings']['symbols'])=={'common','uncommon','rare','mythic'}
    assert len(set(saved['settings']['symbols'].values()))==4
    bad=tmp_path/'bad-symbols';bad.mkdir()
    for rarity,color in colors.items():
        name='legendary.png' if rarity=='mythic' else rarity+'.png'
        (bad/name).write_bytes(png((120,120),color))
    before=dict(saved['settings']['symbols'])
    with page.expect_file_chooser() as chooser:page.click('#symbol-folder-button')
    chooser.value.set_files(str(bad))
    expect(page.locator('.toast.error')).to_contain_text('common.*, uncommon.*, rare.*, and mythic.*',timeout=10000)
    assert app.ws.deck(d['id'])['settings']['symbols']==before
    assert not errors,errors
def test_browser_card_search_preserves_typing_order_and_caret(browser_app):
    app,server,page,errors=browser_app
    d=app.ws.create({'name':'Search deck','source':'1 A Test Creature'})
    page.goto(server.origin+'/#deck/'+d['id']+'/cards')
    search=page.locator('#card-search');search.wait_for();search.click()
    page.keyboard.type('Test')
    expect(search).to_have_value('Test')
    assert search.evaluate('(el)=>[el.selectionStart,el.selectionEnd]')==[4,4]
    page.keyboard.press('ArrowLeft');page.keyboard.type('X')
    expect(page.locator('#card-search')).to_have_value('TesXt')
    assert page.locator('#card-search').evaluate('(el)=>[el.selectionStart,el.selectionEnd]')==[4,4]
    assert not errors,errors


def test_browser_card_hover_shows_assigned_back_without_flip_button(browser_app):
    app,server,page,errors=browser_app
    art=ingest_image(app.store,png());back=ingest_image(app.store,png((300,420),'#775544'));symbols=rarity_variants(app.store,art['id'])
    d=app.ws.create({'name':'Hover back deck','source':'1 A Test Creature','settings':{'symbols':symbols,'backAsset':back['id']}});d=app.ws.prepare(d['id'])
    comp=d['cards'][0]['faces'][0]['compiled'];app.ws.save_render(comp['renderKey'],png((comp['data']['width'],comp['data']['height'])),(comp['data']['width'],comp['data']['height']))
    page.goto(server.origin+'/#deck/'+d['id']+'/cards')
    card=page.locator('[data-card]').first;img=card.locator('img').first;img.wait_for()
    front=img.get_attribute('src');assert front and front!='/api/assets/'+back['id']
    assert page.locator('.flip-button').count()==0
    expect(card.locator('.card-name-pill')).to_have_text('A Test Creature')
    assert card.locator('h3,.card-credit,.card-item-footer').count()==0
    card.hover();expect(img).to_have_attribute('src','/api/assets/'+back['id'])
    card.dispatch_event('mouseleave');expect(img).to_have_attribute('src',front)
    assert not errors,errors

def test_browser_paired_order_snapshot(browser_app):
    app,server,page,errors=browser_app
    art=ingest_image(app.store,png());back=ingest_image(app.store,png((300,420),'#665577'));symbols=rarity_variants(app.store,art['id'])
    d=app.ws.create({'name':'Paired deck','source':'2 A Test Creature','settings':{'symbols':symbols,'backAsset':back['id']}});d=app.ws.prepare(d['id'])
    comp=d['cards'][0]['faces'][0]['compiled'];app.ws.save_render(comp['renderKey'],png((comp['data']['width'],comp['data']['height'])),(comp['data']['width'],comp['data']['height']))
    page.reload();page.locator('[data-select]').check();page.click('#order-selected');page.click('#order-plan')
    page.locator('.pair-images img').first.wait_for()
    assert page.locator('.pair-images img').count()==2
    if page.locator('#ack-order-warnings').count():page.check('#ack-order-warnings')
    page.click('#build-order');page.locator('#download-order').wait_for()
    with page.expect_download() as dl:page.click('#download-order')
    data=Path(dl.value.path()).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert set(z.namelist())=={'FRONT/000001.png','BACK/000001.png','FRONT/000002.png','BACK/000002.png'}
        assert z.read('BACK/000001.png')==app.store.asset_path(back['id']).read_bytes()
    assert page.url.startswith(server.origin)
    assert not errors,errors

@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in pinned CardConjurer network rendering')
def test_real_cardconjurer_roundtrip(tmp_path):
    """Uses genuine pinned runtime/fonts/frames with synthetic test art, never a fixture renderer."""
    from playwright.sync_api import sync_playwright
    store=Store(tmp_path/'live');net=Network(store);native_transport=net._transport
    def transport(url):
        if 'api.scryfall.com' in url:return json.dumps(sf()).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return png(),'image/png',{}
        return native_transport(url)
    net.transport=transport;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    art=ingest_image(store,png());back=ingest_image(store,png((300,420)));symbols=rarity_variants(store,art['id'])
    d=app.ws.create({'name':'Native CardConjurer test','source':'A Test Creature','settings':{'symbols':symbols,'backAsset':back['id']}})
    (ROOT/'test-results').mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#deck/'+d['id']);page.locator('#generate-deck').wait_for();page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=240000)
            current=app.ws.deck(d['id'])
            assert current['status']=='ready',{'status':current['status'],'activity':page.locator('#activity-log').text_content(),'errors':errors}
            comp=current['cards'][0]['faces'][0]['compiled'];r=store.render_get(comp['renderKey']);im=Image.open(store.asset_path(r['asset_id']))
            assert im.size==(2010,2814)
            assert len(im.resize((100,140)).getcolors(14000) or [])>80,'Native output is unexpectedly blank or flat'
            before=len(app.runtime.requested)
            page.click('#generate-deck');page.wait_for_timeout(2500)
            assert len(app.runtime.requested)==before,'Unchanged front was not reused from render cache'
            (ROOT/'test-results').mkdir(exist_ok=True)
            im.thumbnail((502,703));im.save(ROOT/'test-results/native-card-preview.png')
            (ROOT/'test-results/native-runtime.json').write_text(json.dumps(app.runtime.diagnostic(),indent=2))
            assert not errors,errors
        finally:
            page.screenshot(path=str(ROOT/'test-results/native-browser.png'),full_page=True)
            browser.close();server.shutdown();server.server_close();app.close()


@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in pinned CardConjurer network rendering')
def test_real_cardconjurer_inline_mana_cluster_stays_inside_rules_box(tmp_path):
    from playwright.sync_api import sync_playwright
    card={
        'object':'card','id':'33333333-3333-4333-8333-333333333333',
        'oracle_id':'44444444-4444-4444-8444-444444444444',
        'name':'Morophon, the Boundless','layout':'normal','type_line':'Legendary Creature — Shapeshifter',
        'colors':[],'mana_cost':'{7}','power':'6','toughness':'6','rarity':'mythic',
        'set':'mh1','collector_number':'1','artist':'Fixture Artist',
        'oracle_text':'Changeling (This card is every creature type.)\n'
                      'As Morophon, the Boundless enters, choose a creature type.\n'
                      'Spells of the chosen type you cast cost {W}{U}{B}{R}{G} less to cast. '
                      'This effect reduces only the amount of colored mana you pay.\n'
                      'Other creatures you control of the chosen type get +1/+1.',
        'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/morophon.jpg'},
    }
    store=Store(tmp_path/'mana-wrap');net=Network(store);native_transport=net._transport
    def transport(url):
        if 'api.scryfall.com' in url:return json.dumps(card).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return png(),'image/png',{}
        return native_transport(url)
    net.transport=transport;app=App(store,net);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    art=ingest_image(store,png());symbols=rarity_variants(store,art['id'])
    d=app.ws.create({'name':'Mana wrapping','source':[{'id':card['id']}],'settings':{'symbols':symbols}})
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(server.origin+'/#deck/'+d['id']);page.locator('#generate-deck').wait_for()
            page.evaluate("""() => {
              const originalRemove=HTMLIFrameElement.prototype.remove;
              HTMLIFrameElement.prototype.remove=function(){
                if(this.classList?.contains('render-frame')){this.dataset.testKept='1';return;}
                return originalRemove.call(this);
              };
            }""")
            page.click('#generate-deck');page.locator('.badge.ready,.toast.error').first.wait_for(timeout=240000)
            current=app.ws.deck(d['id'])
            assert current['status']=='ready',{'status':current['status'],'errors':errors,'activity':page.locator('#activity-log').text_content()}
            rules=current['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
            assert 'cost {W}{U}{B}{R}{G} less to cast' in rules
            assert 'cost\n{W}{U}{B}{R}{G}' not in rules
            runtime_frame=next(frame for frame in page.frames if '/runtime/host' in frame.url)
            metrics=runtime_frame.evaluate("""() => {
              const box=window.card?.text?.rules;
              const canvas=window.textCanvas,ctx=window.textContext;
              if(!box||!canvas||!ctx) return null;
              const right=Math.round((box.x+box.width)*window.card.width);
              const top=Math.max(0,Math.floor(box.y*window.card.height));
              const bottom=Math.min(canvas.height,Math.ceil((box.y+box.height)*window.card.height));
              const image=ctx.getImageData(0,top,canvas.width,bottom-top);
              let maxX=-1;
              for(let y=0;y<image.height;y++)for(let x=0;x<image.width;x++){
                if(image.data[(y*image.width+x)*4+3])maxX=Math.max(maxX,x);
              }
              return {title:window.card?.text?.title?.text,right,maxX,overflow:Math.max(0,maxX-right)};
            }""")
            assert metrics and metrics['title']=='Morophon, the Boundless',metrics
            assert metrics['overflow']<=8,metrics
            assert not errors,errors
        finally:
            page.screenshot(path=str(ROOT/'test-results/morophon-mana-wrap.png'),full_page=True)
            browser.close();server.shutdown();server.server_close();app.close()


def test_browser_artist_credit_and_custom_upload(browser_app):
    app,server,page,errors=browser_app
    art=ingest_image(app.store,png());symbols=rarity_variants(app.store,art['id'])
    d=app.ws.create({'name':'Artist credits','source':[{'id':sf()['id']}],
        'settings':{'symbols':symbols,'artist':'Deck Custom Artist'}})
    d=app.ws.prepare(d['id'])
    page.goto(server.origin+'/#deck/'+d['id']);page.locator('[data-card]').first.click()
    expect(page.locator('#printing-artist')).to_have_text('Original Artist')
    expect(page.locator('#face-artist')).to_be_disabled()
    expect(page.locator('#face-credit-preview')).to_have_text('Original Artist (Scryfall) • Art © respective rights holders')
    assert page.locator('#face-modification').count()==0
    with page.expect_file_chooser() as chooser:page.click('#face-art')
    chooser.value.set_files({'name':'custom_art.png','mimeType':'image/png','buffer':png((900,650),'#113355')})
    expect(page.locator('#face-artist')).to_be_enabled()
    page.fill('#face-artist','Custom Per-Card Artist')
    expect(page.locator('#face-credit-preview')).to_have_text('Custom Per-Card Artist')
    page.click('#save-card');page.locator('#save-card').wait_for(state='detached');page.locator('[data-card]').first.wait_for()
    d=app.ws.prepare(d['id'])
    assert d['cards'][0]['faces'][0]['compiled']['data']['infoArtist']=='Custom Per-Card Artist'
    assert d['cards'][0]['faces'][0]['compiled']['data']['infoNote']=='BulkProxyForge • Unofficial Proxy'
    assert not errors,errors


def test_browser_deck_artist_previews(browser_app):
    app,server,page,errors=browser_app
    d=app.ws.create({'name':'Deck credit defaults','source':[{'id':sf()['id']}]})
    page.goto(server.origin+'/#deck/'+d['id']+'/setup');page.locator('#deck-name').wait_for()
    page.fill('#deck-artist','My Custom Artist')
    expect(page.locator('#scryfall-credit-preview')).to_have_text('Original Artist (Scryfall) • Art © respective rights holders')
    expect(page.locator('#custom-credit-preview')).to_have_text('My Custom Artist')
    assert page.locator('#deck-modification').count()==0
    assert page.locator('#use-land-library').count()==0
    page.click('#save-setup');expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    current=app.ws.deck(d['id'])
    assert current['settings']['artist']=='My Custom Artist'
    assert 'modificationCredit' not in current['settings']
    assert 'useLandLibrary' not in current['settings']
    assert not errors,errors


def test_browser_default_icon_full_back_and_reload(browser_app):
    app,server,page,errors=browser_app
    d=app.ws.new_deck('Back designer')
    page.goto(server.origin+'/#deck/'+d['id']+'/setup');page.locator('#back-designer').wait_for()
    expect(page.locator('[data-back-action=default]')).to_have_attribute('aria-pressed','true')
    with page.expect_file_chooser() as chooser:page.click('[data-back-action=icon]')
    # Wide synthetic icon must be contained, never forced to a square.
    chooser.value.set_files({'name':'test_logo.png','mimeType':'image/png','buffer':png((1000,200))})
    expect(page.locator('[data-back-action=icon]')).to_have_attribute('aria-pressed','true',timeout=15000)
    before=page.locator('[data-back-preview]').get_attribute('src')
    page.check('[data-back-guide]');expect(page.locator('.back-icon-guide')).to_be_visible()
    assert page.locator('[data-back-preview]').get_attribute('src')==before
    page.click('#save-setup');expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    saved=app.ws.deck(d['id']);assert saved['settings']['backDesign']['mode']=='icon'
    icon_id=saved['settings']['backAsset']
    page.reload();expect(page.locator('[data-back-action=icon]')).to_have_attribute('aria-pressed','true')
    with page.expect_file_chooser() as chooser:page.click('[data-back-action=custom]')
    chooser.value.set_files({'name':'whole_back.png','mimeType':'image/png','buffer':png((300,420))})
    expect(page.locator('[data-back-action=custom]')).to_have_attribute('aria-pressed','true')
    page.click('#save-setup');expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    assert app.ws.deck(d['id'])['settings']['backAsset']!=icon_id
    page.click('[data-back-action=default]');page.click('#save-setup');expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    assert app.ws.deck(d['id'])['settings']['backAsset']==app.ws.backs.builtin('default')['id']
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    assert not errors,errors
