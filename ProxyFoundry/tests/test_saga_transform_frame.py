import copy,io
import pytest
from PIL import Image,ImageDraw
from foundry.color_indicator import BASE_BOUNDS,INDICATOR_BASE_NAME,INDICATOR_NAME,apply_color_indicator
from foundry.compiler import Compiler,semantic
from foundry.saga_frame import PREFIX,transform_back_png
from foundry.runtime import Runtime
from foundry.network import Network
from foundry.storage import Store
from test_transform_dfc import env


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def test_native_header_and_type_material_preserve_the_saga_body():
    saga=Image.new('RGBA',(1500,2100),'beige');back=Image.new('RGBA',saga.size,'gray')
    ImageDraw.Draw(back).rectangle((89,1181,1410,1302),fill='brown')
    mask=Image.new('RGBA',saga.size)
    ImageDraw.Draw(mask).rectangle((89,1774,1410,1895),fill='white')
    result=Image.open(io.BytesIO(transform_back_png(png(saga),png(back),png(mask))))
    assert result.crop((0,60,1500,237)).tobytes()==back.crop((0,60,1500,237)).tobytes()
    assert result.getpixel((200,1800))==(165,42,42,255)
    assert result.crop((0,237,1500,1774)).tobytes()==saga.crop((0,237,1500,1774)).tobytes()
    assert result.crop((0,1896,1500,2100)).tobytes()==saga.crop((0,1896,1500,2100)).tobytes()


def test_derived_saga_back_reuses_its_durable_cached_asset(tmp_path):
    calls=[];frame=png(Image.new('RGBA',(1500,2100),'gray'))
    def transport(url):calls.append(url);return frame,'image/png',{}
    runtime=Runtime(Network(Store(tmp_path),transport=transport))
    path=PREFIX+'back-right-W.png';first=runtime.fetch(path)
    assert len(calls)==3
    def fail(url):pytest.fail('Cached Saga material downloaded again: '+url)
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert restarted.fetch(path)==first
    assert restarted.requested[path]['cache']


@pytest.mark.parametrize('colors',[['W'],['W','U'],['W','U','B'],list('WUBRG')])
def test_saga_indicator_uses_bottom_type_bar_for_all_native_pip_styles(colors):
    box={'x':.0854,'y':.8481,'width':.78,'height':.0543}
    data={'saga':{'count':3},'text':{'type':copy.deepcopy(box)},'frames':[]}
    assert apply_color_indicator(data,{'color_indicator':colors})
    base=next(f for f in data['frames'] if f['name']==INDICATOR_BASE_NAME)['bounds']
    pip=next(f for f in data['frames'] if f['name']==INDICATOR_NAME)['bounds']
    assert base['y']+base['height']/2==pytest.approx(box['y']+box['height']/2)
    assert pip['y']==pytest.approx(base['y']-BASE_BOUNDS['y'])
    assert data['text']['type']['x']>base['x']+base['width']
    assert data['text']['type']['x']+data['text']['type']['width']==pytest.approx(box['x']+box['width'])


def argent():
    return {'name':'Elesh Norn // The Argent Etchings','layout':'transform','frame_effects':['legendary'],'rarity':'mythic',
        'card_faces':[
            {'name':'Elesh Norn','type_line':'Legendary Creature — Phyrexian Praetor','colors':['W'],'mana_cost':'{2}{W}{W}',
             'oracle_text':'Vigilance','power':'3','toughness':'5'},
            {'name':'The Argent Etchings','type_line':'Enchantment — Saga','colors':['W'],'color_indicator':['W'],'mana_cost':'',
             'oracle_text':'I — Incubate 2 five times, then transform all Incubator tokens you control.\n'
                 'II — Creatures you control get +1/+1 and gain double strike until end of turn.\n'
                 'III — Destroy all other permanents except for artifacts, lands, and Phyrexians. Exile this Saga, then return it to the battlefield (front face up).'}]}


def test_argent_back_has_dark_native_bars_right_marker_and_bottom_indicator(tmp_path):
    choice='auto'
    store,art,settings=env(tmp_path);sf=argent();face=sf['card_faces'][1]
    result=Compiler(store).compile_face(sf,face,1,{'templateOverride':choice},settings,art)
    data=result['data']
    assert result['recipe']=='saga_transform_back' and data['saga']['count']==3
    assert PREFIX+'back-right-W.png' in [f['src'] for f in data['frames']]
    assert data['text']['title']['color']==data['text']['type']['color']=='white'
    assert data['text']['title']['x']+data['text']['title']['width']<.86
    #The native reverse header already embeds its single down-arrow marker.
    assert not any('/transform/icons/' in f['src'] for f in data['frames'])
    base=next(f for f in data['frames'] if f['name']==INDICATOR_BASE_NAME)['bounds']
    assert base['y']>.84
    compiler=Compiler(store)
    raw_identity=compiler.template_identity('transform-back',choice,{**face,'frame_effects':sf['frame_effects']})
    semantic_identity=compiler.template_identity('transform-back',choice,
        {**semantic(sf,face,1),'frame_effects':sf['frame_effects'],'color_indicator':face['color_indicator']})
    assert raw_identity==semantic_identity
    assert result['templateVersion']==raw_identity[1]


def test_saga_refresh_does_not_invalidate_unrelated_cards(tmp_path):
    compiler=Compiler(Store(tmp_path));face=argent()['card_faces'][1]
    for choice in ('auto','normal'):
        baseline=compiler.template_identity('transform-back',choice,{})
        saga=compiler.template_identity('transform-back',choice,{**face,'color_indicator':[]})
        assert saga==(baseline[0],baseline[1]+1,baseline[2]+1)
        assert compiler.template_identity('transform-front',choice,{**face,'color_indicator':[]})==compiler.template_identity('transform-front',choice,{})
    assert compiler.template_identity('transform-back','godzilla-card',face)==compiler.template_identity('transform-back','godzilla-card',{})
