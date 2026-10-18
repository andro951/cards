"""Visual-recipe validation, persistence and semantic layer conditions."""
import copy,base64,io
from PIL import Image
import pytest
from foundry.template_model import convert_cardconjurer,validate_model,TRANSPARENT
from foundry.domain import ValidationError
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.compiler import custom_data,Compiler


@pytest.fixture
def model(tmp_path):
    workspace=Workspace(Store(tmp_path))
    template=convert_cardconjurer(workspace.template_seed('normal'),'Visual','standard')
    template['legendary']=True
    raw=io.BytesIO();Image.new('RGBA',(2,2),(0,0,0,0)).save(raw,'PNG')
    source='data:image/png;base64,'+base64.b64encode(raw.getvalue()).decode()
    template['visualRecipe']={'version':1,'sources':{'test':source},'layers':[
        {'name':name,'when':condition,'mode':'source-over','opacity':100,'images':{'C':{'asset':'test','mask':None,'bounds':{'x':0,'y':0,'width':1,'height':1}}}}
        for name,condition in [('Base','always'),('Crown','legendary'),('Subtitle','nickname'),('PT','pt')]],
        'bindings':{'title':'title','type':'type','rules':'rules','mana':'mana','pt':'pt'},
        'textRules':{slot:{'when':'pt' if slot=='pt' else 'always','flow':None,'reserveFor':None,'opacity':1} for slot in ['title','type','rules','mana','pt']},
        'divider':True,'ptBounds':None}
    return template


def test_visual_recipe_persists_and_changes_template_fingerprint(tmp_path,model):
    workspace=Workspace(Store(tmp_path/'persist'))
    template=workspace.import_template_file(model)
    assert model['visualRecipe']['sources']['test'].startswith('data:')
    assert all(source.startswith('/api/assets/') for source in template['visualRecipe']['sources'].values())
    before=Compiler(workspace.store).template_identity('standard',template['id'])[1]
    template['visualRecipe']['layers'][0]['opacity']=90
    workspace.save_template(template)
    assert Compiler(workspace.store).template_identity('standard',template['id'])[1]!=before
    assert workspace.export_template_file(template['id'])['visualRecipe']['version']==1
    portable=workspace.export_template_file(template['id'])
    restored=Workspace(Store(tmp_path/'restored')).import_template_file(portable)
    assert restored['visualRecipe']==template['visualRecipe']


@pytest.mark.parametrize('types,subtypes,colors,land_colors,body,accent',[
    (['Artifact'],[],['U'],[],'A','U'),
    (['Artifact'],['Vehicle'],['R'],[],'V','R'),
    (['Land'],[],[],['G'],'L','G'),
    (['Creature'],[],['B'],[],'B','B'),
])
def test_structural_body_and_colored_parts_are_independent(model,types,subtypes,colors,land_colors,body,accent):
    layers=model['visualRecipe']['layers']
    layers[:]=[copy.deepcopy(layers[0]),copy.deepcopy(layers[0])]
    for layer,role in zip(layers,['Frame','Title']):
        layer.update(name=role,role=role)
        layer['images']={code:{'asset':code,'mask':None,'bounds':{'x':0,'y':0,'width':1,'height':1}} for code in 'CWUBRGMALV'}
    model['visualRecipe']['sources']={code:'data:image/png;base64,'+code for code in 'CWUBRGMALV'}
    data=custom_data(model,{'name':'Test','types':types,'subtypes':subtypes,'colors':colors,'land_colors':land_colors})
    assert [frame['src'].rsplit(',',1)[1] for frame in data['frames']]==[accent,body]


def test_conditions_hide_and_show_native_frames_and_nickname(model):
    sem={'name':'Original','nickname':'Nickname','types':['Creature'],'subtypes':[],'colors':['U'],'legendary':True,'power':'2','toughness':'3','oracle_text':'Flying'}
    data=custom_data(validate_model(model),sem)
    assert [frame['name'] for frame in data['frames']]==['PT','Subtitle','Crown','Base']
    assert data['text']['title']['text']=='Nickname'
    plain=custom_data(model,{**sem,'nickname':'','legendary':False,'power':None,'toughness':None})
    assert [frame['name'] for frame in plain['frames']]==['Base']
    assert plain['text']['pt']['text']==''


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(version=99),
    lambda r:r['sources'].update(test='javascript:alert(1)'),
    lambda r:r['layers'][0].update(when='arbitraryCode'),
    lambda r:r['layers'][0].update(opacity=float('nan')),
    lambda r:r['layers'][0]['images']['C'].update(asset='missing'),
    lambda r:r['layers'][0]['images']['C']['bounds'].update(width=-1),
    lambda r:r['bindings'].update(title='unknown'),
    lambda r:r['textRules']['title'].update(reserveFor='missing'),
])
def test_bad_visual_recipes_are_rejected(model,mutation):
    mutation(model['visualRecipe'])
    with pytest.raises(ValidationError):validate_model(model)