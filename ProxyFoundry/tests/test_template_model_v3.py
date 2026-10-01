import copy
from pathlib import Path

import pytest

from foundry.domain import ValidationError
from foundry.template_expressions import evaluate_formula,parse_formula
from foundry.template_model import apply_regions,convert_cardconjurer,select_variant,validate_model
from foundry.workspace import Workspace
from foundry.storage import Store


@pytest.fixture
def model(tmp_path):
    return convert_cardconjurer(Workspace(Store(tmp_path)).template_seed('normal'),'Dynamic','standard')


def test_v2_migrates_without_losing_offsets_and_portable_v3_roundtrips(model,tmp_path):
    model['schemaVersion']=2;model['regions']['title']['offset']={'x':.03}
    migrated=validate_model(model)
    assert migrated['schemaVersion']==3 and migrated['regions']['title']['offset']=={'x':.03}
    source=Workspace(Store(tmp_path/'source'));saved=source.save_template(migrated)
    target=Workspace(Store(tmp_path/'target'));imported=target.import_template_file(source.export_template_file(saved['id']))
    assert imported['regions']==migrated['regions'] and imported['variants']==[]


@pytest.mark.parametrize('expression',["__import__('os')","native.__class__","[x for x in range(100)]","2 ** 9999","min(*[1,2])","lambda: 1","True","1e309"])
def test_geometry_formulas_cannot_execute_code(expression):
    with pytest.raises(ValidationError):parse_formula(expression)


def test_semantic_formulas_and_conditional_variants_are_deterministic(model):
    model['regions']['title']['formulas']={'width':'clamp(native.width - card.titleLength * .001, .2, .9)'}
    model['variants']=[{'when':{'legendary':True},'regions':{'title':{
        **model['regions']['title'],'formulas':{'width':'max(.2, native.width - .1)'}}}}]
    model=validate_model(model)
    reference=copy.deepcopy(model['data']);reference['text']['title']['width']=.7
    sem={'name':'Ten letters','legendary':True}
    variant=select_variant(model,sem,'standard');data=copy.deepcopy(variant['data'])
    apply_regions(data,reference,variant['regions'],sem)
    assert data['text']['title']['width']==pytest.approx(.6)
    assert model['regions']['title']['formulas']['width'].startswith('clamp')
    with pytest.raises(ValidationError):evaluate_formula('native.width / 0',{'native.width':.7})


def test_all_native_structural_slots_survive_conversion_with_dynamic_text(model):
    source=copy.deepcopy(model['data']);source['text']['rules2']={**source['text']['rules'],'text':'Specific payoff'}
    converted=convert_cardconjurer(source,'Station','station')
    assert converted['regions']['rules2']['field']=='native:rules2'
    assert converted['data']['text']['rules2']['text']==''
    reference=copy.deepcopy(source);reference['text']['rules2']['text']='Actual card payoff'
    reference['text']['rules2']['y']=.72
    apply_regions(converted['data'],reference,converted['regions'])
    assert converted['data']['text']['rules2']['text']=='Actual card payoff'
    assert converted['data']['text']['rules2']['y']==.72


@pytest.mark.parametrize('kind',['token-classic','token-full-art','token-borderless','godzilla-land'])
def test_exposed_special_seed_can_be_converted_and_saved(tmp_path,kind):
    workspace=Workspace(Store(tmp_path))
    group='token' if kind.startswith('token-') else 'land'
    converted=convert_cardconjurer(workspace.template_seed(kind),'Seed',group)
    if group=='token':converted['layoutMetadata']={'tokenStyle':kind}
    saved=workspace.save_template(converted)
    assert saved['baseGroup']==group and saved['schemaVersion']==3


def test_invalid_variant_is_rejected_before_rendering(model):
    model['variants']=[{'when':{'colors':[42]}}]
    with pytest.raises(ValidationError):validate_model(model)
    model['variants']=[{'when':{'legendary':'yes'}}]
    with pytest.raises(ValidationError):validate_model(model)
    model['variants']=[{'frames':[{'src':'javascript:alert(1)'}]}]
    with pytest.raises(ValidationError):validate_model(model)



@pytest.mark.parametrize('bad',[{'colors':['U','U']},{'colors':[[]]}])
def test_invalid_color_conditions_fail_cleanly(model,bad):
    model['variants']=[{'when':bad}]
    with pytest.raises(ValidationError):validate_model(model)


def test_geometry_types_and_unbounded_formulas_are_rejected(model):
    model['data']['text']['title']['width']='wide'
    with pytest.raises(ValidationError):validate_model(model)
    model['data']['text']['title']['width']=.5
    model['regions']['title']['formulas']={'width':'100000'}
    with pytest.raises(ValidationError):apply_regions(model['data'],copy.deepcopy(model['data']),model['regions'])


@pytest.mark.parametrize('land',[False,True])
def test_station_template_updates_badges_and_payoff_from_the_actual_card(tmp_path,land):
    import io,json
    from PIL import Image
    from foundry.images import ingest_image
    from tests.test_v58_station import card
    workspace=Workspace(Store(tmp_path));buffer=io.BytesIO();Image.new('RGB',(900,1400)).save(buffer,'PNG')
    art=ingest_image(workspace.store,buffer.getvalue())['id'];settings=workspace.validate_settings({})
    seed=card(legendary=False)
    if land:seed=json.loads((Path(__file__).parent/'fixtures/station_lands/adagia.json').read_text(encoding='utf-8'))
    compiled=workspace.compiler.compile_face(seed,seed,0,{},settings,art)
    template=workspace.save_template(convert_cardconjurer(compiled['data'],'Station','station'))
    changed=copy.deepcopy(seed);changed['oracle_text']=changed['oracle_text'].replace('7+ |','9+ |').replace('12+ |','15+ |')
    changed['oracle_text']=changed['oracle_text'].split('|')[0]+'| Draw three cards.'
    result=workspace.compiler.compile_face(changed,changed,0,{'templateOverride':template['id']},settings,art)
    assert result['data']['station']['badgeValues'][-1]==('15+' if land else '9+')
    assert result['data']['text']['ability2']['text']=='Draw three cards.'
    assert result['data']['text']['title']['text']==changed['name']



def test_fully_shadowed_variant_cannot_receive_false_preview_approval(model):
    model['variants']=[{'when':{'legendary':True}},{'when':{'legendary':True,'colors':['U']}}]
    with pytest.raises(ValidationError,match='previous variant'):validate_model(model)



def test_declaring_station_support_does_not_approve_a_plain_frame(tmp_path):
    import io
    from PIL import Image
    from foundry.images import ingest_image
    from tests.test_v58_station import card
    workspace=Workspace(Store(tmp_path));buffer=io.BytesIO();Image.new('RGB',(900,1400)).save(buffer,'PNG')
    art=ingest_image(workspace.store,buffer.getvalue())['id'];settings=workspace.validate_settings({})
    model=convert_cardconjurer(workspace.template_seed('normal'),'Incomplete','station');model['legendary']=True
    template=workspace.save_template(model);source=card()
    with pytest.raises(ValidationError,match='native text regions'):
        workspace.compiler.compile_face(source,source,0,{'templateOverride':template['id']},settings,art)