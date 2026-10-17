import io
import xml.etree.ElementTree as ET
import pytest
from PIL import Image,ImageDraw
from foundry.planeswalker_frame import PREFIX,TALL_EXTRA,SPLICE_Y,MOVE_START,fit_ability_rows,layout_planeswalker_abilities,pinline_without_loyalty_png,nickname_pinline_png,extend_rules_png,extend_rules_svg,renderer_script
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
    assert len(calls)==5
    def fail(url):raise AssertionError('Tall frame must use its saved local copy')
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert [restarted.fetch(p) for p in paths]==results
    assert all(restarted.requested[p]['cache'] for p in paths)


def test_nickname_pinline_mask_excludes_missing_rails_and_entire_loyalty_badge():
    frame=Image.new('RGBA',(1500,2100));pinline=Image.new('RGBA',frame.size);badge=Image.new('RGBA',frame.size)
    ImageDraw.Draw(frame).rectangle((60,1200,1400,1250),fill=(250,220,100,255))
    ImageDraw.Draw(frame).rectangle((1200,1850,1400,1980),fill='black')
    draw=ImageDraw.Draw(pinline)
    draw.rectangle((60,200,80,1250),fill='white')
    draw.rectangle((60,1200,1400,1250),fill='white')
    draw.rectangle((1200,1850,1400,1980),fill='white')
    ImageDraw.Draw(badge).rectangle((1200,1850,1400,1980),fill=(255,255,255,128))
    def png(image):
        out=io.BytesIO();image.save(out,'PNG');return out.getvalue()
    badge=badge.resize((2010,2814),Image.Resampling.NEAREST)
    alpha=Image.open(io.BytesIO(nickname_pinline_png(*map(png,(frame,pinline,badge))))).getchannel('A')
    assert alpha.getpixel((70,700))==0
    assert alpha.getpixel((700,1220))==255
    assert alpha.crop((1200,1850,1401,1981)).getbbox() is None


def test_renderer_uses_matching_mask_without_changing_normal_tall_cards():
    raw=b"if (card.version.includes('Tall') || card.version.includes('Compleated')) { oldTall(); }"
    result=renderer_script(raw).decode()
    assert 'planeswalkerNicknameTall' in result and '/proxy-foundry/planeswalker/textTall.svg' in result
    assert raw.decode() in result


def test_regular_pinline_keeps_rails_but_excludes_the_loyalty_badge():
    pinline=Image.new('RGBA',(1500,2100));badge=Image.new('RGBA',pinline.size)
    draw=ImageDraw.Draw(pinline)
    draw.rectangle((60,200,80,1250),fill='white')
    draw.rectangle((60,1900,1400,1920),fill='white')
    ImageDraw.Draw(badge).rectangle((1200,1850,1400,1980),fill=(255,255,255,128))
    def png(image):
        out=io.BytesIO();image.save(out,'PNG');return out.getvalue()
    output=Image.open(io.BytesIO(pinline_without_loyalty_png(png(pinline),png(badge)))).getchannel('A')
    assert output.getpixel((70,700))==255
    assert output.getpixel((700,1910))==255
    assert output.crop((1200,1850,1401,1981)).getbbox() is None


@pytest.mark.parametrize('count',[1,2,3,4])
@pytest.mark.parametrize('passive',[False,True])
def test_shared_fitter_uses_supplied_bounds_and_reserves_badge_margin(count,passive):
    abilities=[('+1','Draw a card.')]*count
    if passive:abilities[0]=('','Whenever you draw a card, you gain 1 life.')
    bounds={'x':.15,'y':.5,'width':.7,'height':.39}
    rows=fit_ability_rows(abilities,bounds)
    assert len(rows)==count and len({r['size'] for r in rows})==1
    assert rows[0]['y']==bounds['y']
    assert rows[-1]['y']+rows[-1]['height']==pytest.approx(bounds['y']+bounds['height'])
    for index,row in enumerate(rows):
        assert row['x']==pytest.approx(bounds['x']+(.044 if abilities[index][0] else 0))
        assert row['x']+row['width']==pytest.approx(bounds['x']+bounds['width'])
        if index:assert row['y']==pytest.approx(rows[index-1]['y']+rows[index-1]['height'])
    moved=fit_ability_rows(abilities,{**bounds,'x':.2,'y':.4})
    assert [r['height'] for r in moved]==[r['height'] for r in rows]
    assert all(b['y']==pytest.approx(a['y']-.1) for a,b in zip(rows,moved))


@pytest.mark.parametrize('count',[1,2,3,4])
def test_frames_share_geometry_and_badge_centers_at_equal_bounds(count):
    oracle='\n'.join(['+1: Draw a card.','-2: Destroy target creature.','0: You gain 3 life.','-7: Draw seven cards.'][:count])
    versions=['planeswalkerRegular','planeswalkerNickname','planeswalkerTall','planeswalkerNicknameTall']
    cards=[]
    for version in versions:
        data={'version':version,'text':{'type':{'y':.5625,'height':.0548}}}
        layout_planeswalker_abilities(data,{'oracle_text':oracle})
        cards.append(data)
    assert all(d['text']==cards[0]['text'] for d in cards)
    # Different native anchor tables must still draw the badges at the same
    # calculated centers. Check the one-row anchor in each family as well.
    normal={1:[.7467],2:[.6953,.822],3:[.6639,.7467,.8362],4:[.6505,.72,.7905,.861]}[count]
    tall={1:[.72],2:[.6391,.801],3:[.5986,.72,.8415],4:[.5986,.6796,.7605,.8415]}[count]
    for data in cards:
        bases=tall if data['version']=='planeswalkerTall' else normal
        for index in range(count):
            row=data['text'][f'ability{index}']
            assert bases[index]+data['planeswalker']['abilityAdjust'][index]+.0085==pytest.approx(row['y']+row['height']/2)
        assert all(data['text'][f'ability{i}']['height']==0 for i in range(count,4))
