import copy
import io

import pytest
from PIL import Image

from foundry.domain import ValidationError
from foundry.storage import Store
from foundry.template_model import apply_regions, convert_cardconjurer, validate_model
from foundry.workspace import Workspace
from foundry.images import ingest_image


def test_cardconjurer_conversion_discards_card_specific_media(tmp_path):
    workspace=Workspace(Store(tmp_path))
    source=workspace.template_seed('normal')
    source['artSource']='https://cards.scryfall.io/example.jpg'
    source['setSymbolSource']='https://cards.scryfall.io/symbol.png'
    source['watermarkSource']='https://cards.scryfall.io/watermark.png'
    source['text']['title']['text']='Specific card name'
    converted=convert_cardconjurer(source,'Reusable','standard')
    assert converted['schemaVersion']==3
    assert 'artSource' not in converted['data']
    assert 'setSymbolSource' not in converted['data']
    assert converted['data']['watermarkOpacity']==0
    assert converted['data']['text']['title']['text']==''
    assert converted['regions']['title']['geometry']=='native'
    assert validate_model(converted)['name']=='Reusable'


def test_dynamic_regions_follow_native_geometry_with_small_offsets(tmp_path):
    workspace=Workspace(Store(tmp_path))
    template=convert_cardconjurer(workspace.template_seed('normal'),'Reusable','standard')
    template['regions']['title']['offset']={'x':.01,'width':-.02}
    data=copy.deepcopy(template['data'])
    reference=workspace.template_seed('normal')
    reference['text']['title']['x']=.20
    reference['text']['title']['width']=.70
    apply_regions(data,reference,template['regions'])
    assert data['text']['title']['x']==pytest.approx(.21)
    assert data['text']['title']['width']==pytest.approx(.68)
    template['regions']['title']['offset']['x']=.8
    with pytest.raises(ValidationError):validate_model(template)


def test_template_in_use_cannot_be_deleted(tmp_path):
    workspace=Workspace(Store(tmp_path))
    template=workspace.save_template(convert_cardconjurer(workspace.template_seed('normal'),'Reusable','standard'))
    deck=workspace.new_deck('Using this style')
    settings={**deck['settings'],'templateRules':{'standard':template['id']}}
    workspace.store.put('decks',{**deck,'settings':settings},deck['revision'])
    with pytest.raises(ValidationError,match='Using this style'):
        workspace.delete_template(template['id'],template['revision'])


def test_template_json_carries_uploaded_frame_images(tmp_path):
    source=Workspace(Store(tmp_path/'source'))
    buffer=io.BytesIO();Image.new('RGBA',(120,160),'orange').save(buffer,'PNG')
    frame=ingest_image(source.store,buffer.getvalue())['id']
    model=convert_cardconjurer(source.template_seed('normal'),'Portable','standard')
    model['data']['frames'].append({'name':'Uploaded frame','src':'/api/assets/'+frame,
                                    'bounds':{'x':0,'y':0,'width':1,'height':1},'masks':[]})
    saved=source.save_template(model)
    exported=source.export_template_file(saved['id'])
    assert frame in exported['assets']
    destination=Workspace(Store(tmp_path/'destination'))
    imported=destination.import_template_file(exported)
    assert destination.store.asset(frame)
    assert imported['data']['frames'][-1]['src']=='/api/assets/'+frame
    exported['assets'][frame]['base64']='corrupt'
    third=Workspace(Store(tmp_path/'third'))
    with pytest.raises((ValidationError,ValueError)):
        third.import_template_file(exported)
