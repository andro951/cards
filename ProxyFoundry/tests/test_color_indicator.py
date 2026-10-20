import copy
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import pytest

from foundry.color_indicator import COLORS, PREFIX, BASE_BOUNDS, INDICATOR_NAME, INDICATOR_BASE_NAME, apply_color_indicator
from foundry.compiler import Compiler
from foundry.images import ingest_image
from foundry.storage import Store
from foundry.workspace import Workspace
from tests.test_werewolf_godzilla import card


def data():
    return {'width':2010,'height':2814,'frames':[],
            'text':{'type':{'x':.0854,'y':.57,'width':.78,'height':.04}}}


@pytest.mark.parametrize('colors',[['R'],['W','U'],['W','U','B'],list('WUBRG')])
def test_circle_has_face_colors_outline_and_clearance(colors):
    compiled = data()
    original_right = compiled['text']['type']['x']+compiled['text']['type']['width']
    assert apply_color_indicator(compiled,{'color_indicator':colors})
    frame = compiled['frames'][0]
    assert frame['name'] == INDICATOR_NAME
    base=next(f for f in compiled['frames'] if f['name']==INDICATOR_BASE_NAME)
    assert base['src']==PREFIX+'base.png'
    bounds = base['bounds']
    assert bounds == BASE_BOUNDS
    box = compiled['text']['type']
    assert bounds['x']+bounds['width'] < box['x']
    assert box['x']+box['width'] == pytest.approx(original_right)
    if len(colors)<=3:
        assert [f['src'] for f in compiled['frames'][:-1]] == [PREFIX+c.lower()+'.svg' for c in colors]
        assert all(bool(f['masks'])==(len(colors)>1) for f in compiled['frames'][:-1])
    else:
        svg = ET.fromstring(unquote(frame['src'].split(',',1)[1]))
        assert [element.get('fill') for element in svg] == [COLORS[color] for color in colors]
    snapshot = copy.deepcopy(compiled)
    assert not apply_color_indicator(compiled,{'color_indicator':colors})
    assert compiled == snapshot


@pytest.mark.parametrize('face',[{'colors':['R']},{'color_indicator':[]},{'color_indicator':['C']},{}])
def test_faces_without_a_printed_indicator_are_unchanged(face):
    compiled = data()
    snapshot = copy.deepcopy(compiled)
    assert not apply_color_indicator(compiled,face)
    assert compiled == snapshot


@pytest.mark.parametrize('legendary',[False,True])
@pytest.mark.parametrize('nickname',[False,True])
@pytest.mark.parametrize('style',['auto','godzilla-card'])
def test_production_dfc_back_has_indicator_and_front_does_not(tmp_path, legendary, nickname,style):
    from PIL import Image
    import io
    store = Store(tmp_path);workspace = Workspace(store)
    output = io.BytesIO();Image.new('RGB',(100,140),'gray').save(output,'PNG')
    art = ingest_image(store,output.getvalue())['id']
    sf = card(legendary)
    sf['card_faces'][1]['color_indicator'] = ['R']
    options = {'templateOverride':style}
    if nickname:options['semanticOverrides'] = {'nickname':'Garth'}
    settings = workspace.validate_settings({})
    compiler = Compiler(store)
    for index, face in enumerate(sf['card_faces']):
        result = compiler.compile_face(sf,face,index,options,settings,art)['data']
        indicators = [frame for frame in result['frames'] if frame['name'] == INDICATOR_NAME]
        assert len(indicators) == index
        if index:
            bounds = next(f for f in result['frames'] if f['name']==INDICATOR_BASE_NAME)['bounds'];box = result['text']['type']
            assert bounds['x']+bounds['width'] < box['x']
            assert box['x']+box['width'] <= result['setSymbolX']-.009


def test_regular_indicator_cache_refresh_is_limited_to_faces_with_printed_indicators(tmp_path):
    compiler=Compiler(Store(tmp_path))
    for group in ('transform-front','transform-back'):
        original=compiler.template_identity(group,'auto',{})
        assert compiler.template_identity(group,'auto',{'colors':['U']})==original
        assert compiler.template_identity(group,'auto',{'color_indicator':[]})==original
        printed=compiler.template_identity(group,'auto',{'color_indicator':['U']})
        assert printed[0]==original[0] and printed[1:]==(original[1]+1,original[2]+1)
        assert compiler.template_identity(group,'godzilla-card',{'color_indicator':['U']})==compiler.template_identity(group,'godzilla-card',{})
