"""Durable direct render receipts: batching, restart, invalidation and failed checkpoints."""
import hashlib,io,json,logging,shutil,sqlite3
from types import SimpleNamespace
from pathlib import Path
import pytest
from PIL import Image
from foundry.browser import BrowserStore
from foundry.render_journal import commit_render_saves


def fixture(tmp_path):
    snapshots=[]
    store=BrowserStore(tmp_path,lambda path:snapshots.append(Path(path).read_bytes()))
    app=SimpleNamespace(store=store,log=logging.getLogger('render-test'))
    faces=[{'id':f'face-{n}','compiled':{'renderKey':str(n)*64,'data':{'width':40,'height':56}}} for n in range(1,4)]
    deck=store.put('decks',{'id':'deck','cards':[{'id':'card','faces':faces}]})
    return app,snapshots,deck


def receipt(app,number,color='red',key=None):
    out=io.BytesIO();Image.new('RGBA',(40,56),color).save(out,'PNG');raw=out.getvalue();ident=hashlib.sha256(raw).hexdigest()
    asset=app.store.asset_path(ident);asset.parent.mkdir(parents=True,exist_ok=True);asset.write_bytes(raw)
    row={'key':key or str(number)*64,'hash':ident,'bytes':len(raw),'width':40,'height':56,'deckId':'deck','cardId':'card','faceId':f'face-{number}'}
    folder=app.store.home/'tmp'/'render-pending';folder.mkdir(exist_ok=True)
    path=folder/f'{number}.json';path.write_text(json.dumps(row))
    return path,row


def test_batch_has_one_checkpoint_and_shared_files_survive_partial_deletion(tmp_path):
    app,snapshots,_=fixture(tmp_path)
    _,row=receipt(app,1);receipt(app,2);count=len(snapshots)
    assert commit_render_saves(app)=={'registered':2}
    assert len(snapshots)==count+1
    assert commit_render_saves(app)=={'registered':0}
    first=app.store.render_get('1'*64)
    assert first['file_path']==f"assets/{row['hash'][:2]}/{row['hash']}"
    assert not list((tmp_path/'renders').rglob('*.png'))
    #A second deck can refer to the same PNG without owning a duplicate file.
    with app.store.connect() as db:db.execute("UPDATE renders SET deck_id='other' WHERE render_key=?",('2'*64,))
    app.store.clear_deck_renders('deck')
    assert app.store.render_get('2'*64)
    app.store.clear_deck_renders('other')
    assert not app.store.asset_path(row['hash']).exists()


def test_reload_recovers_completed_files_and_ignores_changed_or_deleted_faces(tmp_path):
    app,_,deck=fixture(tmp_path);receipt(app,1);receipt(app,2,key='f'*64)
    #Reopen the saved database as a fresh browser engine.
    app.store=BrowserStore(tmp_path)
    assert commit_render_saves(app)['registered']==1
    assert app.store.render_get('1'*64) and not app.store.render_get('f'*64)
    path,row=receipt(app,3)
    app.store.begin_delete('decks','deck',deck['revision'])
    assert commit_render_saves(app)['registered']==0 and not path.exists()
    while app.store.cleanup_step()['pending']:pass
    assert not app.store.render_get('1'*64)


@pytest.mark.parametrize('accepted',[False,True])
def test_failed_checkpoint_keeps_receipts_and_prior_render_until_retry(tmp_path,accepted):
    app,snapshots,_=fixture(tmp_path);receipt(app,1);commit_render_saves(app)
    previous=app.store.render_get('1'*64);path,row=receipt(app,1,'blue');persist=app.store.persist
    def fail(snapshot):
        if accepted:snapshots.append(Path(snapshot).read_bytes())
        raise OSError('disk full')
    app.store.persist=fail
    with pytest.raises(OSError,match='disk full'):commit_render_saves(app)
    assert path.exists() and app.store.render_get('1'*64)['asset_id']==previous['asset_id']
    assert app.store.asset_path(previous['asset_id']).exists()
    app.store.persist=persist
    assert commit_render_saves(app)['registered']==1
    assert app.store.render_get('1'*64)['asset_id']==row['hash']
    while app.store.cleanup_step()['pending']:pass
    assert not app.store.asset_path(previous['asset_id']).exists()


@pytest.mark.parametrize('damage',['missing','truncated','header','size','traversal','json'])
def test_damaged_receipt_does_not_publish_a_cache_hit(tmp_path,damage):
    app,_,_=fixture(tmp_path);path,row=receipt(app,1)
    asset=app.store.asset_path(row['hash'])
    if damage=='missing':asset.unlink()
    elif damage=='truncated':asset.write_bytes(b'bad')
    elif damage=='header':asset.write_bytes(b'bad!!!!!'+asset.read_bytes()[8:])
    elif damage=='size':row['width']=42
    elif damage=='traversal':row['hash']='../../workspace.sqlite3'
    path.write_text('broken' if damage=='json' else json.dumps(row))
    assert commit_render_saves(app)['registered']==0
    assert app.store.render_get('1'*64) is None
    assert path.with_suffix('.rejected').exists()


def test_existing_unique_schema_upgrades_without_losing_render_records(tmp_path):
    from foundry.storage import Store
    store=Store(tmp_path)
    out=io.BytesIO();Image.new('RGB',(40,56),'red').save(out,'PNG')
    asset=store.add_asset(out.getvalue(),'image/png',40,56)
    store.render_put('a'*64,asset,face_id='face')
    reopened=BrowserStore(tmp_path)
    assert reopened.render_get('a'*64)['asset_id']==asset['id']
    with reopened.connect() as db:
        schema=db.execute("SELECT sql FROM sqlite_master WHERE name='renders'").fetchone()[0]
    assert 'file_path TEXT NOT NULL UNIQUE' not in schema


def test_live_rejection_reports_error_once_without_blocking_future_saves(tmp_path):
    from foundry.domain import ValidationError
    app,_,_=fixture(tmp_path);path,row=receipt(app,1)
    path.write_text('[]')
    with pytest.raises(ValidationError):commit_render_saves(app,strict=True)
    receipt(app,2)
    assert commit_render_saves(app,strict=True)['registered']==1

def test_new_save_replaces_legacy_copy_only_after_metadata_is_committed(tmp_path):
    app,_,_=fixture(tmp_path)
    old_bytes=io.BytesIO();Image.new('RGBA',(40,56),'green').save(old_bytes,'PNG')
    asset=app.store.add_asset(old_bytes.getvalue(),'image/png',40,56)
    previous=app.store.render_put('b'*64,asset,deck_id='deck',card_id='card',face_id='face-1',deck_name='Deck',face_name='Card')
    legacy=app.store.home/previous['file_path']
    _,row=receipt(app,1)
    commit_render_saves(app)
    assert legacy.exists() and app.store.render_get('1'*64)['asset_id']==row['hash']
    assert not app.store.render_get('b'*64)
    while app.store.cleanup_step()['pending']:pass
    assert not legacy.exists() and not app.store.asset_path(asset['id']).exists()
    assert app.store.render_get('1'*64)
