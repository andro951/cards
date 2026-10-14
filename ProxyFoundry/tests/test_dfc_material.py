import io
from PIL import Image
from foundry.dfc_material import color_title_png,PREFIX
from foundry.runtime import Runtime
from foundry.network import Network
from foundry.storage import Store


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def test_colored_title_retains_native_bevel_outline_holes_and_true_name():
    header=Image.new('RGBA',(8,270),(0,0,0,0))
    header.putpixel((0,70),(0,0,0,128))
    header.putpixel((1,70),(80,80,80,179))
    header.putpixel((2,70),(0,0,0,255))
    header.putpixel((3,70),(200,40,20,128))
    header.putpixel((0,230),(0,0,0,127))
    header.putpixel((0,71),(0,0,0,179))
    material=Image.new('RGBA',(1500,2100),(180,60,30,255))
    result=Image.open(io.BytesIO(color_title_png(png(header),png(material),joined_crown=True))).convert('RGBA')
    assert result.getpixel((0,70))==(180,60,30,255)
    highlight=result.getpixel((1,70));shade=result.getpixel((0,71))
    assert highlight[3]==shade[3]==255
    assert highlight[0]>180 and highlight[1]>60 and highlight[2]>30
    assert shade[0]<180 and shade[1]<60 and shade[2]<30
    for point in ((2,70),(3,70),(4,70),(0,230)):
        assert result.getpixel(point)==header.getpixel(point)


def test_colored_title_and_joined_crown_reuse_cache_after_restart(tmp_path):
    calls=[]
    header=png(Image.new('RGBA',(100,221),(0,0,0,128)))
    material=png(Image.new('RGBA',(1500,2100),(180,60,30,255)))
    def load(url):
        calls.append(url);return (material if '/regular/back' in url else header),'image/png',{}
    runtime=Runtime(Network(Store(tmp_path),transport=load))
    for kind in ('TitleColored','CrownJoinedColored'):
        path=PREFIX+kind+'R.png';first=runtime.fetch(path)[0]
        assert not runtime.requested[path]['cache']
        def fail(url):raise AssertionError('Processed title should be cached locally')
        restarted=Runtime(Network(Store(tmp_path),transport=fail))
        assert restarted.fetch(path)[0]==first and restarted.requested[path]['cache']
    assert len(calls)==3
