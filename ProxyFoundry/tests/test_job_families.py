"""Cooperative imports/exports keep cancellation and publication atomic."""
import copy,json,zipfile
import pytest
from foundry.browser import create_app,request
from foundry.domain import GENERATION_VERSION,uid
from foundry.images import ingest_image
from foundry.workspace import DEFAULT_SETTINGS
from test_github_setup import BundleRemote,png


@pytest.fixture
def app(tmp_path):
    remote=BundleRemote(back='custom')
    raw=png(size=(30,42))
    def transport(url):
        if url.startswith('https://cards.scryfall.io/'):return raw,'image/png',{}
        return remote.transport(url)
    value=create_app(tmp_path,transport,'http://127.0.0.1:8767')
    front=ingest_image(value.store,raw);value.store.render_put('front',front)
    template_key,template_version,_=value.ws.compiler.template_identity('standard','auto')
    cards=[]
    for index in range(3):
        name='Card '+str(index)
        cards.append({'id':uid(),'name':name,'quantity':1,'scryfall':{'name':name,'layout':'normal','image_uris':{
            'png':'https://cards.scryfall.io/'+str(index)+'.png','art_crop':'https://cards.scryfall.io/'+str(index)+'-art.png'}},
            'faces':[{'id':uid(),'name':name,'compiled':{'renderKey':'front','generationVersion':GENERATION_VERSION,
                'templateKey':template_key,'templateVersion':template_version}}]})
    deck=value.store.put('decks',{'name':'Export source','settings':dict(DEFAULT_SETTINGS,backAsset=front['id']),
        'status':'prepared','cards':cards})
    value.fixture_deck=deck;value.fixture_remote=remote
    yield value
    value.close()


def start(app,kind):
    ident=app.fixture_deck['id'];url=app.fixture_remote.url
    path,payload={
        'github':('/api/setup/github-import',{'url':url}),
        'symbols':('/api/setup/symbols/github',{'url':url+'/set_symbols'}),
        'order':('/api/orders/build',{'deckIds':[ident]}),
        'backup':('/api/backups/export',{'includeRenders':True}),
        'originals':('/api/decks/'+ident+'/originals',{}),
        'cropped-art':('/api/decks/'+ident+'/cropped-art',{}),
        'review-images':('/api/decks/'+ident+'/review-images',{}),
    }[kind]
    response=request(app,'POST',path,json.dumps(payload).encode())
    assert response['status']==200,response
    return json.loads(response['body'])['id']


@pytest.mark.parametrize('kind',['github','symbols','order','backup','originals','cropped-art','review-images'])
@pytest.mark.parametrize('cancel',[False,True],ids=['complete','cancel'])
def test_import_export_routes_yield_and_preserve_or_cleanup_results(app,kind,cancel):
    before=copy.deepcopy(app.store.get('decks',app.fixture_deck['id']))
    ident=start(app,kind)
    assert app.jobs.get(ident)['state']=='queued'
    app.jobs.run_pending(limit=1)
    assert app.jobs.get(ident)['state']=='running'
    assert request(app,'GET','/api/bootstrap')['status']==200
    if cancel:app.jobs.cancel(ident)
    app.jobs.run_pending()
    job=app.jobs.get(ident)
    assert job['state']==('cancelled' if cancel else 'done'),job
    assert not app.store._asset_pins and not app.store._deferred_asset_deletes
    assert app.store.get('decks',before['id'])==before
    assert not list((app.store.home/'orders').glob('*.partial'))
    assert not list((app.store.home/'backups').glob('*.partial'))
    if cancel:
        assert not app.store.list('orders')
        assert not list((app.store.home/'orders').glob('*.zip'))
        assert not list((app.store.home/'backups').glob('*.zip'))
    elif kind in {'github','symbols'}:
        symbols=job['result'].get('symbols') or job['result']['settings']['symbols']
        assert len(symbols)==4 and all(app.store.asset(value) for value in symbols.values())
        assert not any('/art/' in value for value in app.fixture_remote.calls)
    else:
        result=job['result']
        path=app.store.home/('backups' if kind=='backup' else 'orders')/(result.get('filename') or result['id']+'.zip')
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            if kind!='backup':assert len(archive.namelist())==(6 if kind=='order' else 3)
            if kind in {'originals','cropped-art'}:
                assert all(archive.read(name)==png(size=(30,42)) for name in archive.namelist())
            elif kind=='backup':
                manifest=json.loads(archive.read('workspace.json'))
                front=app.fixture_deck['settings']['backAsset']
                assert archive.read('assets/'+front+'.png')==png(size=(30,42))
                assert manifest['documents']['decks'][0]['cards']==before['cards']


@pytest.mark.parametrize('change',['edit','delete','cancel-final'])
def test_order_final_boundary_rejects_stale_or_cancelled_publication(app,change):
    ident=start(app,'order')
    for _ in range(3):app.jobs.run_pending(limit=1)
    assert app.jobs.get(ident)['done']==3 and app.jobs.get(ident)['state']=='running'
    deck=app.fixture_deck
    if change=='edit':app.store.put('decks',{**deck,'name':'New name'},deck['revision'])
    elif change=='delete':app.store.trash('decks',deck['id'],deck['revision'])
    else:app.jobs.cancel(ident)
    app.jobs.run_pending()
    job=app.jobs.get(ident)
    assert job['state']==('cancelled' if change=='cancel-final' else 'failed')
    if change!='cancel-final':assert 'changed while packaging' in job['error']
    assert not app.store.list('orders') and not list((app.store.home/'orders').iterdir())


def test_github_cancellation_after_last_asset_does_not_publish_a_setup(app):
    ident=start(app,'github')
    while app.jobs.get(ident)['done']<5:app.jobs.run_pending(limit=1)
    assert app.jobs.get(ident)['state']=='running'
    app.jobs.cancel(ident);app.jobs.run_pending()
    assert app.jobs.get(ident)['state']=='cancelled'
    assert 'result' not in app.jobs.get(ident)
    assert app.store.get('decks',app.fixture_deck['id'])==app.fixture_deck


@pytest.mark.parametrize('kind',['order','backup'])
def test_archive_write_failure_cleans_partial_and_releases_queue(app,kind,monkeypatch):
    def fail(*args,**kwargs):raise OSError(51,'Full')
    monkeypatch.setattr(zipfile.ZipFile,'write',fail)
    ident=start(app,kind)
    other=app.jobs.start('Unrelated foreground',lambda update,cancel:{'ok':True})['id']
    app.jobs.run_pending()
    assert app.jobs.get(ident)['state']=='failed'
    assert 'storage is full' in app.jobs.get(ident)['error']
    assert app.jobs.get(other)['result']=={'ok':True}
    assert not app.store.list('orders')
    assert not list((app.store.home/'orders').iterdir())
    assert not list((app.store.home/'backups').iterdir())
    assert not app.store._asset_pins and not app.store._deferred_asset_deletes


@pytest.mark.parametrize('kind',['backup','review-images'])
def test_export_snapshot_keeps_assets_during_foreground_deletion(app,kind):
    ident=start(app,kind);app.jobs.run_pending(limit=1)
    deck=app.fixture_deck;front=deck['settings']['backAsset']
    app.store.begin_delete('decks',deck['id'],deck['revision']);app.store.clear_renders()
    assert app.store.asset(front) and app.store._asset_pins[front]>0
    app.jobs.run_pending()
    job=app.jobs.get(ident);assert job['state']=='done',job
    path=app.store.home/('backups' if kind=='backup' else 'orders')/job['result']['filename']
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        if kind=='backup':assert archive.read('assets/'+front+'.png')==png(size=(30,42))
        else:assert len(archive.namelist())==3
    assert not app.store._asset_pins and not app.store._deferred_asset_deletes
    assert app.store.asset(front) is None