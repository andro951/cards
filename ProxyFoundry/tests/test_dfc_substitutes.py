"""Substitute fronts share quantities, retain ordinary art wells, and commit atomically."""
import copy,io,json,zipfile,os,threading
from pathlib import Path
import pytest
from PIL import Image
from foundry import substitutes
from foundry.browser import BrowserStore,request
from foundry.domain import ValidationError
from foundry.images import ingest_image
from foundry.network import Network
from foundry.orders import Orders
from foundry.server import App
from foundry.storage import Store
from foundry.workspace import Workspace
from test_browser_storage import static_browser
from test_battle import invasion_of_ikoria


def seed(tmp_path,style='auto',enabled=True,quantity=3,store=None,sf=None):
    store=store or Store(tmp_path)
    front={'name':'Brutal Cathar','type_line':'Creature — Human Soldier Werewolf','colors':['W'],
        'mana_cost':'{2}{W}','oracle_text':'Whenever this creature enters, exile target creature.\nDaybound',
        'power':'2','toughness':'2'}
    back={'name':'Moonrage Brute','type_line':'Creature — Werewolf','colors':['R'],
        'mana_cost':'','oracle_text':'First strike\nNightbound','power':'3','toughness':'3'}
    sf=sf or {'id':'test-dfc','name':'Brutal Cathar // Moonrage Brute','layout':'transform','rarity':'rare',
        'artist':'Tester','frame_effects':['sunmoondfc'],'card_faces':[front,back]}
    def transport(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(sf).encode(),'application/json',{}
        raise AssertionError('Unexpected network request: '+url)
    ws=Workspace(store,Network(store,transport=transport))
    output=io.BytesIO();Image.new('RGB',(800,1000),'#456789').save(output,'PNG')
    art=ingest_image(store,output.getvalue())
    card=ws.sources.entry(sf,quantity)
    for face in card['faces']:face['artOverride']=art['id']
    settings=ws.validate_settings({'createDfcSubstitutes':enabled,
        'artist':'Test artwork',
        'templateRules':{'transform-front':style,'transform-back':style}})
    deck=ws.new_deck('DFC substitute tests')
    deck=store.put('decks',{**deck,'cards':[card],'settings':settings},deck['revision'])
    return ws,deck,art


def fake_renders(ws,deck):
    output=io.BytesIO();Image.new('RGB',(30,42),'#123456').save(output,'PNG')
    asset=ingest_image(ws.store,output.getvalue())
    for card in deck['cards']:
        for face in substitutes.render_faces(card,deck['settings']):
            ws.store.render_put(face['compiled']['renderKey'],asset,deck_id=deck['id'],card_id=card['id'],
                face_id=face['id'],deck_name=deck['name'],face_name=face['name'])
    saved=ws.store.get('decks',deck['id'])
    for card in saved['cards']:
        for face in card['faces']:face['acceptedWarningKey']=face['compiled']['renderKey']
    ws.store.put('decks',saved,saved['revision'])


@pytest.mark.parametrize('style',['auto','godzilla-card'])
@pytest.mark.parametrize('legendary,nickname',[(False,''),(False,'Garth, Monster Hunter'),(True,''),(True,'Garth, Monster Hunter')])
def test_substitute_is_a_normal_frame_with_complete_uncropped_sign(tmp_path,style,legendary,nickname):
    ws,deck,art=seed(tmp_path,style)
    if legendary:deck['cards'][0]['scryfall']['card_faces'][0]['type_line']='Legendary Creature — Human Soldier Werewolf'
    if nickname:deck['cards'][0]['faces'][0]['semanticOverrides']={'nickname':nickname}
    ws.sources.resolve_card=lambda *args,**kwargs:deck['cards'][0]['scryfall']
    ws.store.put('decks',deck,deck['revision'])
    prepared=ws.prepare(deck['id']);card=prepared['cards'][0]
    assert not any(face.get('error') for face in card['faces'])
    assert len(card['faces'])==2
    substitute=card['substitute'];data=substitute['compiled']['data'];source=card['faces'][0]['compiled']['data']
    assert data['version']!='m15Nickname' and data['artBounds']['height']<.6
    assert data['text']['type']['text'].startswith('Legendary')==legendary
    assert not any('/godzilla/' in frame.get('src','') for frame in data['frames'])
    for name in ('title','mana','type','rules','pt'):
        assert data['text'][name]['text']==source['text'][name]['text']
    if nickname:assert data['text']['nickname']['text']==nickname
    if style=='auto':assert data['frames'][:-1]==source['frames']
    assert substitute['compiled']['artId']!=art['id']
    sign=data['frames'][-1]['bounds'];bounds=data['artBounds']
    assert sign['x']>=bounds['x']-1e-8 and sign['y']>=bounds['y']-1e-8
    assert sign['x']+sign['width']<=bounds['x']+bounds['width']+1e-8
    assert sign['y']+sign['height']<=bounds['y']+bounds['height']+1e-8
    assert_wall_fills_card(ws,substitute)
    assert prepared['summary']['substitutes']==3 and prepared['summary']['physicalCards']==6
    assert prepared['summary']['faces']==3
    assert len(ws.render_targets([deck['id']])['targets'])==3
    assert len(ws.render_targets_for_card(deck['id'],card['id'])['targets'])==3
    exported=json.loads(ws.export_cc([deck['id']]))
    assert len(exported)==3
    assert exported[-1]['data']['frames'][-1]['src'].startswith('data:image/png;base64,')


def assert_wall_fills_card(ws,substitute):
    data=substitute['compiled']['data'];wall=ws.store.asset(substitute['compiled']['artId'])
    assert wall['width']/wall['height']==pytest.approx(7/5)
    assert data['artY']==0
    assert data['artZoom']*wall['height']==pytest.approx(data['height'])
    assert data['artX']<=0
    assert data['artX']*2+data['artZoom']*wall['width']/data['width']==pytest.approx(1)
    if data.get('landscape'):assert data['artX']==pytest.approx(0)


def planeswalker_dfc():
    front=json.loads((Path(__file__).parent/'fixtures/godzilla_special/Tezzeret.json').read_text(encoding='utf-8'))
    return {'id':'test-planeswalker-dfc','name':front['name']+' // Test reverse','layout':'transform',
        'rarity':'mythic','card_faces':[front,{'name':'Test reverse','type_line':'Artifact','colors':[],
            'mana_cost':'','oracle_text':'Indestructible'}]}


def test_planeswalker_substitute_wall_fills_height_and_sign_stays_in_art_well(tmp_path):
    ws,deck,art=seed(tmp_path,sf=planeswalker_dfc())
    card=deck['cards'][0];front=card['scryfall']['card_faces'][0]
    #Exercise an already-compiled native walker front independently of the
    #unsupported automatic transform-frame choice for this synthetic pair.
    card['faces'][0]['compiled']=ws.compiler.compile_face(front,front,0,{},deck['settings'],art['id'])
    assert substitutes.build(ws,deck,card,deck['settings'])
    sub=card['substitute'];data=sub['compiled']['data']
    assert 'planeswalker' in data['version'].lower()
    assert_wall_fills_card(ws,sub)
    sign=data['frames'][-1]['bounds'];bounds=data['artBounds']
    assert sign['y']>=bounds['y']
    assert sign['y']+sign['height']<=bounds['y']+bounds['height']+1e-8


def test_battle_sign_fits_visible_window_and_refreshes_only_substitute(tmp_path,monkeypatch):
    ws,deck,_=seed(tmp_path,sf=invasion_of_ikoria())
    prepared=ws.prepare(deck['id']);card=prepared['cards'][0]
    source=copy.deepcopy(card['faces']);sub=card['substitute'];data=sub['compiled']['data']
    assert data['version']=='battle' and data['landscape']
    assert data['frames'][:-1]==source[0]['compiled']['data']['frames']
    assert data['text']==source[0]['compiled']['data']['text']
    assert data['artBounds']==substitutes.BATTLE_SIGN_BOUNDS
    sign=data['frames'][-1]['bounds']
    assert sign['y']>=.15
    assert sign['y']+sign['height']<=830/1500+1e-8
    assert sign['x']>=268/2100
    assert sign['x']+sign['width']<=1968/2100+1e-8
    assert_wall_fills_card(ws,sub)
    assert substitutes.current(card)
    fake_renders(ws,prepared)
    old=ws.store.get('decks',deck['id'])
    old['cards'][0]['substitute']['substituteVersion']=1
    ws.store.put('decks',old,old['revision'])
    assert not substitutes.current(old['cards'][0])
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Cached Battle recompiled'))
    monkeypatch.setattr(ws.sources,'resolve_card',lambda *a,**k:pytest.fail('Cached metadata refetched'))
    updated=ws.prepare(deck['id'])['cards'][0]
    assert [f['compiled']['renderKey'] for f in updated['faces']]==[f['compiled']['renderKey'] for f in source]
    assert substitutes.current(updated)
    assert updated['substitute']['id']==sub['id']


def test_orders_include_one_substitute_per_copy_with_normal_back(tmp_path):
    ws,deck,_=seed(tmp_path)
    prepared=ws.prepare(deck['id']);fake_renders(ws,prepared)
    card=prepared['cards'][0];plan=Orders(ws).plan([deck['id']])
    actual=[row for row in plan['cards'] if not row.get('isSubstitute')]
    replacements=[row for row in plan['cards'] if row.get('isSubstitute')]
    assert len(actual)==len(replacements)==3
    assert all(row['backAsset']==ws.store.render_get(card['faces'][1]['compiled']['renderKey'])['asset_id'] for row in actual)
    assert all(row['backAsset']==prepared['settings']['backAsset'] for row in replacements)
    order=Orders(ws).build([deck['id']])
    with zipfile.ZipFile(ws.store.home/'orders'/(order['id']+'.zip')) as archive:
        assert len(archive.namelist())==12


def test_substitute_has_default_back_even_when_deck_omits_backs(tmp_path):
    ws,deck,_=seed(tmp_path)
    ws.save(deck['id'],{'revision':deck['revision'],'settings':{'backDesign':{'mode':'none'}}})
    prepared=ws.prepare(deck['id']);fake_renders(ws,prepared)
    plan=Orders(ws).plan([deck['id']])
    rows=[row for row in plan['cards'] if row.get('isSubstitute')]
    assert len(rows)==3 and all(row['backAsset']==ws.backs.builtin('default')['id'] for row in rows)


def test_enable_disable_and_quantity_changes_reuse_existing_faces(tmp_path,monkeypatch):
    ws,deck,_=seed(tmp_path,enabled=False)
    prepared=ws.prepare(deck['id']);source=[copy.deepcopy(f['compiled']) for f in prepared['cards'][0]['faces']]
    assert not prepared['cards'][0].get('substitute') and prepared['summary']['faces']==2
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Cached source recompiled'))
    monkeypatch.setattr(ws.sources,'resolve_card',lambda *a,**k:pytest.fail('Cached metadata refetched'))
    ws.save(deck['id'],{'revision':prepared['revision'],'settings':{'createDfcSubstitutes':True}})
    prepared=ws.prepare(deck['id']);sub=copy.deepcopy(prepared['cards'][0]['substitute'])
    assert [f['compiled'] for f in prepared['cards'][0]['faces']]==source
    fake_renders(ws,prepared)
    ready=ws.deck(deck['id']);assert ready['status']=='ready'
    ws.mutate_card(deck['id'],ready['cards'][0]['id'],{'revision':ready['revision'],'quantity':5})
    prepared=ws.prepare(deck['id']);assert prepared['summary']['substitutes']==5
    assert prepared['cards'][0]['substitute']['id']==sub['id']
    assert prepared['cards'][0]['substitute']['compiled']['renderKey']==sub['compiled']['renderKey']
    assert not ws.render_targets([deck['id']])['targets']
    ws.save(deck['id'],{'revision':prepared['revision'],'settings':{'createDfcSubstitutes':False}})
    disabled=ws.deck(deck['id']);assert disabled['summary']['physicalCards']==5
    assert len(Orders(ws).plan([deck['id']])['cards'])==5
    assert len(ws.render_targets([deck['id']],force=True)['targets'])==2


@pytest.mark.parametrize('kind',['single','split','token','converted','helper'])
def test_non_dfc_and_tokens_are_excluded(tmp_path,kind):
    ws,deck,_=seed(tmp_path);card=deck['cards'][0]
    if kind in {'single','split'}:
        card['faces']=card['faces'][:1]
        card['scryfall']['layout']='split' if kind=='split' else 'normal'
    elif kind=='token':card['scryfall']['layout']='double_faced_token'
    elif kind=='converted':card['tokenSpec']={}
    else:
        card['scryfall']['card_faces'][0]['type_line']='Card'
        card['faces'][0]['group']='helper'
    assert not substitutes.required(card,deck['settings'])
    assert not substitutes.required(deck['cards'][0],{**deck['settings'],'allCardsTokens':True})


def test_default_is_on_and_sign_does_not_enter_art_matching(tmp_path):
    ws,deck,_=seed(tmp_path)
    assert ws.validate_settings({})['createDfcSubstitutes'] is True
    ws.prepare(deck['id']);card=ws.deck(deck['id'])['cards'][0]
    assert len(ws.sources.entry(card['scryfall'])['faces'])==2
    assert len(card['faces'])==2 and card['substitute']['compiled']['crop']['warning'] is False


def test_substitute_render_survives_backup(tmp_path):
    from foundry.backup import Backups
    ws,deck,_=seed(tmp_path/'source');prepared=ws.prepare(deck['id']);fake_renders(ws,prepared)
    backup=Backups(ws).export();path=ws.store.home/'backups'/backup['filename']
    target=Workspace(Store(tmp_path/'target'))
    Backups(target).import_selected(path,{'decks':[deck['id']]})
    restored=target.deck(deck['id'])
    assert restored['status']=='ready'
    assert restored['cards'][0]['substitute']['compiled']['render']
    assert Orders(target).plan([deck['id']])['count']==6


def test_duplicate_deck_gets_independent_substitute_identity(tmp_path):
    ws,deck,_=seed(tmp_path)
    prepared=ws.prepare(deck['id']);old=prepared['cards'][0]['substitute']
    duplicate=ws.duplicate(deck['id'])
    assert not duplicate['cards'][0].get('substitute')
    updated=ws.prepare(duplicate['id'])
    assert updated['cards'][0]['substitute']['id']!=old['id']
    assert ws.deck(deck['id'])['cards'][0]['substitute']['id']==old['id']


@pytest.mark.parametrize('finish',['commit','abort','incomplete'])
def test_generation_includes_substitutes_in_atomic_commit(tmp_path,finish):
    snapshots=[]
    store=BrowserStore(tmp_path,persist=lambda path:snapshots.append(Path(path).read_bytes()))
    ws,deck,_=seed(tmp_path,store=store)
    app=App(store,ws.net);app.ws=ws
    def call(path,data):return request(app,'POST',path,json.dumps(data).encode())
    try:
        session=json.loads(call('/api/generation/begin',{'deckIds':[deck['id']]})['body'])
        count=len(snapshots);prepared=ws.prepare(deck['id'])
        targets=list(store.generation['targets'].values());assert len(targets)==3
        assert store.generation['faceCounts'][deck['id']]==3
        rows=[]
        for target in targets:
            data=target['data'];width=round(data['width']*(1+2*data.get('marginX',0)));height=round(data['height']*(1+2*data.get('marginY',0)))
            out=io.BytesIO();Image.new('RGB',(width,height),'#789abc').save(out,'PNG',compress_level=1)
            raw=out.getvalue();asset=store.add_asset(raw,'image/png',width,height)
            rows.append({'key':target['key'],'hash':asset['id'],'bytes':len(raw),'width':width,'height':height,
                'deckId':deck['id'],'cardId':target['cardId'],'faceId':target['faceId']})
        assert len(snapshots)==count
        if finish=='commit':
            result=call('/api/generation/commit',{'id':session['id'],'rows':rows})
            assert result['status']==200 and len(snapshots)==count+1
            assert ws.deck(deck['id'])['status']=='ready'
        else:
            if finish=='incomplete':
                result=call('/api/generation/commit',{'id':session['id'],'rows':rows[:2]})
                assert result['status']==400 and not store.render_get(rows[0]['key'])
            call('/api/generation/abort',session)
            assert len(snapshots)==count
            assert not store.get('decks',deck['id'])['cards'][0].get('substitute')
    finally:app.close()


@pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual native render in Chromium')
@pytest.mark.parametrize('kind',['ordinary','battle'])
def test_native_substitute_render_and_print_preview(tmp_path,kind):
    from playwright.sync_api import sync_playwright
    from foundry.server import LocalServer
    sf=invasion_of_ikoria() if kind=='battle' else None
    ws,deck,_=seed(tmp_path,'godzilla-card',quantity=1,sf=sf)
    transport=ws.net.transport
    ws.net.transport=lambda url:ws.net._transport(url) if 'raw.githubusercontent.com' in url else transport(url)
    app=App(ws.store,ws.net);server=LocalServer(app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(server.origin+'/#deck/'+deck['id'])
            page.locator('#generate-deck').wait_for();page.click('#generate-deck')
            page.wait_for_function("() => document.querySelector('.badge.ready') || document.querySelector('.toast.error')",timeout=240000)
            current=app.ws.deck(deck['id'])
            assert current['status']=='ready',{'status':current['status'],'errors':errors,'page':page.locator('body').inner_text()[-2500:]}
            tile=page.locator('[data-substitute]');tile.wait_for()
            page.locator('[data-deck-section="cards"] [data-card]').wait_for()
            assert current['summary']['physicalCards']==2
            tile.click()
            output=Path(__file__).resolve().parents[1]/'test-results'/('dfc-substitute-preview.png' if kind=='ordinary' else kind+'-substitute-preview.png')
            output.parent.mkdir(exist_ok=True)
            source=current['cards'][0]['substitute']['compiled']['render']['asset_id']
            output.write_bytes(app.store.asset_path(source).read_bytes())
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close();app.close();thread.join(timeout=5)


@pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Production static browser generation')
def test_static_browser_generation_commits_substitute_and_reuses_all_faces(static_browser,tmp_path):
    directory,context,origin=static_browser
    ws,deck,art=seed(tmp_path/'seed','godzilla-card',quantity=1)
    import base64
    encoded=base64.b64encode(ws.store.asset_path(art['id']).read_bytes()).decode()
    hook='''
original_substitute_test_request=request

def request(app,method,url,body,headers):
    if url=='/api/__test__/seed-substitute':
        import base64
        source=json.loads(base64.b64decode(DECK_DATA))
        raw=base64.b64decode(ART_DATA)
        asset=app.store.add_asset(raw,'image/png',800,1000)
        settings=source['settings'];settings.pop('symbols',None);settings.pop('backAsset',None)
        source['settings']=app.ws.validate_settings(settings)
        sf=source['cards'][0]['scryfall']
        app.ws.sources.resolve_card=lambda *args,**kwargs:sf
        for face in source['cards'][0]['faces']:face['artOverride']=asset['id']
        result=app.store.put('decks',source)
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_substitute_test_request(app,method,url,body,headers)
'''.replace('DECK_DATA',repr(base64.b64encode(json.dumps(deck).encode()).decode())).replace('ART_DATA',repr(encoded))
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',hook+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate('''async()=>{
        const ui=await import('/site/ui.js');
        const deck=await ui.api('/api/__test__/seed-substitute',{});
        location.hash='#deck/'+deck.id;
        return deck.id;
    }''')
    page.locator('#generate-deck').wait_for();page.click('#generate-deck')
    page.wait_for_function("() => document.querySelector('.badge.ready') || document.querySelector('.toast.error')",timeout=240000)
    current=page.evaluate('async id=>(await import("/site/ui.js")).api("/api/decks/"+id)',result)
    assert current['status']=='ready',page.locator('body').inner_text()[-2000:]
    assert current['summary']['faces']==current['summary']['rendered']==3
    assert current['summary']['physicalCards']==2
    keys=[face['compiled']['renderKey'] for face in substitutes.render_faces(current['cards'][0],current['settings'])]
    repeated=page.evaluate('''async id=>{
        const rendered=await (await import('/site/render.js')).renderDecks([id],{artChecked:true,notify:false});
        return {rows:rendered.rows,deck:await (await import('/site/ui.js')).api('/api/decks/'+id)};
    }''',result)
    assert repeated['rows']==[]
    updated=repeated['deck']
    assert updated['status']=='ready'
    assert [face['compiled']['renderKey'] for face in substitutes.render_faces(updated['cards'][0],updated['settings'])]==keys
