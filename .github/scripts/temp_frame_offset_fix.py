from pathlib import Path


def replace(path, old, new, count=1):
    p=Path(path); text=p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing expected text in {path}: {old[:240]!r}')
    p.write_text(text.replace(old,new,count),encoding='utf-8')

replace('ProxyFoundry/foundry/domain.py',
        "PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v9'",
        "PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v10'")

replace('ProxyFoundry/foundry/compiler.py',
        "M15_SET_SYMBOL_VERTICAL_CENTER=0.59142\n",
        "M15_SET_SYMBOL_VERTICAL_CENTER=0.59142\n\n# Pixel corrections measured from native CardConjurer renders using a 115 px\n# square set symbol. Negative values move the symbol upward. These are scoped\n# by native recipe so ordinary M15/basic frames keep their already-correct\n# placement while the affected land families are centered in their visible bars.\nSET_SYMBOL_RECIPE_Y_OFFSET_PX={\n    'land_colorless':-5,\n    'land_full_single':-5,\n    'land_full_dual':-5,\n    'land_full_tri':-5,\n    'land_five_color':-5,\n    'land_full_legendary':-7,\n    'land_full_dual_legendary':-7,\n    'land_full_tri_legendary':-7,\n    'land_five_color_legendary':-7,\n    'original_dual_land_textless':-3,\n}\n")

replace('ProxyFoundry/foundry/compiler.py',
        'def fit_set_symbol_to_bounds(data,symbol):',
        'def fit_set_symbol_to_bounds(data,symbol,recipe=None):')

replace('ProxyFoundry/foundry/compiler.py',
        "    y=anchor_y\n    if vertical=='center':y-=rendered_h/2\n    elif vertical=='bottom':y-=rendered_h\n    x=_js_round_positive(x);y=_js_round_positive(y)\n",
        "    y=anchor_y\n    if vertical=='center':y-=rendered_h/2\n    elif vertical=='bottom':y-=rendered_h\n    y+=SET_SYMBOL_RECIPE_Y_OFFSET_PX.get(str(recipe or ''),0)\n    x=_js_round_positive(x);y=_js_round_positive(y)\n")

replace('ProxyFoundry/foundry/compiler.py',
        "                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id))",
        "                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),native.infer_layout(d0,native.get_type_info(d0)))")

# Existing geometry test now includes the measured recipe-specific pixel offset.
replace('ProxyFoundry/tests/test_v54_integration.py',
        'from foundry.compiler import Compiler, semantic, M15_SET_SYMBOL_VERTICAL_CENTER, fit_set_symbol_to_bounds, _standard_visible_type_bar',
        'from foundry.compiler import Compiler, semantic, M15_SET_SYMBOL_VERTICAL_CENTER, fit_set_symbol_to_bounds, _standard_visible_type_bar, SET_SYMBOL_RECIPE_Y_OFFSET_PX')
replace('ProxyFoundry/tests/test_v54_integration.py',
        "    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data'];sym=w.store.asset(s['symbols']['rare'])\n",
        "    comp=w.compiler.compile_face(c,c,0,{},s,a['id']);d=comp['data'];sym=w.store.asset(s['symbols']['rare'])\n",
        1)
replace('ProxyFoundry/tests/test_v54_integration.py',
        "    expected_y=anchor_y-rendered_h if vertical=='bottom' else anchor_y-rendered_h/2 if vertical=='center' else anchor_y\n    assert d['setSymbolX']*cw==pytest.approx(round(expected_x),abs=.6)\n",
        "    expected_y=anchor_y-rendered_h if vertical=='bottom' else anchor_y-rendered_h/2 if vertical=='center' else anchor_y\n    expected_y+=SET_SYMBOL_RECIPE_Y_OFFSET_PX.get(comp['recipe'],0)\n    assert d['setSymbolX']*cw==pytest.approx(round(expected_x),abs=.6)\n",
        1)

# Settings now autosave; remove the obsolete browser-test click on the deleted Save button.
replace('ProxyFoundry/tests/test_browser.py',
        "    page.locator('a[data-nav=settings]').click();page.locator('#global-refresh').check();page.click('#save-settings');page.wait_for_timeout(300)\n",
        "    page.locator('a[data-nav=settings]').click();page.locator('#global-refresh').check();page.wait_for_timeout(300)\n")

Path('ProxyFoundry/tests/test_set_symbol_frame_offsets.py').write_text('''import pytest\nfrom foundry.compiler import fit_set_symbol_to_bounds\n\nCARD_H=2814\nSYMBOL={'width':512,'height':512}\n\ndef frame(bounds_y,type_y=None,version='genericShowcase'):\n    text={} if type_y is None else {'type':{'x':.0854,'y':type_y,'width':.8,'height':.0543,'rotation':0}}\n    return {\n        'width':2010,'height':CARD_H,'version':version,\n        'setSymbolBounds':{'x':.9213,'y':bounds_y,'width':.12,'height':.041,'vertical':'center','horizontal':'right'},\n        'text':text,\n    }\n\n@pytest.mark.parametrize('recipe,data,expected_y',[\n    ('card_noncreature',frame(.59355,.5664,'m15Regular'),1606),\n    ('land_full_dual',frame(.59355,.5664),1601),\n    ('land_full_legendary',frame(.63715,.61),1728),\n    ('land_full_basic',frame(.8739,None,'eoeBasics'),2401),\n    ('original_dual_land_textless',frame(.87525,.8481,'textlessBasics'),2402),\n])\ndef test_measured_frame_specific_set_symbol_vertical_offsets(recipe,data,expected_y):\n    fit_set_symbol_to_bounds(data,SYMBOL,recipe)\n    assert data['setSymbolZoom']==pytest.approx(.225)\n    assert data['setSymbolY']*CARD_H==pytest.approx(expected_y)\n\ndef test_land_family_offsets_are_scoped_without_disabling_global_fit():\n    baseline=frame(.59355,.5664,'genericShowcase')\n    fit_set_symbol_to_bounds(baseline,SYMBOL,'card_noncreature')\n    normal=frame(.59355,.5664,'genericShowcase')\n    fit_set_symbol_to_bounds(normal,SYMBOL,'land_full_single')\n    assert baseline['setSymbolZoom']==normal['setSymbolZoom']==pytest.approx(.225)\n    assert baseline['setSymbolY']*CARD_H-normal['setSymbolY']*CARD_H==pytest.approx(5)\n''',encoding='utf-8')
