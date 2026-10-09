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

@pytest.mark.parametrize('legendary,nickname',[(False,False),(False,True),(True,False),(True,True)])
@pytest.mark.parametrize('choice',['auto','legend-land','land'])
def test_default_land_four_headers_and_saved_retired_selection(compiler_setup,legendary,nickname,choice):
    compiler,ws,art=compiler_setup
    sf={'name':'Takenuma, Abandoned Mire','type_line':('Legendary ' if legendary else '')+'Land',
        'colors':[],'mana_cost':'','oracle_text':'{T}: Add {B}.','rarity':'rare','artist':'Artist','layout':'normal'}
    if nickname:sf['flavor_name']='The Veil'
    result=compiler.compile_face(sf,sf,0,{'templateOverride':choice},ws.validate_settings({}),art)
    data=result['data'];frames=data['frames']
    assert result['recipe']=='land_full_legendary'
    assert ('nickname' in data['text'])==nickname
    assert not any('Temple' in f['name'] for f in frames)
    crowns=[f for f in frames if 'crown' in f['name'].lower()]
    if not legendary:
        assert not crowns
        assert any(m['src']==PREFIX+'lower-pinline.svg' for f in frames for m in f['masks'])
        if nickname:
            assert frames[0]['src']==PREFIX+'TitleB.png'
            assert frames[1]['src']==PREFIX+'TrueNameB.png'
            assert not any('/nickname/addons/' in f['src'] for f in frames)
    elif nickname:
        assert len(crowns)==1 and crowns[0]['src'].endswith('CrownJoinedB.png')
        assert not any('Generic Showcase Title' in f['name'] for f in frames)
    else:
        assert len(crowns)==2
        assert any(f['src'].endswith('m15CrownBFloating.png') for f in crowns)
        assert any(f['src']==PREFIX+'CrownOutline.png' for f in crowns)
    if choice=='land':assert result['templateKey']==compiler.template_identity('legendary-land' if legendary else 'land','legend-land')[0]

def test_retirement_is_hidden_and_persisted_settings_are_redirected(compiler_setup):
    compiler,ws,_=compiler_setup
    assert 'land' not in {template['id'] for template in BUILTINS}
    assert ws.validate_settings({'templateRules':{'land':'land','legendary-land':'land'}})['templateRules']=={'land':'legend-land','legendary-land':'legend-land'}
    assert compiler.template_identity('land','land')==compiler.template_identity('land','legend-land')

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
