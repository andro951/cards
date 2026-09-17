import pytest
from foundry.compiler import fit_set_symbol_to_bounds

CARD_H=2814
SYMBOL={'width':512,'height':512}

def frame(bounds_y,type_y=None,version='genericShowcase'):
    text={} if type_y is None else {'type':{'x':.0854,'y':type_y,'width':.8,'height':.0543,'rotation':0}}
    return {
        'width':2010,'height':CARD_H,'version':version,
        'setSymbolBounds':{'x':.9213,'y':bounds_y,'width':.12,'height':.041,'vertical':'center','horizontal':'right'},
        'text':text,
    }

@pytest.mark.parametrize('recipe,data,expected_y',[
    ('card_noncreature',frame(.59355,.5664,'m15Regular'),1606),
    ('land_full_dual',frame(.59355,.5664),1601),
    ('land_full_legendary',frame(.63715,.61),1728),
    ('land_full_basic',frame(.8739,None,'eoeBasics'),2401),
    ('original_dual_land_textless',frame(.87525,.8481,'textlessBasics'),2402),
])
def test_measured_frame_specific_set_symbol_vertical_offsets(recipe,data,expected_y):
    fit_set_symbol_to_bounds(data,SYMBOL,recipe)
    assert data['setSymbolZoom']==pytest.approx(.225)
    assert data['setSymbolY']*CARD_H==pytest.approx(expected_y)

def test_land_family_offsets_are_scoped_without_disabling_global_fit():
    baseline=frame(.59355,.5664,'genericShowcase')
    fit_set_symbol_to_bounds(baseline,SYMBOL,'card_noncreature')
    normal=frame(.59355,.5664,'genericShowcase')
    fit_set_symbol_to_bounds(normal,SYMBOL,'land_full_single')
    assert baseline['setSymbolZoom']==normal['setSymbolZoom']==pytest.approx(.225)
    assert baseline['setSymbolY']*CARD_H-normal['setSymbolY']*CARD_H==pytest.approx(5)
