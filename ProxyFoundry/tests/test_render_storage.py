import io,hashlib
from pathlib import Path
from PIL import Image
import pytest

from foundry.domain import SCHEMA_VERSION
from foundry.images import ingest_image
from foundry.storage import Store


def png(color):
    out=io.BytesIO();Image.new('RGB',(100,140),color).save(out,'PNG');return out.getvalue()


@pytest.mark.parametrize('record_exists',[False,True])
def test_asset_retry_repairs_an_incomplete_file(tmp_path,record_exists):
    store=Store(tmp_path);raw=png('#123456');ident=hashlib.sha256(raw).hexdigest()
    if record_exists:store.add_asset(raw,'image/png',100,140)
    target=store.asset_path(ident);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(raw[:32])
    recovered=store.add_asset(raw,'image/png',100,140)
    assert recovered['id']==ident and recovered['size']==len(raw)
    assert [recovered['width'],recovered['height']]==[100,140]
    assert target.read_bytes()==raw


def test_one_current_render_per_face_and_human_readable_path(tmp_path):
    store=Store(tmp_path)
    first=ingest_image(store,png('#112233'))
    r1=store.render_put('1'*64,first,deck_id='deck-1',card_id='card-1',face_id='face-1',deck_name='My Deck',face_name='Clara Oswald')
    p1=store.home/r1['file_path']
    assert p1.parent.name=='My Deck' and p1.name=='Clara Oswald.png' and p1.is_file()

    second=ingest_image(store,png('#445566'))
    r2=store.render_put('2'*64,second,deck_id='deck-1',card_id='card-1',face_id='face-1',deck_name='My Deck',face_name='Clara Oswald')
    assert store.render_get('1'*64) is None
    assert store.render_get('2'*64)['asset_id']==second['id']
    assert (store.home/r2['file_path'])==p1
    assert not store.asset(first['id'])


def test_delete_all_images_keeps_nonrender_assets(tmp_path):
    store=Store(tmp_path)
    art=ingest_image(store,png('#abcdef'))
    render=ingest_image(store,png('#123456'))
    store.render_put('a'*64,render,deck_id='deck',card_id='card',face_id='face',deck_name='Deck',face_name='Card')
    out=store.clear_renders()
    assert out['deleted']==1
    assert store.stats()['renders']==0
    assert store.asset(art['id'])
    assert not store.asset(render['id'])
    assert not any((store.home/'renders').rglob('*.png'))


def test_render_storage_is_fresh_schema_without_migration_code():
    assert SCHEMA_VERSION==2
    source=(Path(__file__).resolve().parents[1]/'foundry/storage.py').read_text(encoding='utf-8')
    assert 'ALTER TABLE' not in source
    settings=(Path(__file__).resolve().parents[1]/'site/settings.js').read_text(encoding='utf-8')
    assert 'Delete All Images' in settings and '/api/images/delete-all' in settings


def test_browser_copy_failure_preserves_previous_render_and_metadata(tmp_path):
    import shutil
    from foundry.browser import BrowserStore
    store=BrowserStore(tmp_path,copy_file=shutil.copy2)
    first=ingest_image(store,png('#112233'))
    previous=store.render_put('1'*64,first,face_id='face',face_name='Card')
    output=store.home/previous['file_path'];saved=output.read_bytes()
    second=ingest_image(store,png('#445566'))
    def interrupted(source,destination):
        Path(destination).write_bytes(Path(source).read_bytes()[:32])
        raise OSError('Interrupted browser copy')
    store.copy_file=interrupted
    with pytest.raises(OSError,match='Interrupted browser copy'):
        store.render_put('2'*64,second,face_id='face',face_name='Card')
    assert output.read_bytes()==saved
    assert store.render_get('1'*64)['asset_id']==first['id']
    assert store.render_get('2'*64) is None
    assert not list((store.home/'renders').rglob('*.tmp'))
