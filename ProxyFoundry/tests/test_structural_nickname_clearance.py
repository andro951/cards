import pytest
from foundry.compiler import Compiler
from tests.test_class_and_enchantment_land import env,cleric_class

@pytest.mark.parametrize('kind',['class','saga','saga-creature'])
def test_nickname_reserves_strip_height_without_moving_ability_bottom(tmp_path,kind):
    store,art,settings=env(tmp_path)
    card=cleric_class() if kind=='class' else {
        'name':'Preview','layout':'saga','type_line':'Enchantment — Saga' if kind=='saga' else 'Enchantment Creature — Saga Dragon',
        'colors':['R'],'mana_cost':'{2}{R}','rarity':'rare','power':'3','toughness':'3',
        'oracle_text':'I — Draw a card.\nII — Draw two cards.\nIII — Draw three cards.'+('\nFlying' if kind=='saga-creature' else ''),
    }
    compiler=Compiler(store)
    normal=compiler.compile_face(card,card,0,{},settings,art)['data']
    named=compiler.compile_face(card,card,0,{'semanticOverrides':{'nickname':'Custom Name'}},settings,art)['data']
    first,last=('level0c','level2c') if kind=='class' else ('ability0','ability2')
    assert named['text'][first]['y']-normal['text'][first]['y']==pytest.approx(named['text']['title']['height'])
    end=lambda data:data['text'][last]['y']+data['text'][last]['height']
    assert end(named)==pytest.approx(end(normal),abs=1/2814)
    assert named['text'][first]['y']>named['text']['title']['y']+named['text']['title']['height']
    if kind=='class':assert named['text']['level3c']['height']==0


def test_native_class_keeps_unused_level_empty():
    from foundry.runtime import Runtime
    class Net:
        def fetch(self,*args,**kwargs):
            return b"card.text['level' + i + 'c'].height = height || 1;",'application/javascript',{}
    raw,_=Runtime(Net()).fetch('/js/frames/versionClass.js')
    assert b'height || 0' in raw and b'height || 1' not in raw
