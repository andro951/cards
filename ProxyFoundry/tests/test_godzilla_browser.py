import json
import hashlib
import os
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect
from playwright.sync_api import sync_playwright

from test_browser import browser_app,png,sf
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image
from PIL import Image


pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in real Chromium tests')


def test_art_setup_stages_local_and_github_data_and_opens_frame_picker(browser_app):
    app,server,page,errors=browser_app
    deck=app.ws.create({'name':'Data imports','source':'1 A Test Creature'})
    page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
    page.locator('#open-card-data').wait_for()

    local={'version':1,'cards':[{'name':'A Test Creature','nickname':'Local name'}]}
    with page.expect_file_chooser() as chooser:
        page.click('#open-card-data')
    chooser.value.set_files({'name':'data.json','mimeType':'application/json',
                            'buffer':json.dumps(local).encode()})
    expect(page.locator('#card-data-status')).to_contain_text('1 nonempty card entry staged')
    assert not app.ws.deck(deck['id'])['cards'][0]['faces'][0].get('semanticOverrides')

    original=app.ws.net.transport
    def transport(url):
        if url=='https://raw.githubusercontent.com/owner/repo/main/data.json':
            data={'version':1,'cards':[{'name':'A Test Creature','nickname':'GitHub name',
                                       'flavor_text':'Linked flavor'}]}
            return json.dumps(data).encode(),'application/json',{}
        return original(url)
    app.ws.net.transport=transport
    page.locator('#data-json-section').get_by_role('button',name='From GitHub',exact=True).click()
    page.fill('#card-data-url','https://github.com/owner/repo/blob/main/data.json')
    page.locator('#card-data-url').press('Tab')
    expect(page.locator('#card-data-status')).to_contain_text('GitHub data.json: 1 nonempty card entry staged')
    assert not errors,errors

    page.click('[data-frame-group=standard]')
    expect(page.locator('#modal-host')).to_contain_text('Godzilla full art · non-land')
    expect(page.locator('#modal-host')).to_contain_text('Classic card')
    page.click('#modal-close')
    expect(page.locator('#activity')).to_be_hidden(timeout=60000)

    page.click('#save-setup')
    expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    values=app.ws.deck(deck['id'])['cards'][0]['faces'][0]['semanticOverrides']
    assert values['nickname']=='GitHub name'
    assert values['flavor_text']=='Linked flavor'


def test_frame_can_be_selected_before_the_preview_plan_arrives(browser_app):
    app,server,page,errors=browser_app
    deck=app.ws.create({'name':'Immediate frame choice','source':'1 A Test Creature'})
    page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
    requests=[];runtime=[]
    page.route('**/api/render-sessions/template-previews',lambda route:requests.append(route))
    page.on('request',lambda request:runtime.append(request.url) if '/api/runtime/prepare' in request.url else None)
    page.click('[data-frame-group=standard]')
    choice=page.get_by_role('button',name='Select Godzilla full art · non-land',exact=True)
    expect(choice).to_be_enabled()
    choice.click()
    expect(page.locator('#modal-host')).to_be_empty()
    for route in requests:
        route.fulfill(json={'targets':[{'choice':'godzilla-card'}],'previewErrors':{}})
    page.click('#save-setup')
    expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    assert app.ws.deck(deck['id'])['settings']['templateRules']['standard']=='godzilla-card'
    assert not runtime and not page.locator('iframe.render-frame').count()
    assert not errors,errors


@pytest.mark.parametrize('selection',['label','preview'])
def test_frame_selection_cancels_an_active_preview_renderer(browser_app,selection):
    app,server,page,errors=browser_app
    deck=app.ws.create({'name':'Cancel active frame preview','source':'1 A Test Creature'})
    page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
    page.route('**/api/runtime/prepare',lambda route:route.fulfill(json={'id':'fake-runtime-job'}))
    page.route('**/api/jobs/fake-runtime-job',lambda route:route.fulfill(json={'state':'done','kind':'runtime','message':'Complete','done':1,'total':1,'result':{}}))
    page.route('**/runtime/host**',lambda route:route.fulfill(content_type='text/html',headers={'Content-Security-Policy':"script-src 'unsafe-inline'"},body='''<script>
      const parentOrigin=new URL(location.href).searchParams.get('parent');
      parent.postMessage({source:'pf-native-runtime',type:'ready'},parentOrigin);
      addEventListener('message',event=>{
        if(event.data.type==='render')parent.postMessage({source:'picker-test',type:'started'},parentOrigin);
      });
    </script>'''))
    page.evaluate("window.__previewStarted=false; addEventListener('message',event=>{if(event.data?.source==='picker-test')window.__previewStarted=true;})")
    page.click('[data-frame-group=standard]')
    expect(page.locator('iframe.render-frame')).to_have_count(1)
    page.wait_for_function('()=>window.__previewStarted',timeout=15000)
    expect(page.locator('#modal-host [role=status]')).to_contain_text('You can choose a frame now.')
    choice=page.get_by_role('button',name=('Select Godzilla full art · non-land' if selection=='label' else 'Choose Godzilla full art · non-land from preview'),exact=True)
    expect(choice).to_be_enabled()
    if selection=='preview':
        expect(choice).to_contain_text('Rendering…')
        output=Path(__file__).resolve().parents[1]/'test-results'
        output.mkdir(exist_ok=True)
        page.locator('#modal-host .modal').screenshot(path=str(output/'frame-picker-select-while-rendering.png'))
    choice.click()
    expect(page.locator('iframe.render-frame')).to_have_count(0)
    expect(page.locator('#activity')).to_be_hidden()
    page.click('#save-setup')
    expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    assert app.ws.deck(deck['id'])['settings']['templateRules']['standard']=='godzilla-card'
    assert not errors,errors


@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in noncreature Godzilla rendering')
def test_native_noncreature_godzilla_frames_render_without_missing_text(tmp_path):
    store=Store(tmp_path/'noncreature-nickname');app=App(store,Network(store));server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    art=ingest_image(store,png((1000,1400),'#597586'))['id'];deck=app.ws.new_deck('Noncreature Godzilla')
    settings=app.ws.validate_settings({'source':{'mode':'local','localFiles':{'test_artifact':art,'test_land':art}},'artist':'Fixture Artist'})
    cards=[]
    for i,(name,types,style) in enumerate([('Test Artifact','Artifact — Equipment','godzilla-card'),('Test Land','Land','godzilla-land')]):
        source={'name':name,'layout':'normal','type_line':types,'colors':['B'] if i==0 else [],
                'mana_cost':'{B}' if i==0 else '', 'oracle_text':'Equipped creature gets +1/+1.\nEquip {1}' if i==0 else '{T}: Add {B}.',
                'rarity':'common','artist':'Fixture Artist'}
        cards.append({'id':'card-'+str(i),'name':name,'quantity':1,'scryfall':source,
                      'faces':[{'id':'face-'+str(i),'name':name,'index':0,'templateOverride':style}]})
    app.ws.store.put('decks',{**deck,'settings':settings,'cards':cards},deck['revision'])
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True);page=browser.new_page()
        try:
            page.goto(server.origin+'/#deck/'+deck['id']);page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=180000)
            current=app.ws.deck(deck['id'])
            assert current['status']=='ready',page.locator('#activity-log').text_content()
            output=Path(__file__).resolve().parents[1]/'test-results';output.mkdir(exist_ok=True)
            for entry in current['cards']:
                compiled=entry['faces'][0]['compiled'];assert compiled['data']['text']['pt']['text']==''
                render=store.render_get(compiled['renderKey']);assert render
                picture=Image.open(store.asset_path(render['asset_id']));picture.thumbnail((603,844))
                picture.save(output/(entry['name'].replace(' ','_')+'_godzilla.png'))
        finally:browser.close();server.shutdown();server.server_close();app.close()


@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in pinned CardConjurer network rendering')
def test_native_frame_picker_renders_and_selects_godzilla(tmp_path):
    store=Store(tmp_path/'native-picker')
    network=Network(store)
    remote=network._transport
    def transport(url):
        if 'api.scryfall.com' in url:
            return json.dumps(sf()).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:
            return png(),'image/png',{}
        return remote(url)
    network.transport=transport
    app=App(store,network)
    server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    deck=app.ws.create({'name':'Native picker','source':'1 A Test Creature'})
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
            page.click('[data-frame-group=standard]')
            page.locator('#modal-host img:visible').first.wait_for(timeout=240000)
            page.locator('#activity').wait_for(state='hidden',timeout=240000)
            assert page.locator('#modal-host img:visible').count()>=2
            page.wait_for_function("Array.from(document.querySelectorAll('#modal-host img')).filter(image=>image.offsetWidth>0).filter(image=>image.complete&&image.naturalWidth>0).length>=2",timeout=240000)
            images=page.locator('#modal-host img:visible')
            hashes=[hashlib.sha256(images.nth(index).screenshot()).hexdigest() for index in range(images.count())]
            assert len(set(hashes))>=2,'Frame choices rendered identical PNGs.'
            godzilla=page.locator('#modal-host button[aria-label="Select Godzilla full art · non-land"]')
            expect(godzilla).to_be_enabled(timeout=240000)
            output=Path(__file__).resolve().parents[1]/'test-results'
            output.mkdir(exist_ok=True)
            page.locator('#modal-host img:visible').first.screenshot(path=str(output/'godzilla-frame-preview.png'))
            godzilla.click()
            page.click('#save-setup')
            expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
            assert app.ws.deck(deck['id'])['settings']['templateRules']['standard']=='godzilla-card'
            assert not errors,errors
        finally:
            browser.close()
            server.shutdown();server.server_close();app.close()


@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in pinned CardConjurer network rendering')
def test_native_black_and_colorless_nickname_tokens_have_complete_frames(tmp_path):
    store=Store(tmp_path/'native-tokens')
    network=Network(store)
    app=App(store,network)
    server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    art=ingest_image(store,png((1000,1400),'#597586'))['id']
    deck=app.ws.new_deck('Nickname tokens')
    settings=app.ws.validate_settings({'source':{'mode':'local','localFiles':{
        'black_creature':art,'colorless_creature':art}},'artist':'Fixture Artist',
        'allCardsTokens':True})
    cards=[]
    for index,(name,colors,nickname) in enumerate([
        ('Black Creature',['B'],'Black Reskin'),
        ('Colorless Creature',[],'Colorless Reskin'),
    ]):
        source={'name':name,'layout':'normal','type_line':'Creature — Beast',
                'mana_cost':'{2}{B}' if colors else '{3}','oracle_text':'Vigilance',
                'flavor_text':'Flavor text.','colors':colors,'rarity':'rare',
                'power':'3','toughness':'3','flavor_name':nickname,'artist':'Fixture Artist'}
        cards.append({'id':f'00000000-0000-4000-8000-{index+1:012d}','name':name,
                      'quantity':1,'scryfall':source,
                      'faces':[{'id':f'11111111-1111-4111-8111-{index+1:012d}',
                                'name':name,'index':0}]})
    app.ws.store.put('decks',{**deck,'settings':settings,'cards':cards},deck['revision'])
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(server.origin+'/#deck/'+deck['id'])
            page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=240000)
            current=app.ws.deck(deck['id'])
            assert current['status']=='ready',page.locator('#activity-log').text_content()
            output=Path(__file__).resolve().parents[1]/'test-results'
            output.mkdir(exist_ok=True)
            for card_entry in current['cards']:
                compiled=card_entry['faces'][0]['compiled']
                frames=compiled['data']['frames']
                assert any('m15NicknameFrame' in frame['src'] for frame in frames)
                assert all(frame.get('masks')==[] for frame in frames)
                render=store.render_get(compiled['renderKey'])
                assert render
                picture=Image.open(store.asset_path(render['asset_id']))
                picture.save(output/(card_entry['name'].replace(' ','_')+'.png'))
            assert not errors,errors
        finally:
            browser.close()
            server.shutdown();server.server_close();app.close()
