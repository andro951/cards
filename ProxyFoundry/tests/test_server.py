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
from foundry.workspace import Workspace


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
    bad.write_bytes(b'{"id":"legacy","message":"bad '+bytes([0x81])+b' byte","result":{"large":"omit"}}')
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


def _review_test_png(size,color):
    out=io.BytesIO();Image.new('RGBA',size,color).save(out,'PNG');return out.getvalue()


def test_review_images_export_pairs_scryfall_printing_with_rendered_faces(tmp_path):
    store=Store(tmp_path)
    reference={
        'https://cards.scryfall.io/png/front/review_normal.png':_review_test_png((100,140),(220,30,30,255)),
        'https://cards.scryfall.io/png/front/review_transform.png':_review_test_png((100,140),(30,220,30,255)),
        'https://cards.scryfall.io/png/back/review_back.png':_review_test_png((100,140),(30,30,220,255)),
    }
    def transport(url):
        if url in reference:return reference[url],'image/png',{}
        raise AssertionError('Unexpected review-image URL: '+url)
    app=App(store,Network(store,transport=transport,sleeper=lambda _:None))
    normal={'id':'11111111-1111-4111-8111-111111111111','name':'Review Normal','layout':'normal','type_line':'Creature — Human','set':'tst','collector_number':'10',
            'image_uris':{'png':'https://cards.scryfall.io/png/front/review_normal.png'}}
    dfc={'id':'22222222-2222-4222-8222-222222222222','name':'Review Transform // Review Back','layout':'transform','set':'tst','collector_number':'11',
         'card_faces':[
             {'name':'Review Transform','type_line':'Creature — Human','image_uris':{'png':'https://cards.scryfall.io/png/front/review_transform.png'}},
             {'name':'Review Back','type_line':'Land','image_uris':{'png':'https://cards.scryfall.io/png/back/review_back.png'}}]}
    deck=store.put('decks',{'name':'Review Deck','cards':[
        {'id':'normal-card','name':'Review Normal','quantity':1,'scryfall':normal,'faces':[{'id':'normal-face','name':'Review Normal','index':0}]},
        {'id':'dfc-card','name':'Review Transform // Review Back','quantity':1,'scryfall':dfc,'faces':[{'id':'dfc-front','name':'Review Transform','index':0},{'id':'dfc-back','name':'Review Back','index':1}]},
    ],'settings':{'refreshData':False,'templateRules':{}},'status':'draft','notes':'','importedSource':''})
    deck=app.ws.deck(deck['id'])
    colors=[(240,180,20,255),(20,180,240,255),(180,20,240,255)];n=0
    deck_back=ingest_image(store,_review_test_png((101,141),(5,5,5,255)))['id'];deck['settings']['backAsset']=deck_back
    for c in deck['cards']:
        for f in c['faces']:
            asset=ingest_image(store,_review_test_png((101,141),colors[n]));n+=1
            key=(str(n)*64)[:64];render=store.render_put(key,asset)
            template_key,template_version,_=app.ws.compiler.template_identity(f['group'],'auto')
            f['compiled']={'renderKey':key,'generationVersion':PIPELINE_VERSION,'templateKey':template_key,'templateVersion':template_version}
    deck['status']='prepared';deck=store.put('decks',deck,deck['revision'])
    assert app.ws.deck(deck['id'])['status']=='ready'
    out=app.ws.review_images(deck['id'])
    assert all(store.cache_get(url) is None for url in reference)
    with zipfile.ZipFile(store.home/'orders'/out['filename']) as z:
        assert set(z.namelist())=={'review_normal_review.png','review_transform_review.png','review_back_review.png'}
        assert out['count']==3
        image=Image.open(io.BytesIO(z.read('review_normal_review.png')));image.load()
        assert image.size==(203,141)
        assert image.getpixel((5,5))[:3]==(220,30,30)
        assert image.getpixel((101,5))[:3]==(0,0,0)
        assert image.getpixel((150,5))[:3]==(240,180,20)
        back=Image.open(io.BytesIO(z.read('review_back_review.png')));back.load()
        assert back.getpixel((5,5))[:3]==(30,30,220)
        assert back.getpixel((150,5))[:3]==(180,20,240)
    app.close()



def test_review_images_export_is_single_worker_and_reaches_complete_progress(tmp_path):
    import threading
    store=Store(tmp_path)
    urls={f'https://cards.scryfall.io/png/front/review_{i}.png':_review_test_png((100,140),(20*i,40,80,255)) for i in range(1,5)}
    active=0;max_active=0;lock=threading.Lock()
    def transport(url):
        nonlocal active,max_active
        if url not in urls:raise AssertionError('Unexpected review-image URL: '+url)
        with lock:
            active+=1;max_active=max(max_active,active)
        try:
            time.sleep(.01)
            return urls[url],'image/png',{}
        finally:
            with lock:active-=1
    app=App(store,Network(store,transport=transport,sleeper=lambda _:None))
    cards=[]
    for i,url in enumerate(urls,1):
        sf={'id':f'00000000-0000-4000-8000-{i:012d}','name':f'Review {i}','layout':'normal','type_line':'Creature — Human','set':'tst','collector_number':str(i),'image_uris':{'png':url}}
        face={'id':f'face-{i}','name':f'Review {i}','index':0}
        cards.append({'id':f'card-{i}','name':f'Review {i}','quantity':1,'scryfall':sf,'faces':[face]})
    deck=store.put('decks',{'name':'Sequential Reviews','cards':cards,'settings':{'refreshData':False,'templateRules':{}},'status':'prepared','notes':'','importedSource':''})
    d=app.ws.deck(deck['id'])
    for i,c in enumerate(d['cards'],1):
        f=c['faces'][0];asset=ingest_image(store,_review_test_png((101,141),(10*i,120,180,255)));key=(str(i)*64)[:64]
        store.render_put(key,asset,deck_id=d['id'],card_id=c['id'],face_id=f['id'],deck_name=d['name'],face_name=f['name'])
        template_key,template_version,_=app.ws.compiler.template_identity(f['group'],'auto')
        f['compiled']={'renderKey':key,'generationVersion':PIPELINE_VERSION,'templateKey':template_key,'templateVersion':template_version}
    d['status']='prepared';store.put('decks',d,d['revision'])
    progress=[]
    out=app.ws.review_images(d['id'],lambda done,total,message:progress.append((done,total,message)))
    assert out['count']==4
    assert max_active==1
    assert progress[-1][0:2]==(4,4)
    assert all(store.cache_get(url) is None for url in urls)
    app.close()

def test_cropped_art_export_uses_compiled_window_and_readable_names(tmp_path):
    store=Store(tmp_path)
    source=Image.new('RGB',(100,100),'red')
    source.paste('green',(50,0,100,50));source.paste('blue',(0,50,50,100));source.paste('yellow',(50,50,100,100))
    raw=io.BytesIO();source.save(raw,'PNG');art=ingest_image(store,raw.getvalue())
    ws=Workspace(store,Network(store,transport=lambda url: (png(),'image/png',{}),sleeper=lambda _:None))
    deck={'id':'deck','name':'Crop Deck','status':'prepared','cards':[{
        'id':'card','name':'Card: One','faces':[{
            'id':'face','name':'Card: One','compiled':{
                'artId':art['id'],
                'data':{'width':100,'height':100,'marginX':0,'marginY':0,
                        'artBounds':{'x':.25,'y':.25,'width':.5,'height':.5},
                        'artX':0,'artY':0,'artZoom':1,'artRotate':0}
            }
        }]
    }]}
    ws.deck=lambda ident: deck
    out=ws.cropped_art('deck')
    with zipfile.ZipFile(store.home/'orders'/out['filename']) as archive:
        assert archive.namelist()==['Card One.png']
        image=Image.open(io.BytesIO(archive.read('Card One.png')));image.load()
        assert image.size==(50,50)
        assert image.getpixel((0,0))[:3]==(255,0,0)
        assert image.getpixel((49,0))[:3]==(0,128,0)
        assert image.getpixel((0,49))[:3]==(0,0,255)
        assert image.getpixel((49,49))[:3]==(255,255,0)


def test_download_cropped_art_is_in_deck_actions_menu():
    source=(Path(__file__).resolve().parents[1]/'site/deck.js').read_text(encoding='utf-8')
    assert 'Download Cropped Art' in source
    assert '/cropped-art' in source


def test_review_images_export_uses_one_background_job_and_transient_fetches():
    root=Path(__file__).resolve().parents[1]
    workspace=(root/'foundry/workspace.py').read_text(encoding='utf-8')
    network=(root/'foundry/network.py').read_text(encoding='utf-8')
    review=workspace[workspace.index('    def review_images'):]
    assert 'ThreadPoolExecutor' not in review
    assert 'as_completed(' not in review
    assert "self._review_composite(url,render,refresh)" in review
    assert "fetch_transient(reference_url)" in workspace
    assert "def fetch_transient" in network


def test_review_images_action_is_in_deck_menu():
    source=(Path(__file__).resolve().parents[1]/'site/deck.js').read_text(encoding='utf-8')
    assert 'Download review Images' in source
    assert '/review-images' in source
    handler=source[source.index("$('#download-review-images')"):source.index("$('#use-as-defaults')")]
    assert 'needsGeneration' in handler
    assert "await generate(current)" in handler
    assert handler.index("await generate(current)") < handler.index("/review-images")
    assert 'Some card images could not be generated.' in handler


def test_single_review_image_export_can_download_a_specific_face_png(tmp_path):
    store=Store(tmp_path)
    reference={
        'https://cards.scryfall.io/png/front/review_transform.png':_review_test_png((100,140),(30,220,30,255)),
        'https://cards.scryfall.io/png/back/review_back.png':_review_test_png((100,140),(30,30,220,255)),
    }
    def transport(url):
        if url in reference:return reference[url],'image/png',{}
        raise AssertionError('Unexpected review-image URL: '+url)
    app=App(store,Network(store,transport=transport,sleeper=lambda _:None))
    dfc={'id':'22222222-2222-4222-8222-222222222222','name':'Review Transform // Review Back','layout':'transform','set':'tst','collector_number':'11',
         'card_faces':[
             {'name':'Review Transform','type_line':'Creature — Human','image_uris':{'png':'https://cards.scryfall.io/png/front/review_transform.png'}},
             {'name':'Review Back','type_line':'Land','image_uris':{'png':'https://cards.scryfall.io/png/back/review_back.png'}}]}
    deck=store.put('decks',{'name':'Review Deck','cards':[
        {'id':'dfc-card','name':'Review Transform // Review Back','quantity':1,'scryfall':dfc,'faces':[{'id':'dfc-front','name':'Review Transform','index':0},{'id':'dfc-back','name':'Review Back','index':1}]},
    ],'settings':{'refreshData':False,'templateRules':{}},'status':'draft','notes':'','importedSource':''})
    deck=app.ws.deck(deck['id'])
    colors=[(20,180,240,255),(180,20,240,255)]
    for n,f in enumerate(deck['cards'][0]['faces']):
        asset=ingest_image(store,_review_test_png((101,141),colors[n]))
        key=(str(n+1)*64)[:64];render=store.render_put(key,asset)
        template_key,template_version,_=app.ws.compiler.template_identity(f.get('group'),'auto')
        f['compiled']={'renderKey':key,'render':render,'generationVersion':PIPELINE_VERSION,'templateKey':template_key,'templateVersion':template_version}
    deck['status']='prepared';deck=store.put('decks',deck,deck['revision'])
    out=app.ws.review_image(deck['id'],'dfc-card','dfc-back')
    path=store.home/'orders'/out['filename']
    assert path.suffix=='.png' and out['download'].endswith('.png')
    image=Image.open(path);image.load()
    assert image.size==(203,141)
    assert image.getpixel((5,5))[:3]==(30,30,220)
    assert image.getpixel((150,5))[:3]==(180,20,240)
    app.close()


def test_render_targets_for_card_only_returns_the_requested_card_even_while_deck_is_draft(tmp_path):
    store=Store(tmp_path)
    app=App(store,Network(store,transport=lambda url: (png(),'image/png',{}),sleeper=lambda _:None))
    deck={'id':'deck-1','name':'Render card deck','status':'draft','cards':[
        {'id':'card-one','name':'Alpha','quantity':1,'scryfall':card('Alpha'),'faces':[{'id':'face-one','name':'Alpha','index':0,'compiled':{'renderKey':'1'*64,'data':{'width':1,'height':1}}}]},
        {'id':'card-two','name':'Beta','quantity':1,'scryfall':card('Beta'),'faces':[{'id':'face-two','name':'Beta','index':0,'compiled':{'renderKey':'2'*64,'data':{'width':1,'height':1}}}]},
    ]}
    app.ws.deck=lambda ident: deck
    plan=app.ws.render_targets_for_card(deck['id'],'card-two')
    assert plan['cardName']=='Beta'
    assert [t['name'] for t in plan['targets']]==['Beta']
    assert [t['key'] for t in plan['targets']]==['2'*64]
    app.close()


def test_single_card_prepare_endpoint_never_calls_full_deck_prepare(running):
    app,s=running
    _,art,_=request(s,'/api/uploads',png(),headers={'X-Filename':'sample_card.png'})
    _,back,_=request(s,'/api/uploads',png((300,420),'#223355'))
    _,symbols,_=request(s,'/api/symbols/generate',{'assetId':art['id']})
    d=job_done(s,'/api/decks/import',{'name':'Single prepare','source':'1 Sample Card','settings':{'symbols':symbols,'backAsset':back['id']}})
    d=job_done(s,'/api/decks/'+d['id']+'/prepare',{})
    c=d['cards'][0];f=c['faces'][0];before=f['compiled']['renderKey']
    other=json.loads(json.dumps(c));other['id']='22222222-2222-4222-8222-222222222222';other['name']='Untouched Card'
    other['faces'][0]['id']='33333333-3333-4333-8333-333333333333';other['faces'][0]['name']='Untouched Card'
    other['faces'][0]['compiled']['data']['_single_prepare_sentinel']='keep-me'
    stored=app.store.get('decks',d['id']);stored['cards'].append(other);stored.pop('summary',None)
    d=app.store.put('decks',stored,stored['revision']);d=app.ws.deck(d['id'])
    _,d,_=request(s,'/api/decks/'+d['id']+'/cards/'+c['id'],{'revision':d['revision'],'faceId':f['id'],'semanticOverrides':{'oracle_text':'Reach'}})
    assert d['status']=='draft'
    app.ws.prepare=lambda *a,**k: (_ for _ in ()).throw(AssertionError('full deck prepare must not run'))
    d=job_done(s,'/api/decks/'+d['id']+'/cards/'+c['id']+'/prepare',{})
    assert d['status']!='draft'
    selected=next(x for x in d['cards'] if x['id']==c['id'])['faces'][0]
    untouched=next(x for x in d['cards'] if x['id']==other['id'])['faces'][0]
    assert selected['compiled']['renderKey']!=before
    assert selected['compiled']['data']['text']['rules']['text']=='Reach'
    assert untouched['compiled']['data']['_single_prepare_sentinel']=='keep-me'
    _,plan,_=request(s,'/api/render-sessions/card',{'deckId':d['id'],'cardId':c['id']})
    assert len(plan['targets'])==1 and plan['targets'][0]['name']=='Sample Card'


def test_single_card_prepare_keeps_deck_draft_when_another_face_is_pending(running):
    app,s=running
    _,art,_=request(s,'/api/uploads',png(),headers={'X-Filename':'sample_card.png'})
    _,back,_=request(s,'/api/uploads',png((300,420),'#223355'))
    _,symbols,_=request(s,'/api/symbols/generate',{'assetId':art['id']})
    d=job_done(s,'/api/decks/import',{'name':'Two pending cards','source':'1 Sample Card','settings':{'symbols':symbols,'backAsset':back['id']}})
    d=job_done(s,'/api/decks/'+d['id']+'/prepare',{})
    stored=app.store.get('decks',d['id']);other=json.loads(json.dumps(stored['cards'][0]))
    other['id']='22222222-2222-4222-8222-222222222222';other['name']='Other Sample';other['faces'][0]['id']='33333333-3333-4333-8333-333333333333';other['faces'][0]['name']='Other Sample'
    stored['cards'].append(other);d=app.store.put('decks',stored,stored['revision']);d=app.ws.deck(d['id'])
    first=d['cards'][0];other=d['cards'][1]
    _,d,_=request(s,'/api/decks/'+d['id']+'/cards/'+first['id'],{'revision':d['revision'],'faceId':first['faces'][0]['id'],'semanticOverrides':{'oracle_text':'Reach'}})
    _,d,_=request(s,'/api/decks/'+d['id']+'/cards/'+other['id'],{'revision':d['revision'],'faceId':other['faces'][0]['id'],'semanticOverrides':{'oracle_text':'Flying'}})
    d=job_done(s,'/api/decks/'+d['id']+'/cards/'+first['id']+'/prepare',{})
    assert d['status']=='draft'
    assert next(x for x in d['cards'] if x['id']==other['id'])['faces'][0].get('compiled') is None


def test_card_inspector_actions_exist_in_source():
    source=(Path(__file__).resolve().parents[1]/'site/deck.js').read_text(encoding='utf-8')
    assert 'Generate this card' in source
    assert 'Download review image' in source
    assert '/review-image' in source
    inspect=source[source.index('async function inspect'):source.index('async function printings')]
    assert "'/api/decks/'+d.id+'/cards/'+c.id+'/prepare'" in inspect
    assert "job('/api/decks/'+d.id+'/prepare'" not in inspect
    generate=inspect[inspect.index("$('#generate-card')"):inspect.index("$('#download-review-image')")]
    assert 'await prepareCard();' in generate
    assert 'await prepareIfNeeded();' not in generate
    assert 'This card already matches the cached render.' in inspect
    assert 'Regenerating it now should produce the same image.' in inspect
    assert 'Regenerate anyway' in inspect
    assert 'Recommended source shape: <b>5:7</b>.' in inspect
    assert 'colorlessCreature' in inspect
    assert "const hasPhysicalReverse=c=>c.faces.length===2||Boolean(c.meldBackAsset||c.scryfall?._meld_result);" in source
    assert 'async function inspectMeldReverse' in source
    assert 'Use actual meld reverse' in source
    assert 'attempt(()=>inspectMeldReverse(d,c))' in inspect
    assert 'hasPhysicalReverse(c)?' in inspect
    render=(Path(__file__).resolve().parents[1]/'site/render.js').read_text(encoding='utf-8')
    assert '/api/render-sessions/card' in render

