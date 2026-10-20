import io,json
from pathlib import Path
import pytest
from PIL import Image,ImageChops
from foundry.compiler import Compiler,BUILTINS
from foundry.land_frame import ASSET_ROOT,GEOMETRY,PREFIX
from foundry.images import ingest_image
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.runtime import Runtime

@pytest.fixture
def compiler_setup(tmp_path):
    store=Store(tmp_path);ws=Workspace(store)
    output=io.BytesIO();Image.new('RGB',(100,140),'#456789').save(output,'PNG')
    art=ingest_image(store,output.getvalue())['id']
    return Compiler(store),ws,art


@pytest.mark.parametrize('legendary',[False,True])
@pytest.mark.parametrize('nickname',['','Steam Passage'])
def test_classic_scalding_tarn_has_neutral_bars_and_dual_pinline(compiler_setup,legendary,nickname):
    compiler,ws,art=compiler_setup
    sf={'name':'Scalding Tarn','type_line':('Legendary ' if legendary else '')+'Land',
        'colors':[],'mana_cost':'','rarity':'rare','artist':'Artist','layout':'normal',
        'oracle_text':'{T}, Pay 1 life, Sacrifice Scalding Tarn: Search your library for an Island or Mountain card, put it onto the battlefield, then shuffle.'}
    result=compiler.compile_face(sf,sf,0,{'templateOverride':'normal',
        'semanticOverrides':{'nickname':nickname}},ws.validate_settings({}),art)
    frames=result['data']['frames']
    for name in ('Title','Type'):
        bars=[f for f in frames if any(m.get('name')==name for m in f.get('masks',[]))]
        assert bars and all(f['src']=='/img/frames/m15/regular/m15FrameL.png' for f in bars)
    pinlines=[f for f in frames if any(m.get('name')=='Pinline' for m in f.get('masks',[]))]
    assert pinlines and all(f['src'].startswith('data:image/svg+xml;utf8,') for f in pinlines)
    assert ('nickname' in result['data']['text'])==bool(nickname)

@pytest.mark.parametrize('legendary,nickname',[(False,False),(False,True),(True,False),(True,True)])
@pytest.mark.parametrize('choice',['auto','legend-land','land'])
def test_default_land_four_headers_and_saved_retired_selection(compiler_setup,legendary,nickname,choice):
    compiler,ws,art=compiler_setup
    sf={'name':'Takenuma, Abandoned Mire','type_line':('Legendary ' if legendary else '')+'Land',
        'colors':[],'mana_cost':'','oracle_text':'{T}: Add {B}.','rarity':'rare','artist':'Artist','layout':'normal'}
    if nickname:sf['flavor_name']='The Veil'
    result=compiler.compile_face(sf,sf,0,{'templateOverride':choice},ws.validate_settings({}),art)
    data=result['data'];frames=data['frames']
    panel=next(f['bounds'] for f in frames if f['name']=='50% Black Transparent Rules Fill')
    rules=data['text']['rules']
    padding=rules['y']-panel['y']
    assert rules['y']+rules['height']<=panel['y']+panel['height']-padding+1e-9
    assert rules['bounded'] and not rules['oneLine']
    assert result['recipe']=='land_full_legendary'
    assert ('nickname' in data['text'])==nickname
    assert not any('Temple' in f['name'] for f in frames)
    crowns=[f for f in frames if 'crown' in f['name'].lower()]
    if not legendary:
        assert not crowns
        assert any(m['src']==PREFIX+'lower-pinline.svg' for f in frames for m in f['masks'])
        if nickname:
            assert frames[0]['src']=='/img/frames/proxy-foundry/godzilla/TitleJoinedB.png'
            assert frames[0]['masks']==[]
            assert not any(PREFIX+'TrueName' in frame['src'] for frame in frames)
            assert not any('/nickname/addons/' in f['src'] for f in frames)
    elif nickname:
        assert len(crowns)==1 and crowns[0]['src'].endswith('CrownJoinedBlackB.png')
        assert not any('Generic Showcase Title' in f['name'] for f in frames)
    else:
        assert len(crowns)==2
        assert any(f['src'].endswith('m15CrownBFloating.png') for f in crowns)
        assert any(f['src']==PREFIX+'CrownOutline.png' for f in crowns)
        assert any(f['src']=='/img/frames/proxy-foundry/godzilla/TitleB.png' for f in frames)
        assert not any('/TitleBlack' in f['src'] for f in frames)
    if choice=='land':assert result['templateKey']==compiler.template_identity('legendary-land' if legendary else 'land','legend-land')[0]

def test_retirement_is_hidden_and_persisted_settings_are_redirected(compiler_setup):
    compiler,ws,_=compiler_setup
    assert 'land' not in {template['id'] for template in BUILTINS}
    assert ws.validate_settings({'templateRules':{'land':'land','legendary-land':'land'}})['templateRules']=={'land':'legend-land','legendary-land':'legend-land'}
    assert compiler.template_identity('land','land')==compiler.template_identity('land','legend-land')

def test_rules_box_uses_visible_panel_and_never_expands_a_smaller_box():
    from foundry.land_frame import fit_compact_land_rules
    data={'text':{'rules':{'y':.6743,'height':.2931769722814499}},'frames':[
        {'name':'50% Black Transparent Rules Fill','bounds':{'y':.6687988628287136,'height':.2537313432835821}}]}
    fit_compact_land_rules(data)
    assert data['text']['rules']['height']==pytest.approx(.2427290689410093)
    data['text']['rules']['height']=.10
    fit_compact_land_rules(data)
    assert data['text']['rules']['height']==.10

@pytest.mark.parametrize('name,type_line,recipe',[
    ('Plains','Basic Land — Plains','land_full_basic'),
    ('Tundra','Land — Plains Island','original_dual_land_textless'),
])
def test_other_full_art_land_families_are_unchanged(compiler_setup,name,type_line,recipe):
    compiler,ws,art=compiler_setup
    sf={'name':name,'type_line':type_line,'colors':[],'mana_cost':'','oracle_text':'','rarity':'common','artist':'Artist','layout':'normal'}
    result=compiler.compile_face(sf,sf,0,{},ws.validate_settings({}),art)
    assert result['recipe']==recipe
    assert not any(PREFIX in f['src'] for f in result['data']['frames'])

def test_bundled_join_matches_approved_crop_and_position():
    width,height=GEOMETRY['canvas']
    def placed(name):
        bounds=GEOMETRY['parts'][name];image=Image.open(ASSET_ROOT/(name+'.png')).convert('RGBA')
        canvas=Image.new('RGBA',(width,height));canvas.paste(image,(round(bounds['x']*width),round(bounds['y']*height)))
        return canvas
    assert GEOMETRY['topCropPixels']==1 and GEOMETRY['raisePixels']==2
    assert GEOMETRY['textShift']==pytest.approx(.0405+148*(.1053/221)-(219.5/2100-1.5*(.1053/221))+2/height)
    title,bar=placed('TitleB'),placed('TrueNameB')
    assert bar.getchannel('A').getbbox()[1]==296
    # A small native seam overlap is intentional; the title remains above it.
    assert ImageChops.multiply(title.getchannel('A'),bar.getchannel('A')).getbbox()
    approved=Path(__file__).resolve().parents[1]/'test-results/compact-land-top-crop-1-up-2'
    if (approved/'header-transparent.png').exists():
        actual=Image.alpha_composite(bar,title).crop((0,110,width,410))
        expected=Image.open(approved/'header-transparent.png').convert('RGBA')
        for channel in ImageChops.difference(actual,expected).split():
            assert channel.getbbox() is None
        unchanged_title=Image.open(approved/'title-only.png').convert('RGBA')
        for channel in ImageChops.difference(title.crop((0,110,width,410)),unchanged_title).split():
            assert channel.getbbox() is None


def test_join_preserves_title_and_surviving_subtitle_pixels():
    from scripts.build_land_join_assets import joined_parts,W,H,BAR_SCALE,BAR_Y
    source=Image.new('RGBA',(1500,2100))
    source.paste((39,38,36,255),(50,50,1450,220))
    mask=Image.new('L',source.size,255)
    addon=Image.new('RGBA',(1352,221),(0,0,0,127))
    title,bar=joined_parts(source,mask,addon)
    expected_title=source.copy()
    expected_title.putalpha(source.getchannel('A').point(lambda a:round(a*.68)))
    expected_title=expected_title.resize((W,H),Image.Resampling.LANCZOS)
    for channel in ImageChops.difference(title,expected_title).split():
        assert channel.getbbox() is None
    sx=.9014*W/1352;sy=BAR_SCALE*H
    previous=addon.crop((0,148,1352,221)).transform((W,H),Image.Transform.AFFINE,
        (1/sx,0,-.0494*W/sx,0,1/sy,-BAR_Y*H/sy),Image.Resampling.BICUBIC)
    silhouette=title.getchannel('A').point(lambda a:255 if a>=16 else 0)
    footprint=Image.new('L',(W,H));footprint.paste(silhouette.crop((0,1,W,H)),(0,0))
    previous.putalpha(ImageChops.multiply(previous.getchannel('A'),ImageChops.invert(footprint)))
    left,top,right,bottom=previous.getchannel('A').getbbox()
    expected=previous.crop((left,top+1,right,bottom))
    actual=bar.crop((left,top-1,right,bottom-2))
    for channel in ImageChops.difference(actual,expected).split():
        assert channel.getbbox() is None


def test_runtime_uses_bundled_parts_without_network():
    class NoNetwork:
        def fetch(self,*args,**kwargs):raise AssertionError('Bundled part fetched remotely')
    runtime=Runtime(NoNetwork())
    for name in GEOMETRY['parts']:
        raw,mime=runtime.fetch(PREFIX+name+'.png')
        assert mime=='image/png' and Image.open(io.BytesIO(raw)).width>0


@pytest.mark.parametrize('legendary,nickname',[(False,False),(False,True),(True,False),(True,True)])
@pytest.mark.parametrize('oracle_text,native_pinline',[
    ('{T}: Add {W}.','/img/frames/m15/boxTopper/short/wl.png'),
    ('{T}: Add {B} or {R}.',None),
    ('{T}: Add {W}, {B}, or {R}.',None)])
def test_compact_title_material_is_independent_of_card_colors(compiler_setup,legendary,nickname,oracle_text,native_pinline):
    compiler,ws,art=compiler_setup
    sf={'name':'Example Land','type_line':('Legendary ' if legendary else '')+'Land',
        'colors':[],'mana_cost':'','oracle_text':oracle_text,'rarity':'rare','artist':'Artist','layout':'normal'}
    if nickname:sf['flavor_name']='Example Nickname'
    frames=compiler.compile_face(sf,sf,0,{},ws.validate_settings({}),art)['data']['frames']
    headers=[f for f in frames if f['name'] in {'Compact land black title','Compact land native Godzilla title','Compact land native Godzilla joined title'} or 'CrownJoinedBlack' in f['src']]
    assert headers
    assert not any('Generic Showcase Title' in f['name'] for f in frames)
    assert all('opacity' not in f for f in headers) # Opacity is baked once, not applied twice.
    if not legendary:
        assert all('/godzilla/TitleJoined' in frame['src'] if nickname else '/godzilla/Title' in frame['src'] for frame in headers)
        assert headers[0]['bounds']=={'x':.0494,'y':.0405,'width':.9014,'height':.1053 if nickname else .069}
        assert not any('/compact-land/TrueName' in frame['src'] for frame in frames)
        pinlines=[f for f in frames if any(m.get('src')==PREFIX+'lower-pinline.svg' for m in f.get('masks',[]))]
        assert pinlines and all('opacity' not in f for f in pinlines)
        if native_pinline:assert all(f['src']==native_pinline for f in pinlines)
        else:assert all(f['src'].startswith('data:image/svg+xml') for f in pinlines)

@pytest.mark.parametrize('oracle_text',['{T}: Add {W}.','{T}: Add {B} or {R}.','{T}: Add {W}, {B}, or {R}.'])
def test_all_four_headers_share_identical_lower_frame_layers(compiler_setup,oracle_text):
    compiler,ws,art=compiler_setup;layers=[]
    for legendary,nickname in [(False,False),(False,True),(True,False),(True,True)]:
        sf={'name':'Example Land','type_line':('Legendary ' if legendary else '')+'Land',
            'colors':[],'mana_cost':'','oracle_text':oracle_text,'rarity':'rare','artist':'Artist','layout':'normal'}
        if nickname:sf['flavor_name']='Example Nickname'
        frames=compiler.compile_face(sf,sf,0,{},ws.validate_settings({}),art)['data']['frames']
        lower=[]
        for frame in frames:
            if not any(mask.get('name') in {'Type','Pinline'} for mask in frame.get('masks',[])):continue
            # Full/native and lower-only pinline masks have identical type and
            # rules contours. Only the independent upper title loop differs.
            item=json.loads(json.dumps(frame))
            for mask in item['masks']:
                if mask['src']=='/img/frames/m15/boxTopper/short/pinline.svg':mask['src']=PREFIX+'lower-pinline.svg'
            lower.append(item)
        layers.append(lower)
    assert layers[0] and layers[0]==layers[1]==layers[2]==layers[3]

@pytest.mark.parametrize('oracle_text',[
    '{T}: Add {C}.','{T}: Add {U}.','{T}: Add {B} or {R}.',
    '{T}: Add {W}, {B}, or {R}.','{T}: Add {W}, {U}, {B}, or {R}.',
    '{T}: Add one mana of any color.'])
@pytest.mark.parametrize('legendary,nickname',[(False,False),(False,True),(True,False),(True,True)])
def test_pinline_fade_survives_every_color_count_and_header(compiler_setup,oracle_text,legendary,nickname):
    compiler,ws,art=compiler_setup
    sf={'name':'Example Land','type_line':('Legendary ' if legendary else '')+'Land',
        'colors':[],'mana_cost':'','oracle_text':oracle_text,'rarity':'rare','artist':'Artist','layout':'normal'}
    if nickname:sf['flavor_name']='Nickname'
    frames=compiler.compile_face(sf,sf,0,{},ws.validate_settings({}),art)['data']['frames']
    pinlines=[frame for frame in frames if any(mask.get('name')=='Pinline' for mask in frame.get('masks',[]))]
    assert pinlines
    for frame in pinlines:
        fade=[mask for mask in frame['masks'] if mask['src']==PREFIX+'PinlineFade.png']
        if frame['src'].startswith('data:image/svg+xml'):assert len(fade)==1
        else:
            assert '/boxTopper/short/' in frame['src'] and not fade # Native alpha already exists; never square it.

def test_bundled_fade_preserves_the_native_asset_alpha(tmp_path):
    from scripts.build_compact_pinline_fade import build
    source=Image.new('RGBA',(10,10),(230,210,180,255))
    source.putpixel((3,2),(0,0,0,0));source.putpixel((4,2),(130,100,80,127))
    out=io.BytesIO();source.save(out,'PNG')
    def fetch(path):
        assert path=='/img/frames/m15/boxTopper/short/wl.png'
        return out.getvalue(),'image/png'
    build(fetch,tmp_path)
    result=Image.open(tmp_path/'PinlineFade.png').convert('RGBA')
    assert ImageChops.difference(result.getchannel('A'),source.getchannel('A')).getbbox() is None
    class NoNetwork:
        def fetch(self,*args,**kwargs):raise AssertionError('Fade should be bundled')
    raw,mime=Runtime(NoNetwork()).fetch(PREFIX+'PinlineFade.png')
    fade=Image.open(io.BytesIO(raw)).convert('RGBA')
    assert mime=='image/png' and fade.getpixel((750,1265))[3]==0
    assert fade.getpixel((105,1600))[3]==255


def test_title_tint_preserves_rim_and_matches_type_interior_alpha():
    from scripts.build_compact_land_black_title import black_title,black_crown
    source=Image.new('RGBA',(1500,2100),(20,30,40,255))
    source.paste((154,154,154,230),(100,112,1400,208))
    mask=Image.new('L',source.size)
    mask.paste(255,(80,98,1420,224))
    material=Image.new('RGBA',source.size,(0,0,0,200))
    title=black_title(source,mask,material)
    fill=title.getpixel((1005,201))
    # RGBA resizing can round a premultiplied color channel by one.
    assert abs(fill[3]-144)<=1 and all(abs(value-46)<=1 for value in fill[:3])
    border=title.getpixel((1005,139))
    assert border[3]==255 and all(abs(value-9)<=1 for value in border[:3])
    assert border[0]<title.getpixel((1005,201))[0] # Shading is retained, not flattened.
    assert title.getpixel((1005,80))[3]==0
    crown=Image.new('RGBA',(1428,270),(180,40,20,255))
    crown.paste((0,0,0,127),(65,72,1370,186))
    result=black_crown(crown,material)
    assert result.getpixel((714,130))==(0,0,0,144)
    assert result.getpixel((714,200))==crown.getpixel((714,200))
    assert result.getpixel((20,130))==crown.getpixel((20,130))
