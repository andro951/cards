import io
from PIL import Image, ImageDraw
from foundry.transform_crown import PREFIX, restore_crown_bevel, mirror_header_png
from foundry.runtime import Runtime
from foundry.network import Network
from foundry.storage import Store


def png(pixels):
    image=Image.new('RGBA',(len(pixels),1));image.putdata(pixels)
    output=io.BytesIO();image.save(output,'PNG');return output.getvalue()


def test_bevel_restores_material_and_preserves_openings_outlines_and_alpha():
    source=[(80,75,70,255),(0,0,0,255),(240,245,250,0),(0,0,0,127),(180,170,160,255)]
    donor=[(180,175,170,255),(240,245,250,255),(240,245,250,255),(240,245,250,255),(240,245,250,0)]
    result=Image.open(io.BytesIO(restore_crown_bevel(png(source),png(donor)))).convert('RGBA')
    assert list(result.get_flattened_data())==[donor[0],*source[1:]]


def test_donor_bar_end_fragments_cannot_overwrite_circle_collar():
    source=Image.new('RGBA',(500,100),(220,215,210,255))
    ImageDraw.Draw(source).ellipse((15,25,55,65),fill=(0,0,0,0))
    donor=Image.new('RGBA',source.size,(140,135,130,255))
    # Rounded donor endcap fragments just above/below the circular opening.
    donor.putpixel((25,24),(30,30,30,255))
    donor.putpixel((25,66),(30,30,30,255))
    raws=[]
    for im in (source,donor):
        buf=io.BytesIO();im.save(buf,'PNG');raws.append(buf.getvalue())
    result=Image.open(io.BytesIO(restore_crown_bevel(*raws))).convert('RGBA')
    for point in ((25,24),(25,66),(35,45)):
        assert result.getpixel(point)==source.getpixel(point)
    assert result.getpixel((100,20))==donor.getpixel((100,20))
    assert result.getchannel('A').tobytes()==source.getchannel('A').tobytes()


def test_beveled_crown_is_persisted_and_needs_no_sources_after_restart(tmp_path):
    calls=[]
    native=png([(80,75,70,255),(0,0,0,127)])
    def transport(url):
        calls.append(url);return native,'image/png',{}
    runtime=Runtime(Network(Store(tmp_path),transport=transport))
    path=PREFIX+'CrownJoinedB.png'
    first,_=runtime.fetch(path)
    assert not runtime.requested[path]['cache'] and len(calls)==2
    def fail(url):raise AssertionError('Processed crown cache must survive restart')
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert restarted.fetch(path)[0]==first
    assert restarted.requested[path]['cache']


def test_artifact_tint_invalidates_when_underlying_bevel_changes(tmp_path,monkeypatch):
    from foundry.artifact_frame import ArtifactFrameCache
    from foundry import transform_crown
    cache=ArtifactFrameCache(Store(tmp_path));calls=[]
    def load(path):
        calls.append(path);return png([(180,175,170,255)]),'image/png'
    path=PREFIX+'CrownJoinedA.png'
    assert not cache.fetch(path,load)[1]
    assert cache.fetch(path,load)[1]
    monkeypatch.setattr(transform_crown,'BEVEL_VERSION','native-crown-bevel-v2')
    assert not cache.fetch(path,load)[1]
    assert calls==[path,path]


def test_right_back_reflects_texture_and_alpha_together():
    pixels=[(180,175,170,255),(0,0,0,0),(40,35,30,127)]
    result=Image.open(io.BytesIO(mirror_header_png(png(pixels)))).convert('RGBA')
    assert list(result.get_flattened_data())==list(reversed(pixels))


def test_right_back_crown_is_persisted_without_refetching(tmp_path):
    calls=[]
    native=png([(80,75,70,255),(0,0,0,127)])
    def transport(url):calls.append(url);return native,'image/png',{}
    runtime=Runtime(Network(Store(tmp_path),transport=transport))
    path=PREFIX+'CrownJoinedBackW.png'
    first,_=runtime.fetch(path)
    assert not runtime.requested[path]['cache'] and len(calls)==2
    def fail(url):raise AssertionError('Mirrored header must reuse its local processed cache')
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert restarted.fetch(path)[0]==first
    assert restarted.requested[path]['cache']


def test_right_floating_crown_keeps_circle_and_reuses_processed_cache(tmp_path):
    calls=[];native=png([(100,90,80,255),(0,0,0,0),(80,70,60,200)])
    def load(url):calls.append(url);return native,'image/png',{}
    runtime=Runtime(Network(Store(tmp_path),transport=load))
    path=PREFIX+'CrownFloatingBackW.png';result=runtime.fetch(path)[0]
    assert result==mirror_header_png(native)
    assert len(calls)==1 and '/crowns/floating/w.png' in calls[0]
    def fail(url):raise AssertionError('Floating back crown must reuse its cache')
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert restarted.fetch(path)[0]==result and restarted.requested[path]['cache']
