"""Durable deletion, saved-order ownership and interrupted cleanup regressions."""
from pathlib import Path
import pytest
from foundry.storage import Store
from foundry.storage import ValidationError, ConflictError


def test_orders_block_logical_delete_by_id_and_race(tmp_path):
    store=Store(tmp_path)
    deck=store.put('decks',{'name':'Renamed deck'})
    assert store.blocking_orders(deck['id'])==[]
    unrelated=store.put('orders',{'decks':[{'id':'other','name':'Renamed deck'}]})
    first=store.put('orders',{'decks':[{'id':deck['id'],'name':'Old name'}]})
    second=store.put('orders',{'decks':[{'id':deck['id']}]})
    assert {o['id'] for o in store.blocking_orders(deck['id'])}=={first['id'],second['id']}
    with pytest.raises(ValidationError,match='A print order uses this deck'):
        store.begin_delete('decks',deck['id'],deck['revision'])
    assert store.get('decks',deck['id']) and not store.list('cleanup')
    store.begin_delete('orders',first['id'])
    store.begin_delete('orders',second['id'])
    store.begin_delete('decks',deck['id'],deck['revision'])
    assert store.get('decks',deck['id']) is None
    assert store.get('orders',unrelated['id'])


def test_delete_is_metadata_only_and_cleanup_resumes(tmp_path,monkeypatch):
    store=Store(tmp_path)
    deck=store.put('decks',{'name':'Deck'})
    asset=store.add_asset(b'fake png','image/png',10,10)
    render=store.render_put('a'*64,asset,deck_id=deck['id'],face_id='face')
    original=Path.unlink
    def fail(*args,**kwargs):raise OSError('disk unavailable')
    monkeypatch.setattr(Path,'unlink',fail)
    store.begin_delete('decks',deck['id'],deck['revision'])
    assert store.render_get('a'*64) is None
    result=store.cleanup_step()
    assert result['errors']==['disk unavailable']
    assert (tmp_path/render['file_path']).exists()
    monkeypatch.setattr(Path,'unlink',original)
    store=Store(tmp_path)
    queue=store.list('cleanup')[0];queue.pop('error');store.put('cleanup',queue,queue['revision'])
    assert store.cleanup_step()['pending']==0
    assert not (tmp_path/render['file_path']).exists()
    assert store.asset(asset['id']) is None
    #Lost response/reload must never remove a different deck or fail repeatedly.
    assert store.begin_delete('decks',deck['id'],deck['revision'])['permanent']


def test_cleanup_preserves_shared_order_and_art_assets(tmp_path):
    store=Store(tmp_path)
    asset=store.add_asset(b'card image','image/png',10,10)
    deck=store.put('decks',{'name':'Source','artAsset':asset['id']})
    order=store.put('orders',{'decks':[{'id':'other'}],'cards':[{'frontAsset':asset['id']}]})
    store.begin_delete('orders',order['id'])
    store.cleanup_step()
    assert store.asset(asset['id'])
    store.begin_delete('decks',deck['id'])
    assert store.asset(asset['id'])  #Original artwork is retained.


def test_order_zip_cleanup_revision_and_batched_reload(tmp_path):
    store=Store(tmp_path)
    order=store.put('orders',{'decks':[],'cards':[]})
    archive=tmp_path/'orders'/(order['id']+'.zip');archive.write_bytes(b'zip')
    with pytest.raises(ConflictError):store.begin_delete('orders',order['id'],999)
    assert archive.exists() and store.get('orders',order['id'])
    store.begin_delete('orders',order['id'],order['revision'])
    assert archive.exists() and not store.get('orders',order['id'])
    assert Store(tmp_path).cleanup_step(limit=1)['pending']==0
    assert not archive.exists()


def test_cleanup_yields_after_bounded_batch_and_reloads(tmp_path):
    store=Store(tmp_path)
    paths=[tmp_path/'orders'/(str(index)+'.zip') for index in range(12)]
    for path in paths:path.write_bytes(b'zip')
    store.put('cleanup',{'tasks':[{'file':path.relative_to(tmp_path).as_posix()} for path in paths]})
    assert store.cleanup_step(limit=4)['pending']==1
    assert sum(path.exists() for path in paths)==8
    store=Store(tmp_path)
    assert store.cleanup_step(limit=4)['pending']==1
    assert sum(path.exists() for path in paths)==4
    assert store.cleanup_step(limit=4)['pending']==0


def test_deleted_deck_rejects_late_render_upload(tmp_path):
    from foundry.workspace import Workspace
    workspace=Workspace(Store(tmp_path))
    deck=workspace.store.put('decks',{'name':'Deck'})
    workspace.store.begin_delete('decks',deck['id'])
    with pytest.raises(ValidationError,match='deck was deleted'):
        workspace.save_render({'deckId':deck['id'],'key':'a'*64},b'inflight image',[10,10])