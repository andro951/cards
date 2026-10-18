import io
import pytest
from PIL import Image
from foundry.compiler import Compiler
from foundry.images import ingest_image
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.werewolf_frame import BLACK_TITLE_FILL, PREFIX


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);out=io.BytesIO()
    Image.new('RGB',(100,140),'gray').save(out,'PNG')
    return Compiler(store),ws.validate_settings({}),ingest_image(store,out.getvalue())['id']


@pytest.mark.parametrize('legendary',[False,True])
@pytest.mark.parametrize('nickname',[False,True])
@pytest.mark.parametrize('index',[0,1])
def test_arrow_transform_default_front_and_colored_back(setup,legendary,nickname,index):
    compiler,settings,art=setup
    prefix='Legendary ' if legendary else ''
    card={'name':'Cecil test // Back','layout':'transform','rarity':'rare','frame_effects':['legendary'] if legendary else [],
          'card_faces':[{'name':'Front','type_line':prefix+'Creature — Human Knight','colors':['B'],
                         'mana_cost':'{B}','oracle_text':'Deathtouch','power':'2','toughness':'3'},
                        {'name':'Back','type_line':prefix+'Creature — Human Knight','colors':['W'],
                         'mana_cost':'','oracle_text':'Lifelink','power':'4','toughness':'4','color_indicator':['W']}]}
    options={'templateOverride':'godzilla-card'}
    if nickname:options['semanticOverrides']={'nickname':'Cain'}
    data=compiler.compile_face(card,card['card_faces'][index],index,options,settings,art)['data']
    frames=data['frames'];sources=[f['src'] for f in frames]
    assert any(src.endswith('/downArrow.png' if index else '/default.png') for src in sources)
    assert any(src==PREFIX+'IconRing.png' for src in sources)
    name=data['text']['nickname' if nickname else 'title']
    icon=next(f for f in frames if f['src'].endswith('/downArrow.png' if index else '/default.png'))
    if index:
        assert icon['bounds']['x']>.5
        assert name['x']==pytest.approx(.0854)
        assert name['x']+name['width']<icon['bounds']['x']
    else:
        assert icon['bounds']['x']<.5
        assert name['x']>=.148
    assert name['text']==('Cain' if nickname else card['card_faces'][index]['name'])
    assert data['text']['pt']['text']==('4/4' if index else '2/3')
    assert name['color']=='white' and name['outlineColor']=='black' and name['outlineWidth']>0
    if legendary and not nickname:
        assert any('/transform/crowns/floating/' in src or '/transform/CrownFloatingBack' in src for src in sources)
    if legendary and nickname:
        assert any(src.endswith('/proxy-foundry/transform/CrownJoined'+('BackW' if index else 'B')+'.png') for src in sources)
        assert not any('/nickname/addons/' in src for src in sources)
    if not index:
        fills=[f for f in frames if f['name']=='Godzilla transform title material']
        assert len(fills)==1
        assert fills[0]['src'].endswith('/godzilla/TitleB.png')
        assert [m['name'] for m in fills[0]['masks']]==['Title']
        assert not any(m.get('name')=='Type' for f in frames for m in f.get('masks',[]))
    else:
        assert not any(src==BLACK_TITLE_FILL for src in sources)
        assert any('/transform/TitleColoredW.png' in f['src'] and any(m['name']=='Title' for m in f['masks']) for f in frames)
        assert any('/transform/regular/backW.png' in f['src'] and any(m['name']=='Type' for m in f['masks']) for f in frames)
        assert any(src.endswith('/ciPips/base.png') for src in sources)


def test_godzilla_land_transform_back_uses_its_native_marker(setup):
    compiler,settings,art=setup
    card={'name':'Map // Land','layout':'transform','rarity':'rare','frame_effects':['compasslanddfc'],
          'card_faces':[{'name':'Map','type_line':'Artifact','colors':[],'mana_cost':'{1}','oracle_text':'Transform.'},
                        {'name':'Land','type_line':'Land','colors':[],'mana_cost':'','oracle_text':'{T}: Add {U}.'}]}
    data=compiler.compile_face(card,card['card_faces'][1],1,{'templateOverride':'godzilla-card'},settings,art)['data']
    assert any(f['src'].endswith('/icons/land.svg') for f in data['frames'])
    assert data['text']['title']['text']=='Land'


def test_artifact_transform_crown_uses_the_cached_gray_material(setup):
    compiler,settings,art=setup
    card={'name':'Artifact // Back','layout':'transform','rarity':'rare','frame_effects':['legendary'],
          'card_faces':[{'name':'Artifact','type_line':'Legendary Artifact Creature — Golem','colors':[],
                         'mana_cost':'{2}','oracle_text':'Vigilance','power':'2','toughness':'2'},
                        {'name':'Back','type_line':'Legendary Artifact Creature — Golem','colors':[],
                         'mana_cost':'','oracle_text':'Flying','power':'4','toughness':'4'}]}
    data=compiler.compile_face(card,card['card_faces'][0],0,
        {'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'Machine'}},settings,art)['data']
    assert any(f['src'].endswith('/gray-artifact/TransformCrownJoined.png') for f in data['frames'])
    assert any(f['src'].endswith('/gray-artifact/Frame.png') for f in data['frames'])
