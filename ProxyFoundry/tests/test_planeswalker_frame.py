import io
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
from foundry.planeswalker_frame import PREFIX,TALL_EXTRA,SPLICE_Y,MOVE_START,extend_rules_png,extend_rules_svg,renderer_script
from foundry.runtime import Runtime
from foundry.network import Network
from foundry.storage import Store


def source_png():
    image=Image.new('RGBA',(1500,2100));draw=ImageDraw.Draw(image)
    for y in range(2100):draw.line((0,y,1499,y),fill=(y%256,y//256,80,y%255))
    draw.rectangle((12,0,17,2099),fill=(0,0,0,255))
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def test_tall_extension_preserves_pixels_and_repeats_only_the_middle():
    raw=source_png();source=Image.open(io.BytesIO(raw)).convert('RGBA')
    result=Image.open(io.BytesIO(extend_rules_png(raw))).convert('RGBA')
    assert result.size==source.size
    assert result.crop((0,0,1500,MOVE_START-TALL_EXTRA)).tobytes()==source.crop((0,0,1500,MOVE_START-TALL_EXTRA)).tobytes()
    assert result.crop((0,MOVE_START-TALL_EXTRA,1500,SPLICE_Y-TALL_EXTRA)).tobytes()==source.crop((0,MOVE_START,1500,SPLICE_Y)).tobytes()
    assert result.crop((0,SPLICE_Y-TALL_EXTRA,1500,SPLICE_Y)).tobytes()==source.crop((0,SPLICE_Y-1,1500,SPLICE_Y)).tobytes()*TALL_EXTRA
    assert result.crop((0,SPLICE_Y,1500,2100)).tobytes()==source.crop((0,SPLICE_Y,1500,2100)).tobytes()


SVG=b'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="2100"><path d="M198.367,1314.41L1365.63,1314.41L1384.6,1877.73L179.406,1877.73Z" fill="green"/></svg>'

def test_tall_background_mask_keeps_native_path_and_moves_only_upper_section():
    root=ET.fromstring(extend_rules_svg(SVG));ns={'s':'http://www.w3.org/2000/svg'}
    paths=root.findall('.//s:path',ns)
    assert len(paths)==2 and paths[0].attrib==paths[1].attrib
    assert any(g.get('transform')=='translate(0,-147)' for g in root.findall('s:g',ns))
    middle=next(e for e in root.findall('s:rect',ns))
    assert middle.get('y')=='1403' and middle.get('height')=='147'


def test_derived_frame_and_mask_are_cached_across_runtime_restarts(tmp_path):
    calls=[];raw=source_png()
    def transport(url):calls.append(url);return (SVG,'image/svg+xml',{}) if url.endswith('.svg') else (raw,'image/png',{})
    runtime=Runtime(Network(Store(tmp_path),transport=transport))
    paths=[PREFIX+'FrameTallU.png',PREFIX+'MaskPinlineTall.png',PREFIX+'textTall.svg']
    results=[runtime.fetch(p) for p in paths]
    assert len(calls)==3
    def fail(url):raise AssertionError('Tall frame must use its saved local copy')
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert [restarted.fetch(p) for p in paths]==results
    assert all(restarted.requested[p]['cache'] for p in paths)


def test_renderer_uses_matching_mask_without_changing_normal_tall_cards():
    raw=b"if (card.version.includes('Tall') || card.version.includes('Compleated')) { oldTall(); }"
    result=renderer_script(raw).decode()
    assert 'planeswalkerNicknameTall' in result and '/proxy-foundry/planeswalker/textTall.svg' in result
    assert raw.decode() in result
