from __future__ import annotations
import io,json,threading,urllib.request,urllib.error,zipfile,time
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants
from foundry.domain import PIPELINE_VERSION


def png(size=(900,600),color='#aa7733'):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return out.getvalue()

def padded_png(size, visible_box, color=(100,140,200,180)):
    out=io.BytesIO();im=Image.new('RGBA',size,(0,0,0,0))
    im.paste(color,visible_box);im.save(out,'PNG');return out.getvalue()

def card(name='Sample Card'):
    return {'object':'card','id':'11111111-1111-4111-8111-111111111111','oracle_id':'22222222-2222-4222-8222-222222222222','name':name,
        'type_line':'Creature — Human','layout':'normal','colors':['G'],'mana_cost':'{2}{G}',
        'power':'2','toughness':'3','oracle_text':'Vigilance','rarity':'common','set':'tst','collector_number':'1',
        'artist':'Original artist','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/test.jpg','png':'https://cards.scryfall.io/png/front/a/b/test.png'}}

@pytest.fixture
def running(tmp_path):
    s=Store(tmp_path)
    def transport(url):
        if 'api.scryfall.com' in url:return json.dumps(card()).encode(),'application/json',{}
        return png(),'image/png',{}
    app=App(s,Network(s,transport=transport,sleeper=lambda _:None));server=LocalServer(app)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield app,server
    server.shutdown();server.server_close();app.close()


def request(server,path,data=None,headers=None,raw=False,origin=None):
    h=headers or {}
    if data is not None:
        if not isinstance(data,bytes):data=json.dumps(data).encode();h={'Content-Type':'application/json',**h}
        h={'X-Proxy-CSRF':server.app.csrf,**h}
    if origin:h['Origin']=origin
    req=urllib.request.Request(server.origin+path,data=data,headers=h)
    try:r=urllib.request.urlopen(req,timeout=10)
    except urllib.error.HTTPError as e:r=e
    body=r.read()
    return r.status, body if raw else json.loads(body or b'{}'),r.headers


def job_done(server,path,data):
    status,j,_=request(server,path,data);assert status==200,j
    for _ in range(100):
        _,job,_=request(server,'/api/jobs/'+j['id'])
        if job['state'] in {'done','failed','cancelled'}:
            assert job['state']=='done',job
            return job['result']
        time.sleep(.02)
    raise AssertionError('job stalled')


def test_csrf_and_runtime_isolation(running):
    app,s=running
    bootstrap=request(s,'/api/bootstrap')[1]
    assert bootstrap['runtimeOrigin']!=s.origin
    assert bootstrap['pipelineVersion']==PIPELINE_VERSION
    assert request(s,'/api/decks/new',{'name':'x'},headers={'X-Proxy-CSRF':'bad'})[0]==403
    assert request(s,'/api/decks/new',{'name':'x'},origin='https://evil.example')[0]==403
    r=s.runtime_server
    assert request(r,'/api/bootstrap')[0]==404
    assert request(r,'/api/decks/new',{'name':'x'})[0]==403
    assert request(s,'/api/bootstrap',headers={'Host':'evil.example'})[0]==403


def test_render_diagnostics_log_pipeline_cache_and_symbol_geometry(running):
    app,s=running
    _,art,_=request(s,'/api/uploads',png(),headers={'X-Filename':'sample_card.png'})
    _,back,_=request(s,'/api/uploads',png((300,420),'#223355'))
    _,symbols,_=request(s,'/api/symbols/generate',{'assetId':art['id']})
    d=job_done(s,'/api/decks/import',{'name':'Diagnostic Deck','source':'1 Sample Card','settings':{'symbols':symbols,'backAsset':back['id']}})
    request(s,'/api/decks/'+d['id'])
    d=job_done(s,'/api/decks/'+d['id']+'/prepare',{})
    _,plan,_=request(s,'/api/render-sessions',{'deckIds':[d['id']],'force':True})
    assert plan['pipelineVersion']==PIPELINE_VERSION and plan['force'] is True and len(plan['targets'])==1
    key=plan['targets'][0]['key'];_,target,_=request(s,'/api/render-sessions/'+plan['id']+'/'+key)
    dims=(target['data']['width'],target['data']['height'])
    request(s,'/api/render-sessions/'+plan['id']+'/'+key,png(dims))
    for h in list(app.log.handlers): h.flush()
    log=(app.store.home/'logs/app.log').read_text(encoding='utf-8')
    for token in ['APP_START','DECK_OPEN','PREPARE_BEGIN','PREPARE_FACE','RENDER_PLAN_BEGIN','RENDER_FACE_DECISION','RENDER_SAVE',PIPELINE_VERSION]:
        assert token in log,token
    assert 'zoom=' in log and 'newKey=' in log and 'cachePresent=' in log
    assert 'SET_SYMBOL_GEOMETRY' in log and 'alphaGt2=' in log and 'drawExpectedPx=' in log


def test_diagnostics_download_routes_return_real_files(running):
    app,s=running
    # Simulate a legacy/corrupt job log containing a byte that Windows cp1252
    # cannot decode. Diagnostics should sanitize it instead of failing.
    bad=app.store.home/'logs'/'job-legacy-corrupt.json'
    bad.write_bytes(b'{"id":"legacy","message":"bad \\x81 byte","result":{"large":"omit"}}')
    status,raw,headers=request(s,'/api/diagnostics.zip',raw=True)
    assert status==200 and headers.get_content_type()=='application/zip'
    assert 'BulkProxyForge_Diagnostics.zip' in headers.get('Content-Disposition','')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert 'diagnostics.json' in z.namelist()
        payload=json.loads(z.read('diagnostics.json'))
        assert payload['pipelineVersion']==PIPELINE_VERSION
        legacy=json.loads(z.read('job-legacy-corrupt.json').decode('utf-8'))
        assert legacy['id']=='legacy'
        assert '\ufffd' in legacy['message']
        assert 'result' not in legacy
    status,payload,headers=request(s,'/api/diagnostics.json')
    assert status==200 and payload['pipelineVersion']==PIPELINE_VERSION
    assert 'diagnostics.json' in headers.get('Content-Disposition','')


def test_prepare_error_becomes_attention_and_render_plan_reports_the_real_error(running):
    app,s=running
    _,art,_=request(s,'/api/uploads',png(),headers={'X-Filename':'sample_card.png'})
    _,back,_=request(s,'/api/uploads',png((300,420),'#223355'))
    _,symbols,_=request(s,'/api/symbols/generate',{'assetId':art['id']})
    d=job_done(s,'/api/decks/import',{'name':'Artifact Combo','source':'1 Sample Card','settings':{'symbols':symbols,'backAsset':back['id']}})
    d=job_done(s,'/api/decks/'+d['id']+'/prepare',{})
    stored=app.store.get('decks',d['id'])
    face=stored['cards'][0]['faces'][0]
    face.pop('compiled',None);face['error']='Synthetic preparation failure'
    stored['status']='prepared'
    app.store.put('decks',stored,stored['revision'])
    current=app.ws.deck(d['id'])
    assert current['status']=='attention'
    status,plan,_=request(s,'/api/render-sessions',{'deckIds':[d['id']]})
    assert status==200 and plan['targets']==[]
    assert plan['errors']==['Artifact Combo / Sample Card: Synthetic preparation failure']


def test_runtime_symbol_diagnostic_endpoint(running):
    app,s=running
    payload={'key':'a'*64,'stage':'after-final-draw','diagnostic':{'version':'m15Regular','image':{'width':869,'height':1057},'card':{'x':.87,'y':.57,'zoom':.109},'lastDraw':{'args':[1757,1606,94.7,115.2]}}}
    status,out,_=request(s,'/api/render-diagnostic',payload);assert status==200 and out['ok'] is True
    for h in list(app.log.handlers):h.flush()
    log=(app.store.home/'logs/app.log').read_text(encoding='utf-8')
    assert 'RUNTIME_SYMBOL' in log and 'after-final-draw' in log and '869' in log and '1757' in log


def test_runtime_symbol_source_instrumentation():
    root=Path(__file__).resolve().parents[1]
    bridge=(root/'site/runtime-bridge.js').read_text(encoding='utf-8')
    render=(root/'site/render.js').read_text(encoding='utf-8')
    for token in ['lastSetSymbolDraw','image===window.setSymbol','after-load','after-first-draw','after-final-draw','expectedDraw']:
        assert token in bridge
    assert "m.type==='diagnostic'" in render and '/api/render-diagnostic' in render


def test_import_prepare_render_order_roundtrip(running):
    app,s=running
    _,art,_=request(s,'/api/uploads',png(),headers={'X-Filename':'sample_card.png'})
    _,back,_=request(s,'/api/uploads',png((300,420),'#223355'))
    _,symbols,_=request(s,'/api/symbols/generate',{'assetId':art['id']})
    d=job_done(s,'/api/decks/import',{'name':'Test Deck','source':'2 Sample Card','settings':{'symbols':symbols,'backAsset':back['id']}})
    d=job_done(s,'/api/decks/'+d['id']+'/prepare',{})
    assert d['summary']['errors']==0,d
    assert d['summary']['cards']==2
    _,plan,_=request(s,'/api/render-sessions',{'deckIds':[d['id']]})
    assert len(plan['targets'])==1
    key=plan['targets'][0]['key']
    _,target,_=request(s,'/api/render-sessions/'+plan['id']+'/'+key)
    dims=(target['data']['width'],target['data']['height'])
    assert request(s,'/api/render-sessions/'+plan['id']+'/'+key,png((10,10)))[0]==400
    assert request(s,'/api/render-sessions/'+plan['id']+'/'+key,png(dims))[0]==200
    status,ready,_=request(s,'/api/decks/'+d['id']);assert ready['status']=='ready'
    status,plan,_=request(s,'/api/orders/plan',{'deckIds':[d['id']]});assert status==200;assert plan['count']==2
    order=job_done(s,'/api/orders/build',{'deckIds':[d['id']],'acknowledge':True})
    _,data,_=request(s,order['download'],raw=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert set(z.namelist())=={'FRONT/000001.png','BACK/000001.png','FRONT/000002.png','BACK/000002.png'}
        assert z.read('BACK/000001.png')==app.store.asset_path(back['id']).read_bytes()
    _,t,_=request(s,'/api/orders/'+order['id']+'/transfer',{})
    assert request(s,'/api/transfer/'+t['id']+'/metadata')[0]==403
    h={'X-Proxy-Transfer-Token':t['secret']}
    status,m,_=request(s,'/api/transfer/'+t['id']+'/metadata',headers=h);assert m['count']==2
    status,chunk,headers=request(s,'/api/transfer/'+t['id']+'/zip',headers={**h,'Range':'bytes=0-99'},raw=True)
    assert status==206 and chunk==data[:100]
    changed=app.ws.mutate_card(d['id'],d['cards'][0]['id'],{'revision':ready['revision'],'quantity':3})
    assert app.ws.deck(d['id'])['status']=='ready'
    assert app.ws.render_targets([d['id']])['cached']==1
    assert app.ws.render_targets([d['id']])['targets']==[]
    forced=app.ws.render_targets([d['id']],force=True)
    assert forced['cached']==0 and len(forced['targets'])==1
    _,forced_session,_=request(s,'/api/render-sessions',{'deckIds':[d['id']],'force':True})
    assert forced_session['force'] is True and forced_session['pipelineVersion']==PIPELINE_VERSION
    assert len(forced_session['targets'])==1


def test_trash_controls_and_permanent_delete_setting(running):
    app,s=running
    _,d,_=request(s,'/api/decks/new',{'name':'Trash me'})
    assert request(s,'/api/decks/'+d['id']+'/delete',{'revision':d['revision']})[0]==200
    _,trash,_=request(s,'/api/trash');item=next(x for x in trash if x['id']==d['id'])
    assert item['deleted'] is True
    assert request(s,'/api/trash/'+d['id']+'/delete',{'revision':item['revision']})[0]==200
    assert app.store.get('decks',d['id'],include_deleted=True) is None

    ids=[]
    for name in ['one','two']:
        _,deck,_=request(s,'/api/decks/new',{'name':name});ids.append(deck['id'])
        assert request(s,'/api/decks/'+deck['id']+'/delete',{'revision':deck['revision']})[0]==200
    _,out,_=request(s,'/api/trash/empty',{});assert out['deleted']==2
    assert request(s,'/api/trash')[1]==[]

    _,settings,_=request(s,'/api/settings')
    _,settings,_=request(s,'/api/settings',{'deletePermanently':True,'refreshData':True})
    assert settings['deletePermanently'] is True and settings['refreshData'] is True
    # These are real workspace settings, not browser-only state: a fresh read
    # from the server/workspace must retain both of them.
    reread=request(s,'/api/settings')[1]
    assert reread['deletePermanently'] is True and reread['refreshData'] is True
    assert app.ws.global_settings()['deletePermanently'] is True and app.ws.global_settings()['refreshData'] is True
    _,deck,_=request(s,'/api/decks/new',{'name':'Skip trash'})
    assert request(s,'/api/decks/'+deck['id']+'/delete',{'revision':deck['revision']})[0]==200
    assert app.store.get('decks',deck['id'],include_deleted=True) is None
    assert request(s,'/api/trash')[1]==[]

def test_trash_ui_and_missing_generation_contracts():
    root=Path(__file__).resolve().parents[1]
    settings=(root/'site/settings.js').read_text(encoding='utf-8')
    deck=(root/'site/deck.js').read_text(encoding='utf-8')
    render=(root/'site/render.js').read_text(encoding='utf-8')
    for token in ['permanent-delete','global-refresh','data-trash-inspect','data-trash-delete','empty-trash','/api/trash/empty',"$('#permanent-delete').onchange","$('#global-refresh').onchange",'persistToggle','Object.assign(settings,out)','Saved immediately.']:
        assert token in settings
    assert 'id=\"save-settings\"' not in settings and "$('#save-settings')" not in settings
    assert 'deletePermanently' in deck
    assert 'before.upgradeRequired' in render
    assert 'download-diagnostics' in settings and '/api/diagnostics.zip' in settings and 'downloadBlob' in settings


def test_template_validation_and_seed(running):
    app,s=running
    for kind in ['normal','land','legend-land']:
        status,seed,_=request(s,'/api/templates/seed?kind='+kind)
        assert status==200 and 'artBounds' in seed
    t={'name':'Personal frame','groups':['standard'],'legendary':False,'data':seed}
    status,t,_=request(s,'/api/templates',t);assert status==200
    bad=dict(seed,onload='https://evil.example/script.js')
    assert request(s,'/api/templates',{'data':bad,'groups':['standard']})[0]==400


def test_backup_restore_copies_and_omits_runtime_fonts(running):
    app,s=running
    d=app.ws.new_deck('Keep me')
    app.store.add_asset(b'fake-font','font/ttf')
    backup=app.backups.export()
    path=app.store.home/'backups'/backup['filename']
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist())=={'workspace.json','assets/'+d['settings']['backAsset']+'.png'}
    result=app.backups.restore(path)
    assert result['decks']==1
    assert len(app.ws.list_decks())==2
    assert app.ws.deck(d['id'])['name']=='Keep me'
    assert result['ids'][0]!=d['id']


def test_bad_backup_is_rejected_before_deck_mutation(running):
    app,s=running
    p=app.store.home/'tmp'/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../bad.txt','bad')
    with pytest.raises(ValueError):app.backups.restore(p)
    assert not app.ws.list_decks()


def test_uploaded_file_name_never_becomes_a_local_path(running):
    app,s=running
    status,a,_=request(s,'/api/uploads',png(),headers={'X-Filename':'..%2F..%2Fevil.png'})
    assert status==200 and a['stem']=='evil'
    assert not (app.store.home/'evil.png').exists()
    assert app.store.asset(a['id'])


def test_symbol_and_back_uploads_trim_only_fully_transparent_edges(running):
    app,s=running
    status,symbol,_=request(s,'/api/uploads?kind=symbol',padded_png((100,80),(10,15,70,55)),headers={'X-Filename':'rare.png'})
    assert status==200 and (symbol['width'],symbol['height'])==(60,40)
    status,back,_=request(s,'/api/uploads?kind=back',padded_png((400,600),(25,40,325,460),(15,40,80,255)),headers={'X-Filename':'back.png'})
    assert status==200 and (back['width'],back['height'])==(300,420)
    status,plain,_=request(s,'/api/uploads',padded_png((100,80),(10,15,70,55)),headers={'X-Filename':'art.png'})
    assert status==200 and (plain['width'],plain['height'])==(100,80)

def test_back_catalog_and_composition_endpoint(running):
    app,s=running
    status,cat,_=request(s,'/api/backs/catalog');assert status==200
    assert cat['iconBounds']=={'x':207,'y':450,'size':640}
    _,image,_=request(s,'/api/uploads',png((1200,400)),headers={'X-Filename':'test_icon.png'})
    status,result,_=request(s,'/api/backs/compose',{'iconAsset':image['id']});assert status==200
    assert result['placement']['placedBounds']==[207,663,640,213]
    assert (result['width'],result['height'])==(1055,1491)
    assert request(s,'/api/backs/compose',{'iconAsset':image['id']},headers={'X-Proxy-CSRF':'wrong'})[0]==403
    assert request(s.runtime_server,'/api/backs/catalog')[0]==404
