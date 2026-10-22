import io
from pathlib import Path
import pytest
from PIL import Image,ImageChops
from foundry.compiler import Compiler,BUILTIN_TEMPLATE_VERSIONS
from foundry.images import ingest_image
from foundry.runtime import Runtime
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.werewolf_frame import PREFIX,BLACK_TITLE_FILL,reflect_title_pinline,neutralize_icon_surround

ASSETS=Path(__file__).resolve().parents[1]/'assets/werewolf'

def card(legendary=False):
    prefix='Legendary ' if legendary else ''
    return {'name':'Brutal Cathar // Moonrage Brute','layout':'transform','frame_effects':['sunmoondfc'],
            'rarity':'rare','artist':'Artist','card_faces':[
        {'name':'Brutal Cathar','type_line':prefix+'Creature — Human Soldier Werewolf','colors':['W'],
         'mana_cost':'{2}{W}','oracle_text':'Daybound','power':'2','toughness':'2'},
        {'name':'Moonrage Brute','type_line':prefix+'Creature — Werewolf','colors':['R'],
         'mana_cost':'','oracle_text':'Nightbound','power':'3','toughness':'3'}]}

@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);out=io.BytesIO()
    Image.new('RGB',(100,140),'#456789').save(out,'PNG')
    return Compiler(store),ws.validate_settings({'artist':'Artist'}),ingest_image(store,out.getvalue())['id']

@pytest.mark.parametrize('legendary,nickname',[(False,False),(False,True),(True,False),(True,True)])
@pytest.mark.parametrize('index',[0,1])
def test_both_sides_and_four_headers(setup,legendary,nickname,index):
    compiler,settings,art=setup;sf=card(legendary)
    options={'templateOverride':'godzilla-card'}
    if nickname:options['semanticOverrides']={'nickname':'Garth, Monster Hunter'}
    result=compiler.compile_face(sf,sf['card_faces'][index],index,options,settings,art)
    data=result['data'];frames=data['frames'];sources=[f['src'] for f in frames]
    assert result['group']==('transform-back' if index else 'transform-front')
    if legendary and nickname:
        assert sources[0].endswith('/moon.svg' if index else '/sun.svg')
        assert sources[1]==PREFIX+'IconRing.png'
        assert any(src.endswith('/transform/CrownJoined'+('R' if index else 'W')+'.png') for src in sources)
        assert not any('/nickname/addons/' in src for src in sources)
        assert data['text']['nickname']['x']>=.16
        assert frames[0]['bounds']['x']<.5
        assert any(f['name']=='Godzilla transform title material' for f in frames)
    else:
        assert sources[0].endswith('/moon.svg' if index else '/sun.svg')
        assert sources[1]==PREFIX+'IconRing.png'
        assert frames[0]['bounds']['x']<.5
        assert data['text']['nickname' if nickname else 'title']['x']>=.148
        if legendary:
            assert any('/transform/crowns/floating/' in src for src in sources)
            assert not any('TitlePinline' in src for src in sources)
        else:
            assert PREFIX+'TitlePinline'+('R' if index else 'W')+'.png' in sources
            assert PREFIX+'TitleOutline.png' in sources
            assert not any('/godzilla/TitleJoined' in src for src in sources)
            body=next(f for f in frames if 'm15NicknameFrame' in f['src'])
            assert body['masks'][-1]['src']==PREFIX+'LowerMask.png'
            assert any(m['name']=='Title' and '/transform/regular/maskTitle.png' in m['src'] for f in frames for m in f.get('masks',[]))
            assert data['text']['nickname' if nickname else 'title']['color']=='white'
            assert data['text']['type']['color']=='white'
            if not index:
                fills=[f for f in frames if f['name']=='Godzilla transform title material']
                assert len(fills)==1
                assert fills[0]['src'].endswith('/godzilla/TitleW.png')
                assert [m['name'] for m in fills[0]['masks']]==['Title']
                assert not any(m['name']=='Type' for f in frames for m in f.get('masks',[]))
            else:
                assert not any(f['src']==BLACK_TITLE_FILL for f in frames)
            if nickname:
                assert data['text']['title']['y']==.1129
                assert data['text']['title']['align']=='center'
                assert any('/nickname/addons/' in src for src in sources)
    assert data['text']['rules']['outlineWidth']>0
    assert data['text']['nickname' if nickname else 'title']['outlineWidth']>0
    assert data['text']['nickname' if nickname else 'title']['outlineColor']=='black'
    if index:
        assert any(any(m['name']=='Type' for m in f.get('masks',[])) and f['src'].endswith('/backR.png') for f in frames)
    assert result['templateVersion']==BUILTIN_TEMPLATE_VERSIONS['godzilla-card']+4

def test_dual_front_has_one_black_title_fill_and_preserves_both_pinline_colors(setup):
    compiler,settings,art=setup;sf=card()
    sf['card_faces'][0]['colors']=['W','U']
    sf['card_faces'][0]['mana_cost']='{1}{W}{U}'
    data=compiler.compile_face(sf,sf['card_faces'][0],0,{'templateOverride':'godzilla-card'},settings,art)['data']
    assert sum(f['name']=='Godzilla transform title material' for f in data['frames'])==1
    assert {f['src'] for f in data['frames'] if 'TitlePinline' in f['src']}=={PREFIX+'TitlePinlineW.png',PREFIX+'TitlePinlineU.png'}
    assert data['frames'][0]['src'].endswith('/sun.svg')
    assert data['frames'][1]['src']==PREFIX+'IconRing.png'

@pytest.mark.parametrize('kind',['old-werewolf','other-creature','classic'])
def test_classic_is_preserved_and_other_transforms_get_their_native_markers(setup,kind):
    compiler,settings,art=setup;sf=card()
    if kind=='old-werewolf':sf['frame_effects']=[]
    if kind=='other-creature':
        for face in sf['card_faces']:face['type_line']='Creature — Vampire'
    choice='auto' if kind=='classic' else 'godzilla-card'
    result=compiler.compile_face(sf,sf['card_faces'][0],0,{'templateOverride':choice},settings,art)
    sources=[f['src'] for f in result['data']['frames']]
    if kind=='classic':
        assert not any(src.startswith(PREFIX) for src in sources)
        assert result['recipe']=='m15_transform_front'
    else:
        assert sources[0].endswith('/default.png' if kind=='old-werewolf' else '/sun.svg')
        assert any('/godzilla/Title' in src for src in sources)

def test_reflection_keeps_upper_center_and_removes_lower_rails():
    source=Image.new('RGBA',(100,140))
    # A two-row circle extreme defines the split between rows 10 and 11.
    source.paste((200,30,20,255),(4,10,5,12))
    source.paste((10,20,30,230),(8,6,90,11))
    source.paste((200,30,20,255),(8,20,9,130))
    result=reflect_title_pinline(source)
    upper=result.crop((0,0,100,11));lower=result.crop((0,11,100,22))
    assert all(channel.getbbox() is None for channel in ImageChops.difference(upper,lower.transpose(Image.Transpose.FLIP_TOP_BOTTOM)).split())
    assert result.getchannel('A').crop((0,22,100,140)).getbbox() is None
    assert result.getpixel((4,10))==result.getpixel((4,11))==source.getpixel((4,10))

def test_bundled_headers_need_no_download_or_processing():
    class NoNetwork:
        def fetch(self,*args,**kwargs):raise AssertionError('Unexpected download')
    runtime=Runtime(NoNetwork())
    for path in ASSETS.glob('*.png'):
        if path.name=='IconRing.png':continue
        raw,mime=runtime.fetch(PREFIX+path.name)
        assert mime=='image/png' and raw==path.read_bytes()
    for code in 'WUBRGMAL':
        alpha=Image.open(ASSETS/('TitlePinline'+code+'.png')).getchannel('A')
        assert alpha.crop((0,500,2010,2814)).getbbox() is None
    lower=Image.open(ASSETS/'LowerMask.png').getchannel('A')
    assert lower.crop((0,0,2010,round(.545*2814))).getbbox() is None


def test_neutral_surround_changes_only_red_pixels_and_preserves_alpha():
    source=Image.new('RGBA',(5,1))
    source.putdata([(180,50,35,160),(80,30,20,255),(255,255,255,255),(0,0,0,127),(95,95,95,0)])
    buf=io.BytesIO();source.save(buf,'PNG')
    result=Image.open(io.BytesIO(neutralize_icon_surround(buf.getvalue()))).convert('RGBA')
    pixels=list(result.get_flattened_data())
    assert pixels[0][:3]==(77,77,77) and pixels[1][:3]==(40,40,40)
    assert pixels[2:]==list(source.get_flattened_data())[2:]
    assert result.getchannel('A').tobytes()==source.getchannel('A').tobytes()


def test_real_surround_is_neutral_and_reused_after_restart(tmp_path):
    from foundry.network import Network
    def fail(*args,**kwargs):raise AssertionError('Ring processing requires no downloads')
    runtime=Runtime(Network(Store(tmp_path),transport=fail))
    path=PREFIX+'IconRing.png';raw,mime=runtime.fetch(path)
    assert mime=='image/png' and not runtime.requested[path]['cache']
    source=Image.open(ASSETS/'IconRing.png').convert('RGBA')
    result=Image.open(io.BytesIO(raw)).convert('RGBA')
    assert result.getchannel('A').tobytes()==source.getchannel('A').tobytes()
    for old,new in zip(source.get_flattened_data(),result.get_flattened_data()):
        if old[0]>old[1]+4 and old[0]>old[2]+4:assert new[0]==new[1]==new[2]
        else:assert new==old
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert restarted.fetch(path)[0]==raw and restarted.requested[path]['cache']
