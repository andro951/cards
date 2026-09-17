from pathlib import Path


def replace(path, old, new, count=1):
    p=Path(path)
    text=p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing expected text in {path}: {old[:220]!r}')
    p.write_text(text.replace(old,new,count),encoding='utf-8')


replace(
    'ProxyFoundry/foundry/domain.py',
    "PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v7'",
    "PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v8'",
)

p=Path('ProxyFoundry/foundry/compiler.py')
text=p.read_text(encoding='utf-8')
start=text.index('def align_m15_set_symbol_vertical(data,symbol):')
end=text.index('\n\ndef intentional_art_window_crop',start)
new_func='''def fit_set_symbol_to_bounds(data,symbol):
    """Fit a stored set symbol to the active CardConjurer frame bounds.

    This is intentionally version-agnostic. Any native/generated card frame that
    supplies setSymbolBounds gets the same clipping-aware, aspect-preserving fit.
    The frame's own anchor is authoritative. The standard type-bar geometry also
    receives the calibrated visible-bar vertical center used by the M15 family.
    """
    if not symbol:return
    bounds=data.get('setSymbolBounds')
    if not isinstance(bounds,dict):return
    try:
        card_w=float(data.get('width') or 0);card_h=float(data.get('height') or 0)
        symbol_w=float(symbol.get('width') or 0);symbol_h=float(symbol.get('height') or 0)
        bounds_x=float(bounds.get('x') or 0);bounds_y=float(bounds.get('y') or 0)
        bounds_width=float(bounds.get('width') or 0);bounds_height=float(bounds.get('height') or 0)
        bounds_w=_js_round_positive(bounds_width*card_w)
        bounds_h=_js_round_positive(bounds_height*card_h)
    except (TypeError,ValueError,ZeroDivisionError):return
    values=(card_w,card_h,symbol_w,symbol_h,bounds_w,bounds_h,bounds_x,bounds_y)
    if min(card_w,card_h,symbol_w,symbol_h,bounds_w,bounds_h)<=0 or not all(math.isfinite(x) for x in values):return

    # The ordinary CardConjurer type bar is reused by m15Regular,
    # modalRegular, genericShowcase, Station and other generated versions.
    # Apply the measured visible-bar center by geometry, never by version name.
    standard_type_bar=(
        abs(bounds_x-.9213)<=1e-4
        and abs(bounds_width-.12)<=1e-4
        and abs(bounds_height-.041)<=1e-4
        and abs(bounds_y-.591)<=.002
    )
    if standard_type_bar:
        bounds_y=M15_SET_SYMBOL_VERTICAL_CENTER
        bounds['y']=bounds_y
        bounds['vertical']='center'

    anchor_x=_js_round_positive(bounds_x*card_w)
    anchor_y=_js_round_positive(bounds_y*card_h)

    # Mirrors creator-23.js resetSetSymbol(): fit by the limiting bounds
    # dimension, then toFixed(1) on the percentage before converting back.
    if symbol_w/symbol_h > bounds_w/bounds_h:
        percent=bounds_w/symbol_w*100
    else:
        percent=bounds_h/symbol_h*100
    percent=math.floor(percent*10+0.5)/10
    zoom=percent/100
    if zoom<=0:return
    data['setSymbolZoom']=zoom

    rendered_w=symbol_w*zoom;rendered_h=symbol_h*zoom
    horizontal=str(bounds.get('horizontal') or 'center').lower()
    vertical=str(bounds.get('vertical') or 'center').lower()
    x=anchor_x
    if horizontal=='center':x-=rendered_w/2
    elif horizontal=='right':x-=rendered_w
    y=anchor_y
    if vertical=='center':y-=rendered_h/2
    elif vertical=='bottom':y-=rendered_h
    x=_js_round_positive(x);y=_js_round_positive(y)
    data['setSymbolX']=x/card_w;data['setSymbolY']=y/card_h

    # Preserve the compiler's existing 1%-of-card gap for ordinary right-edge
    # type bars. Other frame geometries keep their own text box width.
    box=(data.get('text') or {}).get('type')
    if horizontal=='right' and isinstance(box,dict) and float(box.get('rotation') or 0)%360==0:
        try:box_x=float(box.get('x') or 0)
        except (TypeError,ValueError):return
        box['width']=max(0,data['setSymbolX']-.01-box_x)

# Backward-compatible import name for older tests/callers.
align_m15_set_symbol_vertical=fit_set_symbol_to_bounds
'''
p.write_text(text[:start]+new_func+text[end:],encoding='utf-8')

replace(
    'ProxyFoundry/foundry/compiler.py',
    '                align_m15_set_symbol_vertical(data,self.store.asset(symbol_id))',
    '                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id))',
)

p=Path('ProxyFoundry/tests/test_v54_integration.py')
text=p.read_text(encoding='utf-8')
text=text.replace(
    'from foundry.compiler import Compiler, semantic, M15_SET_SYMBOL_VERTICAL_CENTER',
    'from foundry.compiler import Compiler, semantic, M15_SET_SYMBOL_VERTICAL_CENTER, fit_set_symbol_to_bounds',
)
start=text.index("@pytest.mark.parametrize('name,type_line,layout',[\n    ('Creature','Creature — Elf','normal')")
end=text.index('\n\ndef test_m15_symbol_fit_matches_cardconjurer_reset_for_cropped_mythic',start)
replacement='''@pytest.mark.parametrize('name,type_line,layout',[
    ('Creature','Creature — Elf','normal'),('Artifact','Artifact','normal'),
    ('Land','Land','normal'),('Legendary Land','Legendary Land','normal')])
def test_symbol_right_edge_and_type_gap(env,name,type_line,layout):
    w,_,a,s=env;c=sf(name,type_line=type_line,layout=layout)
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data'];sym=w.store.asset(s['symbols']['rare'])
    cw=d['width'];ch=d['height'];bounds=d['setSymbolBounds']
    rendered_w=sym['width']*d['setSymbolZoom'];rendered_h=sym['height']*d['setSymbolZoom']
    bounds_w=round(bounds['width']*cw);bounds_h=round(bounds['height']*ch)
    assert rendered_w<=bounds_w+.6 and rendered_h<=bounds_h+.6
    assert min(abs(rendered_w-bounds_w),abs(rendered_h-bounds_h))<=1.5
    anchor_x=round(bounds['x']*cw);anchor_y=round(bounds['y']*ch)
    horizontal=bounds.get('horizontal','center');vertical=bounds.get('vertical','center')
    actual_x=d['setSymbolX']*cw;actual_y=d['setSymbolY']*ch
    expected_x=anchor_x-rendered_w if horizontal=='right' else anchor_x-rendered_w/2 if horizontal=='center' else anchor_x
    expected_y=anchor_y-rendered_h if vertical=='bottom' else anchor_y-rendered_h/2 if vertical=='center' else anchor_y
    assert actual_x==pytest.approx(round(expected_x),abs=.6)
    assert actual_y==pytest.approx(round(expected_y),abs=.6)
    if abs(bounds['x']-.9213)<=1e-4 and abs(bounds['width']-.12)<=1e-4 and abs(bounds['height']-.041)<=1e-4:
        assert bounds['y']==pytest.approx(M15_SET_SYMBOL_VERTICAL_CENTER)
    box=d['text']['type']
    if horizontal=='right' and float(box.get('rotation') or 0)%360==0:
        assert (d['setSymbolX']-(box['x']+box['width']))*cw==pytest.approx(.01*cw,abs=.6)
'''
text=text[:start]+replacement+text[end:]

insert_at=text.index('\n\ndef test_m15_symbol_fit_matches_cardconjurer_reset_for_cropped_mythic')
version_test='''

@pytest.mark.parametrize('version',['m15Regular','modalRegular','genericShowcase','stationRegular','futureFrame'])
def test_set_symbol_fit_is_version_independent(version):
    data={'version':version,'width':2010,'height':2814,'setSymbolZoom':.101,
          'setSymbolX':.85,'setSymbolY':.57,
          'setSymbolBounds':{'x':.9213,'y':.591,'width':.12,'height':.041,'vertical':'center','horizontal':'right'},
          'text':{'type':{'x':.0854,'y':.5664,'width':.78,'height':.0543,'rotation':0}}}
    fit_set_symbol_to_bounds(data,{'width':869,'height':1057})
    assert data['setSymbolZoom']==pytest.approx(.109)
    assert data['setSymbolX']*2010==pytest.approx(1757)
    assert data['setSymbolY']*2814==pytest.approx(1606)
    assert data['setSymbolBounds']['y']==pytest.approx(M15_SET_SYMBOL_VERTICAL_CENTER)


def test_set_symbol_fit_respects_nonstandard_frame_anchor():
    data={'version':'anything','width':1000,'height':1000,
          'setSymbolBounds':{'x':.5,'y':.4,'width':.2,'height':.1,'vertical':'bottom','horizontal':'center'},
          'text':{'type':{'x':.1,'width':.5,'rotation':0}}}
    fit_set_symbol_to_bounds(data,{'width':100,'height':200})
    assert data['setSymbolZoom']==pytest.approx(.5)
    assert data['setSymbolX']*1000==pytest.approx(475)
    assert data['setSymbolY']*1000==pytest.approx(300)
    assert data['setSymbolBounds']['y']==pytest.approx(.4)
'''
text=text[:insert_at]+version_test+text[insert_at:]
p.write_text(text,encoding='utf-8')
