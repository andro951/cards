import io

from PIL import Image

from foundry.images import trim_transparent_edges
from foundry.images import ingest_image
from foundry.storage import Store


def image_bytes(color='red'):
    image=Image.new('RGBA',(12,16),(0,0,0,0));image.paste(color,(3,4,9,12))
    output=io.BytesIO();image.save(output,'PNG');return output.getvalue()


def test_repeated_art_ingest_reuses_normalized_bytes_and_separates_trim(tmp_path,monkeypatch):
    import foundry.images as images
    store=Store(tmp_path);raw=image_bytes();original=images.decode_image;calls=[]
    def decode(raw):calls.append(raw);return original(raw)
    monkeypatch.setattr(images,'decode_image',decode)
    first=ingest_image(store,raw);saved=store.asset_path(first['id']).read_bytes()
    first['width']=999
    repeated=ingest_image(store,raw)
    assert repeated['width']==12 and repeated['height']==16
    assert store.asset_path(repeated['id']).read_bytes()==saved and len(calls)==1
    trimmed=ingest_image(store,raw,trim_transparent_padding=True)
    assert (trimmed['width'],trimmed['height'])==(6,8) and trimmed['id']!=repeated['id']
    assert len(calls)==2
    changed=ingest_image(store,image_bytes('blue'))
    assert changed['id']!=repeated['id'] and len(calls)==3


def test_art_ingest_restores_deleted_asset_and_does_not_cache_invalid_bytes(tmp_path):
    import pytest
    from foundry.domain import ValidationError
    store=Store(tmp_path);raw=image_bytes();first=ingest_image(store,raw)
    store.asset_path(first['id']).unlink()
    restored=ingest_image(store,raw)
    assert restored['id']==first['id'] and store.asset_path(restored['id']).is_file()
    size=len(store._image_ingest_cache)
    with pytest.raises(ValidationError):ingest_image(store,b'not an image')
    assert len(store._image_ingest_cache)==size


def test_art_ingest_cache_bounds_metadata_and_keeps_recent_inputs(tmp_path,monkeypatch):
    import foundry.images as images
    store=Store(tmp_path);original=images.decode_image;calls=[]
    def decode(raw):calls.append(raw);return original(raw)
    monkeypatch.setattr(images,'decode_image',decode)
    rows=[image_bytes((index,0,0,255)) for index in range(129)]
    for raw in rows[:128]:ingest_image(store,raw)
    ingest_image(store,rows[0]);ingest_image(store,rows[128])
    assert len(store._image_ingest_cache)==128
    assert all(isinstance(value,str) and len(value)==64 for value in store._image_ingest_cache.values())
    before=len(calls);ingest_image(store,rows[0]);assert len(calls)==before
    ingest_image(store,rows[1]);assert len(calls)==before+1


def test_transparent_edge_crop_ignores_alpha_two_strays():
    im=Image.new('RGBA',(12,10),(0,0,0,0))
    # Nearly invisible junk in the outer padding must not hold the crop open.
    im.putpixel((0,0),(255,0,0,1))
    im.putpixel((11,9),(0,255,0,2))
    # Real retained content.
    for y in range(3,8):
        for x in range(4,9):
            im.putpixel((x,y),(10,20,30,255))

    cropped=trim_transparent_edges(im)

    assert cropped.size==(5,5)
    assert cropped.getpixel((0,0))==(10,20,30,255)
    assert cropped.getpixel((4,4))==(10,20,30,255)


def test_transparent_edge_crop_keeps_alpha_three_boundary():
    im=Image.new('RGBA',(8,8),(0,0,0,0))
    im.putpixel((1,2),(20,30,40,3))
    im.putpixel((6,5),(50,60,70,255))

    cropped=trim_transparent_edges(im)

    assert cropped.size==(6,4)
    assert cropped.getpixel((0,0))==(20,30,40,3)
    assert cropped.getpixel((5,3))==(50,60,70,255)


def test_transparent_edge_crop_does_not_erase_low_alpha_inside_crop():
    im=Image.new('RGBA',(7,7),(0,0,0,0))
    im.putpixel((2,2),(100,110,120,255))
    im.putpixel((4,4),(130,140,150,255))
    im.putpixel((3,3),(200,210,220,2))

    cropped=trim_transparent_edges(im)

    assert cropped.size==(3,3)
    # The alpha threshold is only for finding the outer bounds; interior pixels
    # are preserved byte-for-byte.
    assert cropped.getpixel((1,1))==(200,210,220,2)
