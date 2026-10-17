import copy
import pytest
from foundry.hybrid_frame import hybrid_colors,apply_hybrid_frame_treatment


@pytest.mark.parametrize('cost,colors,expected',[
    ('{3}{W/U}{W/U}',['U','W'],['W','U']),
    ('{X}{B/G}{B/G}',['B','G'],['B','G']),
    ('{2}{W}{U}',['W','U'],[]),
    ('{2}{W}{U}{W/U}',['W','U'],[]),
    ('{W}{U/B}',['W','U','B'],[]),
    ('{2/W}{2/W}',['W'],[]),
    ('{W/P}{U/P}',['W','U'],[]),
    ('',['W','U'],[]),
])
def test_hybrid_detection_distinguishes_mana_costs(cost,colors,expected):
    assert hybrid_colors({'types':['Creature'],'colors':colors,'mana_cost':cost,
                          'oracle_text':'{W/U}: Draw a card.'})==expected


def test_native_hybrid_materials_replace_gold_without_altering_structure():
    data={'frames':[
        {'src':'/img/frames/m15/regular/m15FrameM.png','name':name,
         'masks':[{'name':name,'src':'/native/'+name+'.png'}]}
        for name in ('Title','Type','Rules','Frame','Border')
    ]+[{'src':'/img/frames/m15/regular/m15PTM.png','name':'Power/Toughness',
        'bounds':{'x':.7573,'y':.8848,'width':.188,'height':.0733},'masks':[]}]}
    before=copy.deepcopy(data)
    sem={'types':['Creature'],'colors':['U','W'],'mana_cost':'{3}{W/U}{W/U}'}
    assert apply_hybrid_frame_treatment(data,sem)
    for name in ('Title','Type'):
        assert next(f for f in data['frames'] if f.get('masks') and f['masks'][0]['name']==name)['src'].endswith('m15FrameL.png')
    for name in ('Rules','Frame'):
        layers=[f for f in data['frames'] if f.get('masks') and f['masks'][0]['name']==name]
        assert [f['src'].rsplit('/',1)[-1] for f in layers]==['m15FrameU.png','m15FrameW.png']
        assert layers[0]['masks'][1]['name']=='Hybrid Right Blend'
    assert next(f for f in data['frames'] if f.get('masks') and f['masks'][0]['name']=='Border')==before['frames'][4]
    assert data['frames'][-1]['src'].endswith('m15PTC.png')
    assert data['frames'][-1]['bounds']==before['frames'][-1]['bounds']
    gold=copy.deepcopy(before)
    assert not apply_hybrid_frame_treatment(gold,{**sem,'mana_cost':'{3}{W}{U}'})
    assert gold==before
