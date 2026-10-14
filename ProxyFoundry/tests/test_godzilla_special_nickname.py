import io,json
from pathlib import Path
from urllib.parse import unquote
import pytest
from PIL import Image
from foundry.compiler import Compiler,BUILTINS,FULL_ART_NONLAND_BOUNDS
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.images import ingest_image

@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path);out=io.BytesIO();Image.new('RGB',(100,140),'gray').save(out,'PNG')
    return Compiler(store),Workspace(store).validate_settings({}),ingest_image(store,out.getvalue())['id']

def card(name):
    return json.loads((Path(__file__).parent/'fixtures/godzilla_special'/(name+'.json')).read_text(encoding='utf-8'))

@pytest.mark.parametrize('name,count,code',[('Tezzeret-the-Seeker',3,'U'),('Tezzeret',4,'L')])
@pytest.mark.parametrize('nickname',[False,True])
def test_planeswalker_native_nickname_frame_keeps_every_ability(setup,name,count,code,nickname):
    compiler,settings,art=setup;sf=card(name)
    options={'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'The Inventor' if nickname else ''}}
    result=compiler.compile_face(sf,sf,0,options,settings,art);data=result['data'];text=data['text']
    assert data['version']==('planeswalkerNicknameTall' if count==4 else 'planeswalkerNickname')
    assert data['onload'].endswith('/versionPlaneswalker.js')
    assert data['planeswalker']['count']==count
    assert data['planeswalker']['abilities'][:count]==(['+1','-X','-5'] if count==3 else ['','0','-3','-7'])
    assert text['loyalty']['text']=='4'
    assert any(f['src'].endswith(f'FrameTall{code}.png' if count==4 else f'planeswalkerNicknameFrame{code}.png') for f in data['frames'])
    crown_src=f'/godzilla/CrownJoined{code}.png' if nickname else f'/crowns/m15Crown{code}Floating.png'
    assert any(f['src'].endswith(crown_src) for f in data['frames'])
    if not nickname:
        assert any(f['src'].endswith(f'/godzilla/Title{code}.png') for f in data['frames'])
        assert not any('/godzilla/Crown' in f['src'] for f in data['frames'])
    assert data['artBounds']==FULL_ART_NONLAND_BOUNDS
    rows=[text[f'ability{i}'] for i in range(count)]
    assert rows[0]['y']==pytest.approx(.5539 if count==4 else .6239)
    assert rows[-1]['y']+rows[-1]['height']==pytest.approx(.891)
    assert len({r['size'] for r in rows})==1
    assert all(rows[i]['y']+rows[i]['height']==pytest.approx(rows[i+1]['y']) for i in range(count-1))
    assert all(r['text'] and r['height']>0 for r in rows)
    assert all(r['x']+r['width']<=.9+1e-9 for r in rows)
    assert data['planeswalker']['orig_ability_textbox_width']==.72
    if count==3:
        badge_top=.6639+data['planeswalker']['abilityAdjust'][0]-.0258
        assert rows[0]['height']>=.088
        assert badge_top>text['type']['y']+text['type']['height']+.008
    else:
        assert text['type']['y']==pytest.approx(.4925)
        assert data['setSymbolBounds']['y']==pytest.approx(.5191)
    assert 'rules' not in text and 'pt' not in text
    if count==4:assert rows[0]['x']==.136 and 'Whenever an artifact' in rows[0]['text']
    assert text['nickname' if nickname else 'title']['text']==('The Inventor' if nickname else sf['name'])
    cutouts=[f for f in data['frames'] if f.get('erase')]
    assert len(cutouts)==1
    assert 'y="0"' in unquote(cutouts[0]['src'])
    assert 'height="310"' in unquote(cutouts[0]['src'])
    if nickname:assert text['title']['y']==.1015 and text['title']['align']=='center'
    else:
        assert 'nickname' not in text

@pytest.mark.parametrize('name',['Esika','Bruce-Banner'])
@pytest.mark.parametrize('nickname',[False,True])
@pytest.mark.parametrize('legendary',[False,True])
@pytest.mark.parametrize('index',[0,1])
def test_modal_native_sides_crowns_and_opposite_face_footer(setup,name,nickname,legendary,index):
    compiler,settings,art=setup;sf=card(name)
    for face in sf['card_faces']:
        face['type_line']=face['type_line'].removeprefix('Legendary ')
        if legendary:face['type_line']='Legendary '+face['type_line']
    face=sf['card_faces'][index];other=sf['card_faces'][1-index]
    options={'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'Alternate Name' if nickname else ''}}
    data=compiler.compile_face(sf,face,index,options,settings,art)['data'];text=data['text']
    assert data['version']=='modalNickname'
    assert data['artBounds']==FULL_ART_NONLAND_BOUNDS
    body=next(f for f in data['frames'] if f['name'].startswith('Native modal nickname'))
    assert body['src'].endswith(('b' if index else 'f')+'.png')
    assert text['flipSideReminder']['text']==other['mana_cost']
    assert text['flipsideType']['text']
    assert text['rules']['y']+text['rules']['height']<text['flipsideType']['y']
    assert text['pt']['text']==(face['power']+'/'+face['toughness'] if 'power' in face else '')
    assert text['nickname' if nickname else 'title']['x']==.1614
    assert text['nickname' if nickname else 'title']['outlineWidth']>0
    crowns=[f for f in data['frames'] if '/modal/crowns/' in f['src'] and f['src'].endswith('.png')]
    assert bool(crowns)==legendary
    assert all(('/nickname/' if nickname else '/floating/') in f['src'] for f in crowns)
    assert any(f['name']=='Hide unused true-name strip' for f in data['frames'])!=nickname
    assert not any('/promo/' in f['src'] or '/transform/' in f['src'] for f in data['frames'])
    if nickname:assert text['title']['text']==face['name'] and text['title']['y']==.1129
    if name=='Esika' and index==0:
        # Five opposite-face mana symbols must have space beside the helper label.
        assert text['flipsideType']['width']<.364

def test_planeswalker_option_is_exposed():
    assert 'planeswalker' in next(b for b in BUILTINS if b['id']=='godzilla-card')['groups']

def test_godzilla_selection_does_not_change_classic_planeswalker(setup):
    compiler,settings,art=setup;sf=card('Tezzeret-the-Seeker')
    before=compiler.compile_face(sf,sf,0,{},settings,art)['data']
    compiler.compile_face(sf,sf,0,{'templateOverride':'godzilla-card'},settings,art)
    after=compiler.compile_face(sf,sf,0,{},settings,art)['data']
    assert after==before and after['version']=='planeswalkerRegular'

def test_dual_color_normal_crown_keeps_planeswalker_header_position(setup):
    compiler,settings,art=setup;sf=card('Tezzeret-the-Seeker')
    sf.update(colors=['U','R'],mana_cost='{3}{U}{R}')
    data=compiler.compile_face(sf,sf,0,{'templateOverride':'godzilla-card'},settings,art)['data']
    crowns=[f for f in data['frames'] if f['src'].endswith(('m15CrownUFloating.png','m15CrownRFloating.png'))]
    assert len(crowns)==2
    assert all(f['bounds']['y']==pytest.approx(.0077) for f in crowns)
