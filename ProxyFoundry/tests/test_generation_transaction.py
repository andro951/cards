"""Generation publishes a complete deck once and preserves the prior deck on failure."""
import json,sqlite3
from pathlib import Path
import pytest
from foundry.browser import BrowserJobs,request
from foundry.domain import ConflictError,ValidationError
from foundry.render_journal import commit_render_rows
from test_render_journal import fixture,receipt


def call(app,path,data):
    return request(app,'POST',path,json.dumps(data).encode())


def test_generation_has_one_durable_commit_and_reopens_with_all_faces(tmp_path):
    app,snapshots,deck=fixture(tmp_path);count=len(snapshots)
    session=app.store.begin_generation(['deck'])
    deck['name']='Updated';app.store.put('decks',deck,deck['revision'])
    rows=[receipt(app,n)[1] for n in range(1,4)]
    assert commit_render_rows(app,rows)=={'registered':3}
    assert len(snapshots)==count
    app.store.commit_generation(session['id'])
    assert len(snapshots)==count+1 and app.store._defer_checkpoint==0
    durable=tmp_path/'durable.sqlite3';durable.write_bytes(snapshots[-1])
    with sqlite3.connect(durable) as db:
        assert db.execute('SELECT count(*) FROM renders').fetchone()[0]==3
        assert 'Updated' in db.execute("SELECT body FROM documents WHERE kind='decks'").fetchone()[0]


def test_abort_preserves_durable_database_and_old_render_bytes(tmp_path):
    app,snapshots,deck=fixture(tmp_path);_,old=receipt(app,1)
    commit_render_rows(app,[old]);durable=snapshots[-1];count=len(snapshots)
    session=app.store.begin_generation(['deck']);deck['name']='Temporary'
    app.store.put('decks',deck,deck['revision'])
    _,new=receipt(app,1,'blue');commit_render_rows(app,[new])
    app.store.abort_generation(session['id'])
    assert len(snapshots)==count and snapshots[-1]==durable
    assert app.store.render_get(old['key'])['asset_id']==old['hash']
    assert app.store.asset_path(old['hash']).exists()
    assert app.store.get('decks','deck').get('name')!='Temporary'
    assert app.store._defer_checkpoint==0


@pytest.mark.parametrize('accepted',[False,True])
def test_failed_final_save_restores_old_database_even_after_write_accepted(tmp_path,accepted):
    app,snapshots,deck=fixture(tmp_path);session=app.store.begin_generation(['deck'])
    deck['name']='Do not publish';app.store.put('decks',deck,deck['revision'])
    persist=app.store.persist;attempts=[]
    def fail_once(path):
        attempts.append(1)
        if len(attempts)==1:
            if accepted:persist(path)
            raise OSError('Final write failed')
        persist(path)
    app.store.persist=fail_once
    with pytest.raises(OSError,match='Final write failed'):app.store.commit_generation(session['id'])
    assert app.store.generation is None and app.store._defer_checkpoint==0
    assert app.store.get('decks','deck').get('name')!='Do not publish'
    durable=tmp_path/'durable.sqlite3';durable.write_bytes(snapshots[-1])
    with sqlite3.connect(durable) as db:
        assert 'Do not publish' not in db.execute("SELECT body FROM documents WHERE kind='decks'").fetchone()[0]


def test_incomplete_or_damaged_manifest_cannot_partially_publish(tmp_path):
    app,snapshots,_=fixture(tmp_path);count=len(snapshots)
    session=app.store.begin_generation(['deck']);rows=[receipt(app,n)[1] for n in range(1,4)]
    response=call(app,'/api/generation/commit',{'id':session['id'],'rows':rows[:1]})
    assert response['status']==400 and not app.store.render_get(rows[0]['key'])
    app.store.asset_path(rows[2]['hash']).unlink()
    with pytest.raises(FileNotFoundError):commit_render_rows(app,rows)
    assert not app.store.render_get(rows[0]['key']) and len(snapshots)==count
    app.store.abort_generation(session['id'])


def test_generation_pauses_unrelated_jobs_and_abort_closes_owned_generator(tmp_path):
    app,_,_=fixture(tmp_path);app.jobs=BrowserJobs(app.store);calls=[]
    app.jobs.start('Earlier task',lambda update,cancel:calls.append('other'))
    session=app.store.begin_generation(['deck'])
    def prepare(update,cancel):
        try:calls.append('prepare');yield
        finally:calls.append('closed')
    app.jobs.start('Generation',prepare);app.jobs.run_pending(limit=1)
    assert calls==['prepare']
    assert call(app,'/api/generation/abort',session)['status']==200
    assert calls==['prepare','closed']
    app.jobs.run_pending();assert calls==['prepare','closed','other']
    assert json.loads(call(app,'/api/generation/abort',session)['body'])=={'aborted':False}


def test_generation_rejects_overlap_and_stale_session(tmp_path):
    app,_,_=fixture(tmp_path);session=app.store.begin_generation(['deck'])
    with pytest.raises(ConflictError):app.store.begin_generation(['deck'])
    with pytest.raises(ConflictError):app.store.commit_generation('stale')
    response=call(app,'/api/settings',{'artist':'Do not lose this edit'})
    assert response['status']==409 and 'Wait before making other workspace changes' in json.loads(response['body'])['error']
    app.store.abort_generation(session['id'])
