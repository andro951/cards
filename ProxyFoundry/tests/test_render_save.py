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