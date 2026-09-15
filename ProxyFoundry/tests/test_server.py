from __future__ import annotations
import io,json,threading,urllib.request,urllib.error,zipfile,time
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants


def png(size=(900,600),color='#aa7733'):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return out.getvalue()

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
    assert request(s,'/api/bootstrap')[1]['runtimeOrigin']!=s.origin
    assert request(s,'/api/decks/new',{'name':'x'},headers={'X-Proxy-CSRF':'bad'})[0]==403
    assert request(s,'/api/decks/new',{'name':'x'},origin='https://evil.example')[0]==403
    r=s.runtime_server
    assert request(r,'/api/bootstrap')[0]==404
    assert request(r,'/api/decks/new',{'name':'x'})[0]==403
    assert request(s,'/api/bootstrap',headers={'Host':'evil.example'})[0]==403


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
        assert z.namelist()==['workspace.json']
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
