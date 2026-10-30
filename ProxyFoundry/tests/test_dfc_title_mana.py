import json
from pathlib import Path
import pytest
from foundry.compiler import Compiler,DFC_TITLE_MANA_VERSION
from test_pipeline import workspace


def fixture(name):
    return json.loads((Path(__file__).parent/'fixtures'/name).read_text(encoding='utf-8'))


@pytest.mark.parametrize('effect',['compasslanddfc','sunmoondfc','originpwdfc'])
@pytest.mark.parametrize('choice',['auto','godzilla-card'])
@pytest.mark.parametrize('nickname',['','A very long alternate name for the green god'])
@pytest.mark.parametrize('cost,right_limit',[('{G}',.88),('{3}{G}{G}',.78),('{W}{U}{B}{R}{G}',.68)])
def test_transform_header_reserves_icon_and_mana_without_narrowing_true_name(workspace,effect,choice,nickname,cost,right_limit):
    store,art,settings=workspace;sf=fixture('ojer_kaslem.json');sf['frame_effects']=[effect]
    front=sf['card_faces'][0];front['mana_cost']=cost
    data=Compiler(store).compile_face(sf,front,0,
        {'templateOverride':choice,'semanticOverrides':{'nickname':nickname}},settings,art)['data']
    main=data['text']['nickname' if nickname else 'title']
    assert main['x']>=.148
    assert main['x']+main['width']<right_limit
    assert main['text']==(nickname or front['name'])
    assert data['text']['mana']['text']==cost
    assert data['text']['pt']['text']=='6/5'
    if nickname:
        true_name=data['text']['title']
        assert true_name['width']==pytest.approx(.72)
        assert true_name['x']+true_name['width']/2==pytest.approx(.5)


@pytest.mark.parametrize('index',[0,1])
@pytest.mark.parametrize('choice',['auto','godzilla-card'])
@pytest.mark.parametrize('nickname',['','A long alternate name for this modal face'])
def test_modal_faces_reserve_their_own_printed_mana_cost(workspace,index,choice,nickname):
    store,art,settings=workspace;sf=fixture('godzilla_special/Esika.json');face=sf['card_faces'][index]
    data=Compiler(store).compile_face(sf,face,index,
        {'templateOverride':choice,'semanticOverrides':{'nickname':nickname}},settings,art)['data']
    main=data['text']['nickname' if nickname else 'title']
    assert main['x']+main['width']<(.78 if index==0 else .68)
    assert data['text']['mana']['text']==face['mana_cost']
    if nickname:
        assert data['text']['title']['text']==face['name']
        if choice=='godzilla-card':assert data['text']['title']['width']==pytest.approx(.72)


@pytest.mark.parametrize('nickname',['','Alternate Name'])
def test_ojer_title_shrinks_only_the_name_field(workspace,monkeypatch,nickname):
    import foundry.compiler as module
    store,art,settings=workspace;sf=fixture('ojer_kaslem.json');front=sf['card_faces'][0];compiler=Compiler(store)
    options={'semanticOverrides':{'nickname':nickname}}
    fixed=compiler.compile_face(sf,front,0,options,settings,art)['data']
    monkeypatch.setattr(module,'reserve_dfc_title_mana_space',lambda data:None)
    old=compiler.compile_face(sf,front,0,options,settings,art)['data']
    slot='nickname' if nickname else 'title'
    assert fixed['text'][slot]['width']<old['text'][slot]['width']
    old['text'][slot]['width']=fixed['text'][slot]['width']
    assert fixed==old


def test_dfc_title_cache_refresh_is_scoped_to_faces_with_mana(workspace,monkeypatch):
    import foundry.compiler as module
    compiler=Compiler(workspace[0]);selections=[
        ('transform-front','auto',{'mana_cost':'{3}{G}{G}'}),
        ('modal-back','godzilla-card',{'mana_cost':'{W}{U}{B}{R}{G}'}),
        ('transform-back','auto',{'mana_cost':''}),
        ('legendary','auto',{'mana_cost':'{3}{G}{G}'}),
        ('token','auto',{'mana_cost':'{3}{G}{G}'})]
    old=[compiler.template_identity(*args) for args in selections]
    monkeypatch.setattr(module,'DFC_TITLE_MANA_VERSION',DFC_TITLE_MANA_VERSION+1)
    new=[compiler.template_identity(*args) for args in selections]
    assert new[0]!=old[0] and new[1]!=old[1]
    assert new[2:]==old[2:]
