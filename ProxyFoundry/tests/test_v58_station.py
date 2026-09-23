"""Tests taken from the supplied v54→v58 handoff. No replacement template math."""
import copy, io, json
from pathlib import Path
import pytest
from PIL import Image
from foundry.compiler import Compiler, semantic, fit_set_symbol_to_bounds, apply_station_underframe_policy
from foundry.domain import ValidationError, GENERATION_VERSION
from foundry.images import ingest_image, data_uri
from foundry.legacy import compiler as native
from foundry.storage import Store
from tests.test_v54_integration import flip_record

REMINDER='Station (Tap another untapped creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery.)'
PRE='At the beginning of combat on your turn, draw a card.'
PAYOFF='Flying\nOther artifacts you control have indestructible.'

def card(colors=('U','R'),legendary=True,pre=True,tiers=1):
    top=(PRE+'\n' if pre else '')+REMINDER
    rules=top+'\n7+ | '+PAYOFF if tiers==1 else top+'\n3+ | Draw a card.\nKeep this line in the first tier.\n12+ | Flying\nKeep this line in the second tier.'
    return {'name':'Station Test','type_line':('Legendary ' if legendary else '')+'Artifact — Spacecraft',
      'layout':'normal','colors':list(colors),'mana_cost':'{2}{U}{R}','oracle_text':rules,
      'power':'5','toughness':'5','rarity':'rare','artist':'Original Station Artist'}

@pytest.fixture
def env(tmp_path):
    s=Store(tmp_path)
    def image(size):
        b=io.BytesIO();Image.new('RGB',size,'#657ca0').save(b,'PNG');return ingest_image(s,b.getvalue())
    symbol=image((600,300));landscape=image((900,600));portrait=image((900,1400))
    settings={'symbols':{r:symbol['id'] for r in ['common','uncommon','rare','mythic']},'modificationCredit':'Modified by ChatGPT'}
    return s,Compiler(s),landscape,portrait,settings

def test_threshold_continuation_and_seriema_shape():
    p=native.parse_station_oracle(card()['oracle_text'])
    assert p['ability_texts']==[PRE,'Station {i}'+REMINDER[len('Station '):]+'{/i}',PAYOFF]
    assert p['badge_values']==['','','7+'] and not p['disable_first_ability']
    assert p['station_abilities'][0]['text']==PAYOFF

def test_compact_one_threshold_and_two_tiers():
    p=native.parse_station_oracle(card(pre=False)['oracle_text'])
    assert p['disable_first_ability'] and p['ability_texts'][0]==''
    q=native.parse_station_oracle(card(tiers=2)['oracle_text'])
    assert q['badge_values']==['','3+','12+'] and not q['disable_first_ability']
    assert 'Keep this line in the first tier.' in q['ability_texts'][1]
    assert 'Keep this line in the second tier.' in q['ability_texts'][2]
    assert PRE in q['ability_texts'][0] and REMINDER[:7] in q['ability_texts'][0]

def test_station_invalid_structures_fail(env):
    _,comp,a,_,settings=env
    for rules in ['',REMINDER,REMINDER+'\n1+ | A\n2+ | B\n3+ | C']:
        c=card();c['oracle_text']=rules
        with pytest.raises(ValidationError):comp.compile_face(c,c,0,{},settings,a['id'])
    c=card();c['type_line']='Creature — Spacecraft'
    with pytest.raises(ValidationError,match='without Artifact'):comp.compile_face(c,c,0,{},settings,a['id'])

@pytest.mark.parametrize('colors',[[],['U'],['U','R'],['W','U','B']])
@pytest.mark.parametrize('legendary',[False,True])
def test_native_station_structure_and_layering(env,colors,legendary):
    store,comp,a,_,settings=env;c=card(colors=colors,legendary=legendary)
    r=comp.compile_face(c,c,0,{},settings,a['id'],art_origin='Scryfall selected printing');d=r['data']
    assert r['recipe']=='station' and r['group']=='station'
    assert d['version']=='stationRegular' and d['onload']=='/js/frames/versionStation.js'
    assert 'rules' not in d['text'] and all(k in d['text'] for k in ['ability0','ability1','ability2','pt'])
    assert d['text']['ability2']['text']==PAYOFF and d['text']['pt']['text']=='5/5'
    assert d['station']['badgeSettings']=={'fontSize':.0245,'width':151.2,'height':151.2,'x':-88,'y':3}
    assert not any(native._is_pt_frame(f) for f in d['frames'])
    base=next(i for i,f in enumerate(d['frames']) if native._is_station_base_overlay(f))
    pin=next(i for i,f in enumerate(d['frames']) if native._is_station_pinline_layer(f))
    assert pin<base and d['frames'][pin]['masks'][0]['src'].endswith('m15MaskPinline.png')
    frame_components=[f for f in d['frames'][base+1:] if any(mask.get('name')=='Frame' for mask in f.get('masks',[]))]
    if len(colors)==0:assert frame_components==[]
    elif len(colors)==1:assert len(frame_components)==1 and frame_components[0]['src']==f'/img/frames/m15/regular/m15Frame{colors[0]}.png'
    else:assert len(frame_components)==1 and frame_components[0]['src']=='/img/frames/m15/regular/m15FrameM.png'
    assert all(i<pin for i,f in enumerate(d['frames']) if '/crowns/' in str(f.get('src','')) or 'legend crown' in f.get('name','').lower())
    pinframe=d['frames'][pin]
    if len(colors)==0:assert pinframe['src']=='/img/frames/station/a.png'
    elif len(colors)==1:assert pinframe['src']=='/img/frames/station/u.png'
    elif len(colors)==2:assert pinframe['src']==native.dual_gradient_fill_src(*native.canonical_dual_color_order(colors))
    else:assert pinframe['src']=='/img/frames/station/m.png'
    assert d['infoArtist']=='Original Station Artist · Modified by ChatGPT'

def test_scryfall_station_uses_art_window_but_custom_art_uses_full_art_placement(env):
    s,comp,landscape,portrait,settings=env;c=card()
    result=comp.compile_face(c,c,0,{},settings,landscape['id'],art_origin='Scryfall selected printing');d=result['data']
    assert (d['artX'],d['artY'],d['artZoom'])==(156/2010,320/2814,2.73)
    assert d['artBounds']=={'x':0.068,'y':0.027,'width':0.864,'height':0.9}
    assert result['crop']['cropX']>.20 and not result['crop']['warning']
    assert result['crop']['intentionalArtWindow'] is True

    for art in (landscape,portrait):
        custom=comp.compile_face(c,c,0,{},settings,art['id'],art_origin='GitHub folder');data=custom['data']
        inner_w=data['width']-160;inner_h=data['height']-160
        expected_zoom=max(inner_w/art['width'],inner_h/art['height'])
        scaled_w=art['width']*expected_zoom;scaled_h=art['height']*expected_zoom
        expected_x=80 if scaled_w<=inner_w+1e-9 else (data['width']-scaled_w)/2
        expected_y=80 if scaled_h<=inner_h+1e-9 else (data['height']-scaled_h)/2
        assert data['artX']*data['width']==pytest.approx(expected_x)
        assert data['artY']*data['height']==pytest.approx(expected_y)
        assert data['artZoom']==pytest.approx(expected_zoom)
        assert data['artBounds']['height']*data['height']==pytest.approx(inner_h)
        assert not any(any(mask.get('name')=='Frame' for mask in frame.get('masks',[])) for frame in data['frames'])

    manual=comp.compile_face(c,c,0,{'fit':{'artX':.1,'artY':.2,'artZoom':1.2,'artRotate':0}},settings,landscape['id'],art_origin='uploaded override')
    assert manual['data']['artBounds']['x']*manual['data']['width']==pytest.approx(80)
    assert manual['data']['artBounds']['height']*manual['data']['height']==pytest.approx(manual['data']['height']-160)
    assert (manual['data']['artX'],manual['data']['artY'],manual['data']['artZoom'])==(.1,.2,1.2)
    assert manual['crop']['warning'] and not manual['crop'].get('intentionalArtWindow')


def test_station_underframe_policy_depends_on_art_source_not_card_color(env):
    _,comp,landscape,_,settings=env
    for colors in ([],['W'],['U','R'],['W','U','B']):
        c=card(colors=colors)
        result=comp.compile_face(c,c,0,{},settings,landscape['id'],art_origin='Scryfall selected printing')
        frame_components=[frame for frame in result['data']['frames'] if any(mask.get('name')=='Frame' for mask in frame.get('masks',[]))]
        assert len(frame_components)==1
        assert frame_components[0]['src']=='/img/frames/m15/regular/m15FrameA.png'
        assert frame_components[0]['name']=='Artifact Frame'

        custom=comp.compile_face(c,c,0,{},settings,landscape['id'],art_origin='computer folder')
        assert not any(any(mask.get('name')=='Frame' for mask in frame.get('masks',[])) for frame in custom['data']['frames'])

def test_compiler_parity_untouched_station_state(env):
    s,comp,a,_,settings=env;c=card(tiers=2)
    sem=semantic(c,c);sem.update(art=data_uri(s,a['id']),art_local_path=str(s.asset_path(a['id'])),set_symbol_source=data_uri(s,settings['symbols']['rare']),artist='Original Station Artist · Modified by ChatGPT')
    expected=native.build_one(sem,{},True)['data']
    apply_station_underframe_policy(expected,sem,'Scryfall selected printing')
    fit_set_symbol_to_bounds(expected,s.asset(settings['symbols']['rare']))
    expected['artSource']='/api/assets/'+a['id'];expected['setSymbolSource']='/api/assets/'+settings['symbols']['rare']
    actual=comp.compile_face(c,c,0,{},settings,a['id'],art_origin='Scryfall selected printing')['data']
    assert actual==expected

def test_flip_medallion_reserves_two_percent(env):
    s,comp,a,_,settings=env;c=flip_record()
    d=comp.compile_face(c,c['card_faces'][0],0,{},settings,a['id'])['data']
    sym=s.asset(settings['symbols']['rare']);right=d['setSymbolX']+sym['width']*d['setSymbolZoom']/d['width']
    bounds=d['setSymbolBounds'];assert bounds['x']==pytest.approx(d['text']['pt']['x']-.02-.01)
    # Native resetSetSymbol anchors in rounded canvas pixels.
    assert right==pytest.approx(round(bounds['x']*d['width'])/d['width'],abs=.6/d['width'])
    lower_left=d['text']['type2']['x']-d['text']['type2']['width']
    assert lower_left==pytest.approx(d['text']['pt2']['x']+.02+.01)
    assert 'v58' in GENERATION_VERSION

def test_no_homemade_station_badge_functions():
    assert all(not hasattr(native,name) for name in ['approx_rules_wrapped_lines','station_accent_markup','station_badge_src','apply_station_badges'])
