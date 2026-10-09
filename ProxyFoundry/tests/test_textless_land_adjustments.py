import io
import pytest
from PIL import Image,ImageChops
from foundry.compiler import Compiler
from foundry.images import ingest_image
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.runtime import Runtime
from foundry.land_frame import ADDON_PREFIX,BASIC_NICKNAME_RAISE,apply_textless_land_adjustments
from scripts.build_land_addon_assets import remove_bottom_outer_outline

@pytest.mark.parametrize('name,type_line,recipe',[
    ('Plains','Basic Land — Plains','land_full_basic'),
    ('Tundra','Land — Plains Island','original_dual_land_textless'),
])
@pytest.mark.parametrize('nickname',[False,True])
def test_native_families_keep_their_frame_and_use_scoped_corrections(tmp_path,name,type_line,recipe,nickname):
    store=Store(tmp_path);ws=Workspace(store)
    output=io.BytesIO();Image.new('RGB',(100,140),'#456789').save(output,'PNG')
    art=ingest_image(store,output.getvalue())['id']
    sf={'name':name,'type_line':type_line,'colors':[],'mana_cost':'','oracle_text':'','rarity':'common','artist':'Artist','layout':'normal'}
    if nickname:sf['flavor_name']='Alternate Name'
    result=Compiler(store).compile_face(sf,sf,0,{},ws.validate_settings({}),art)
    data=result['data']
    assert result['recipe']==recipe
    assert not any('crown' in f['name'].lower() for f in data['frames'])
    if name=='Tundra':
        assert any(m['src']==ADDON_PREFIX+'original-dual-type.svg' for f in data['frames'] for m in f['masks'])
        if nickname:
            bars=[f for f in data['frames'] if 'TrueNameNoOuter' in f['src']]
            assert [f['src'][-5] for f in bars]==['U','W']
            assert bars[0]['masks'] and bars[1]['masks']==[]
    elif nickname:
        assert data['frames'][0]['src']==ADDON_PREFIX+'BasicTrueNameW.png'
        assert data['frames'][0]['bounds']=={'x':0,'y':-BASIC_NICKNAME_RAISE,'width':1,'height':1}
        assert len([f for f in data['frames'] if f['src']=='/img/frames/textless/eoe/w.png'])==3
        for frame in data['frames']:
            if any(m['src'].endswith(('/maskNoBorder.png','/maskPinlines.png')) for m in frame.get('masks',[])):
                assert frame['ogBounds']['y']==0
                assert frame['bounds']['y']-frame['ogBounds']['y']==pytest.approx(-BASIC_NICKNAME_RAISE)
        assert not any('/nickname/addons/' in f['src'] for f in data['frames'])
        assert data['text']['title']['y']==pytest.approx(data['text']['nickname']['y']+.0543+.0064+1/2100)

def test_basic_nickname_group_is_raised_24_pixels_with_border_fixed():
    data={'frames':[{'src':'/img/frames/m15/nickname/addons/m15NicknameTitleW.png','bounds':{'y':.8}},
                    {'src':'/img/frames/textless/eoe/symbols/plains.png'},
                    {'src':'/img/frames/textless/eoe/w.png','bounds':{'x':0,'y':0,'width':1,'height':1}},
                    {'src':'/img/frames/textless/eoe/w.png','masks':[{'src':'/img/frames/textless/eoe/masks/maskBorder.png'}]}],
          'text':{'title':{'y':.87},'nickname':{'y':.82}},
          'setSymbolY':.86,'setSymbolBounds':{'y':.87}}
    import copy
    original=copy.deepcopy(data)
    apply_textless_land_adjustments(data,'land_full_basic',True)
    assert data['frames'][0]['src']==ADDON_PREFIX+'BasicTrueNameW.png'
    assert data['frames'][1]['src']=='/img/frames/textless/eoe/symbols/plains.png'
    for frame in data['frames'][:3]:assert frame['bounds']['y']*2814==pytest.approx(-24)
    assert data['frames'][3]==original['frames'][3]
    assert data['text']['title']['y']==pytest.approx(.87+1/2100-BASIC_NICKNAME_RAISE)
    assert data['text']['nickname']['y']==pytest.approx(.82-BASIC_NICKNAME_RAISE)
    assert data['setSymbolY']==pytest.approx(.86-BASIC_NICKNAME_RAISE)
    assert data['setSymbolBounds']['y']==pytest.approx(.87-BASIC_NICKNAME_RAISE)
    # The same basic layout without a nickname is not moved.
    normal=copy.deepcopy(original)
    apply_textless_land_adjustments(normal,'land_full_basic',False)
    assert normal==original

@pytest.mark.parametrize('code',list('WUBRG'))
def test_basic_addon_is_bundled_at_native_size(code):
    class NoNetwork:
        def fetch(self,*args,**kwargs):raise AssertionError('Join asset fetched remotely')
    raw,mime=Runtime(NoNetwork()).fetch(ADDON_PREFIX+'BasicTrueName'+code+'.png')
    image=Image.open(io.BytesIO(raw)).convert('RGBA')
    assert mime=='image/png' and image.size==(2010,2814)
    assert image.getchannel('A').getbbox()[1]>=2554

def test_basic_join_preserves_title_and_allows_only_one_seam_row():
    from scripts.build_basic_land_join_assets import join,match_addon_alpha,W,H,BAR_X,BAR_WIDTH,BAR_HEIGHT,BAR_Y,CROP
    source=Image.new('RGBA',(W,H))
    source.paste((0,0,0,255),(300,2553,1780,2560))
    source.paste((110,130,150,191),(300,2530,1780,2553))
    source.paste((11,11,11,191),(300,2440,1780,2460))
    addon=Image.new('RGBA',(1352,221))
    addon.paste((0,0,0,255),(51,148,1301,152))
    addon.paste((0,0,0,127),(51,152,1301,204))
    mask=Image.new('L',(W,H),255)
    title,bar,footprint=join(source,[(mask,.5),(mask,.6)],addon)
    # Title composition is intact, including pixels underneath the addon.
    expected=Image.new('RGBA',(W,H))
    for opacity in [.6,.5]:
        layer=source.copy();layer.putalpha(source.getchannel('A').point(lambda a:round(a*opacity)))
        expected=Image.alpha_composite(expected,layer)
    assert ImageChops.difference(title,expected).getbbox() is None
    overlap=ImageChops.multiply(title.getchannel('A'),bar.getchannel('A')).crop((0,0,W,2562))
    assert overlap.getbbox()==(314,2559,1743,2560)
    # Only alpha matching is applied; no horizontal blend changes colors.
    sx=BAR_WIDTH*W/addon.width;sy=BAR_HEIGHT*H/addon.height
    cropped=match_addon_alpha(addon,title).crop((0,CROP,addon.width,addon.height))
    untouched=cropped.transform((W,H),Image.Transform.AFFINE,
        (1/sx,0,-BAR_X*W/sx,0,1/sy,-(BAR_Y*H+CROP*sy)/sy),Image.Resampling.BICUBIC)
    survival=bar.getchannel('A').point(lambda a:255 if a else 0)
    for a,b in zip(bar.split(),untouched.split()):
        assert not ImageChops.multiply(ImageChops.difference(a,b),survival).getbbox()
    assert bar.getpixel((400,2580))[3]==title.getpixel((W//2,2450))[3]

def test_basic_addon_matches_title_fill_and_rim_alpha_without_moving():
    from scripts.build_basic_land_join_assets import match_addon_alpha,W,H
    title=Image.new('RGBA',(W,H));title.putpixel((W//2,2557),(0,0,0,204))
    title.putpixel((W//2,2450),(11,11,11,96))
    addon=Image.new('RGBA',(3,1));addon.putdata([(0,0,0,127),(252,255,255,255),(0,0,0,255)])
    matched=match_addon_alpha(addon,title)
    assert list(matched.getdata())==[(0,0,0,96),(252,255,255,204),(0,0,0,204)]

def test_outline_removal_preserves_colored_strip_inner_line_and_translucent_fill():
    source=Image.new('RGBA',(1352,221))
    for y,color in [(133,(0,0,0,255)),(203,(0,0,0,255)),(202,(0,0,0,127))]:
        source.paste(color,(50,y,1302,y+1))
    source.paste((0,117,191,255),(50,207,1302,217))
    source.paste((0,0,0,255),(50,217,1302,221))
    result=remove_bottom_outer_outline(source)
    assert result.getpixel((676,219))[3]==0
    assert result.getpixel((676,203))==source.getpixel((676,203))
    assert result.getpixel((676,202))==source.getpixel((676,202))
    assert result.getpixel((676,133))==source.getpixel((676,133))
    assert not ImageChops.difference(source.crop((50,207,1302,217)),result.crop((50,207,1302,217))).getbbox()

def test_type_mask_fills_native_half_unit_inset_without_changing_shape():
    import xml.etree.ElementTree as ET
    raw=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 252"><path d="M10 213.36h160v13.68H10z"/></svg>'
    class Network:
        def fetch(self,url,**kwargs):
            assert url.endswith('/img/frames/textless/basics/type.svg')
            return raw,'image/svg+xml',{}
    output,mime=Runtime(Network()).fetch(ADDON_PREFIX+'original-dual-type.svg')
    path=next(node for node in ET.fromstring(output).iter() if node.tag.endswith('}path'))
    assert path.get('d')=='M10 213.36h160v13.68H10z'
    assert float(path.get('stroke-width'))/2>.48
    assert mime=='image/svg+xml'
