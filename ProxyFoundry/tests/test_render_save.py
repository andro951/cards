"""Native PNG persistence preserves bytes and rejects damaged/wrong canvases."""
import io
import pytest
from PIL import Image,PngImagePlugin
from foundry.domain import ValidationError
from foundry.storage import Store
from foundry.workspace import Workspace


def png():
    raw=io.BytesIO();info=PngImagePlugin.PngInfo();info.add_text('fixture','native-byte-preservation')
    Image.new('RGBA',(40,56),(30,90,180,120)).save(raw,'PNG',pnginfo=info,compress_level=1)
    return raw.getvalue()


def test_render_save_keeps_exact_native_png_and_registers_valid_render(tmp_path):
    store=Store(tmp_path);workspace=Workspace(store);raw=png()
    result=workspace.save_render({'key':'a'*64,'name':'Example'},raw,[40,56])
    assert store.asset_path(result['asset_id']).read_bytes()==raw
    assert (store.home/result['file_path']).read_bytes()==raw
    assert workspace.store.render_get('a'*64)['asset_id']==result['asset_id']


@pytest.mark.parametrize('kind',['size','truncated','crc','jpeg'])
def test_invalid_render_creates_no_asset_or_render(tmp_path,kind):
    store=Store(tmp_path);workspace=Workspace(store);raw=png();size=[40,56]
    if kind=='size':size=[41,56]
    elif kind=='truncated':raw=raw[:len(raw)//2]
    elif kind=='crc':
        raw=bytearray(raw);raw[raw.index(b'IDAT')+5]^=1;raw=bytes(raw)
    else:
        out=io.BytesIO();Image.new('RGB',(40,56)).save(out,'JPEG');raw=out.getvalue()
    message='canvas size' if kind=='size' else 'PNG'
    with pytest.raises(ValidationError,match=message):workspace.save_render({'key':'a'*64},raw,size)
    assert store.stats()['assets']==0 and store.stats()['renders']==0



def test_browser_checkpoint_skips_unchanged_database_and_retries_failed_persistence(tmp_path):
    import sqlite3
    from foundry.browser import BrowserStore
    snapshots=[]
    store=BrowserStore(tmp_path,lambda path:snapshots.append(open(path,'rb').read()))
    store.checkpoint();count=len(snapshots)
    store.checkpoint();assert len(snapshots)==count
    store.put('settings',{'id':'test','value':'changed'})
    assert len(snapshots)==count+1
    store.checkpoint();assert len(snapshots)==count+1
    #Direct SQLite mutations, as used by restore/migrations, also invalidate the digest.
    with sqlite3.connect(store.db_path) as db:db.execute("UPDATE documents SET rev=rev+1 WHERE id='test'")
    original=store.persist
    def fail(path):raise OSError('checkpoint failed')
    store.persist=fail
    with pytest.raises(OSError,match='checkpoint failed'):store.checkpoint()
    store.persist=original;store.checkpoint()
    assert len(snapshots)==count+2


@pytest.mark.parametrize('failure',[None,'copy','checkpoint','checkpoint-all','interrupt'])
def test_browser_render_save_has_one_checkpoint_and_recovers_previous_state(tmp_path,failure):
    import shutil,sqlite3
    from pathlib import Path
    from foundry.browser import BrowserStore
    snapshots=[];fail_copy=False;fail_checkpoint=False
    def atomic_copy(source,destination):
        if fail_copy:raise OSError('copy aborted')
        temporary=Path(str(destination)+'.test-copy')
        shutil.copy2(source,temporary);temporary.replace(destination)
    def persist(path):
        nonlocal fail_checkpoint
        if fail_checkpoint:
            fail_checkpoint=failure=='checkpoint-all'
            raise OSError('checkpoint failed')
        snapshots.append(Path(path).read_bytes())
    store=BrowserStore(tmp_path,persist,atomic_copy);workspace=Workspace(store)
    deck=store.put('decks',{'name':'Deck','cards':[]})
    target={'key':'a'*64,'name':'Card','deckId':deck['id'],'faceId':'face'}
    raw=png();previous=workspace.save_render(target,raw,[40,56])
    output=store.home/previous['file_path'];old_snapshots=len(snapshots)
    modified=io.BytesIO();Image.new('RGBA',(40,56),'red').save(modified,'PNG')
    target={**target,'key':'b'*64}
    fail_copy=failure=='copy';fail_checkpoint=failure in ('checkpoint','checkpoint-all')
    if failure=='interrupt':
        with pytest.raises(KeyboardInterrupt):
            with store.render_save():
                asset=store.add_asset(modified.getvalue(),'image/png',40,56)
                store.render_put(target['key'],asset,deck_id=deck['id'],face_id='face',face_name='Card')
                raise KeyboardInterrupt()
    elif failure:
        with pytest.raises(OSError):workspace.save_render(target,modified.getvalue(),[40,56])
    else:
        result=workspace.save_render(target,modified.getvalue(),[40,56])
        assert len(snapshots)==old_snapshots+1
        assert (store.home/result['file_path']).read_bytes()==modified.getvalue()
        assert not output.exists()
        assert store.render_get('a'*64) is None
        assert store.asset(previous['asset_id']) is None
        assert not store.asset_path(previous['asset_id']).exists()
        assert store.render_get('b'*64)['asset_id']==result['asset_id']
    if failure:
        import hashlib
        assert output.read_bytes()==raw
        assert store.render_get('a'*64)['asset_id']==previous['asset_id']
        assert store.render_get('b'*64) is None
        assert store.asset_path(previous['asset_id']).read_bytes()==raw
        assert not store.asset_path(hashlib.sha256(modified.getvalue()).hexdigest()).exists()
        restored=tmp_path/'persisted.sqlite3';restored.write_bytes(snapshots[-1])
        with sqlite3.connect(restored) as db:
            assert db.execute('select render_key from renders').fetchall()==[('a'*64,)]
        fail_copy=False;fail_checkpoint=False
        result=workspace.save_render(target,modified.getvalue(),[40,56])
        assert store.render_get('b'*64)['asset_id']==result['asset_id']
    assert not (tmp_path/'.render-save.sqlite3').exists()
    assert not store._render_batch and not store._render_cleanup and not store._render_rollback
