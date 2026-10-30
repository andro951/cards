"""Browser-native packaging preserves order snapshots and failure cleanup."""
import zipfile
import pytest
from foundry.domain import ConflictError,ValidationError
from test_job_families import app


@pytest.fixture(autouse=True)
def prepared_card_metadata(app):
    #The shared export fixture predates required semantic/template metadata.
    from foundry.compiler import NORMAL_ART_ANCHOR_VERSION
    deck=app.fixture_deck
    for card in deck['cards']:
        sf=card['scryfall'];sf.update(type_line='Artifact',colors=[])
        face=card['faces'][0]
        key,version,_=app.ws.compiler.template_identity_for_face('standard','auto',sf,sf,0,face)
        face['compiled'].update(templateKey=key,templateVersion=version,data={'normalArtAnchorVersion':NORMAL_ART_ANCHOR_VERSION})
    app.fixture_deck=app.store.put('decks',deck,deck['revision'])


class NativeArchive:
    def __init__(self,app):self.app=app;self.polls=0;self.released=False;self.error=None
    def __call__(self,operation,path,entries=None):
        if operation=='start-order-zip':
            self.entries=entries
            with zipfile.ZipFile(self.app.store.home/path,'w',zipfile.ZIP_STORED) as archive:
                for entry in entries:archive.write(self.app.store.home/entry['path'],entry['name'])
            return {'id':'task'}
        assert path=='task'
        if operation=='release-order-zip':self.released=True;return {'ok':True}
        assert operation=='poll-order-zip'
        self.polls+=1
        if self.error and self.polls>1:return {'state':'failed','error':self.error}
        return {'state':'done' if self.polls>1 else 'running','done':len(self.entries) if self.polls>1 else 2,'message':'Packaging'}


def test_native_archive_keeps_exact_front_back_pairs_and_saved_download(app):
    native=NativeArchive(app);app.orders.archive=native;progress=[]
    result=app.orders.build([app.fixture_deck['id']],progress=lambda *value:progress.append(value))
    assert native.released and progress[-1][:2]==(3,3)
    assert result['count']==3 and result['download']=='/api/orders/'+result['id']+'/download'
    assert app.store.get('orders',result['id'])['snapshotHash']==result['snapshotHash']
    raw=app.store.asset_path(app.fixture_deck['settings']['backAsset']).read_bytes()
    with zipfile.ZipFile(app.store.home/'orders'/(result['id']+'.zip')) as archive:
        assert archive.testzip() is None
        assert archive.namelist()==[side+f'/{index:06d}.png' for index in range(1,4) for side in ('FRONT','BACK')]
        assert all(archive.read(name)==raw for name in archive.namelist())
    assert not app.store._asset_pins


def test_save_bytes_and_finalization_reach_job_progress(app):
    from foundry.browser import BrowserJobs
    native=NativeArchive(app);poll=native.__call__
    statuses=iter([
        {'state':'running','done':6,'message':'Saving paired ZIP','phase':'saving','saveStage':'writing','savedBytes':128,'totalBytes':256,'saveElapsedSeconds':2,'saveBytesPerSecond':64,'saveEtaSeconds':2},
        {'state':'running','done':6,'message':'Finalizing paired ZIP','phase':'saving','saveStage':'finalizing','savedBytes':256,'totalBytes':256,'saveElapsedSeconds':4,'saveEtaSeconds':None},
        {'state':'done','done':6,'message':'Paired ZIP saved','phase':'saving','saveStage':'complete','savedBytes':256,'totalBytes':256}])
    def archive(operation,*args):return next(statuses) if operation=='poll-order-zip' else poll(operation,*args)
    app.orders.archive=archive
    jobs=BrowserJobs(app.store);ident=jobs.start('Package paired order',lambda update,cancel:app.orders.build_steps([app.fixture_deck['id']],progress=update,cancel=cancel))['id']
    jobs.run_pending(limit=1);status=jobs.get(ident)
    assert status['message']=='Saving paired ZIP' and status['savedBytes']==128 and status['saveEtaSeconds']==2
    jobs.jobs[ident]['resumeAt']=0;jobs.run_pending(limit=1);assert jobs.get(ident)['saveStage']=='finalizing'
    jobs.jobs[ident]['resumeAt']=0;jobs.run_pending();assert jobs.get(ident)['state']=='done' and jobs.get(ident)['saveStage']=='complete'
    assert jobs.get(ident)['events'][-3]['phase']=='saving'


@pytest.mark.parametrize('change',['cancel','edit','delete','write-failure'])
def test_native_archive_releases_worker_and_removes_unpublished_files(app,change):
    native=NativeArchive(app);app.orders.archive=native;cancelled=False
    steps=app.orders.build_steps([app.fixture_deck['id']],cancel=lambda:cancelled)
    assert next(steps)=={'delay':.05}
    assert app.store._asset_pins and not app.store.list('orders')
    deck=app.fixture_deck
    if change=='cancel':cancelled=True
    elif change=='edit':app.store.put('decks',{**deck,'name':'Changed'},deck['revision'])
    elif change=='delete':app.store.trash('decks',deck['id'],deck['revision'])
    else:native.error='ZIP storage full'
    with pytest.raises(ValidationError if change in {'cancel','write-failure'} else ConflictError):
        next(steps)
    assert native.released and not app.store._asset_pins
    assert not app.store.list('orders') and not list((app.store.home/'orders').iterdir())
