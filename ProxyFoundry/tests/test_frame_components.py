"""Final compiler coverage for native components omitted from the shared pass."""
import copy,itertools
import pytest
from foundry.compiler import apply_universal_frame_color_treatment,semantic
from tests.test_v54_integration import env,sf,flip_record
from tests.test_class_and_enchantment_land import cleric_class
from tests.test_battle import invasion_of_ikoria
from tests.test_v58_station import card as station

KINDS=('walker','tall-walker','class','battle','flip','station','godzilla','godzilla-land')
def example(kind,colors):
    override={}
    if kind in ('walker','tall-walker'):
        rules='+1: Draw a card.\n-2: Return target creature.\n-7: Draw seven cards.'
        if kind=='tall-walker':rules='+2: Scry 2.\n'+rules
        c=sf(kind,type_line='Legendary Planeswalker — Tester',oracle_text=rules,loyalty='4')
    elif kind=='class':c=cleric_class()
    elif kind=='battle':c=invasion_of_ikoria()
    elif kind=='flip':c=flip_record()
    elif kind=='station':c=sf(**station(colors=colors))
    else:
        c=sf(kind,type_line='Legendary Land' if kind=='godzilla-land' else 'Legendary Creature — Elf',oracle_text='{T}: Add '+ ' or '.join('{'+x+'}' for x in colors)+'.' if kind=='godzilla-land' else 'Vigilance')
        override={'templateOverride':'godzilla-land' if kind=='godzilla-land' else 'godzilla-card'}
    c['colors']=list(colors);c['mana_cost']='{2}'+''.join('{'+x+'}' for x in colors)
    face=c.get('card_faces',[c])[0];face['colors']=list(colors);face['mana_cost']=c['mana_cost']
    return c,face,override

@pytest.mark.parametrize('colors',list(itertools.combinations('WUBRG',2)))
@pytest.mark.parametrize('kind',KINDS)
def test_final_native_component_matrix(env,kind,colors):
    w,_,art,settings=env;c,face,override=example(kind,colors)
    data=w.compiler.compile_face(c,face,0,override,settings,art['id'])['data']
    pins=[f for f in data['frames'] if any(m.get('name')=='Pinline' for m in f.get('masks',[]))]
    assert pins and all(f['src'].startswith('data:image/svg+xml') for f in pins)
    # A second shared pass cannot stack duplicate overlays/crowns.
    before=copy.deepcopy(data)
    apply_universal_frame_color_treatment(data,semantic(c,face))
    assert data==before
    if kind.startswith('godzilla'):
        crowns=[f for f in data['frames'] if '/godzilla/Crown' in f.get('src','')]
        assert len(crowns)==2
        assert crowns[0]['masks'][0]['name']=='Right Blend'
        assert any('/nickname/m15NicknameFrame' in f.get('src','') and not f['masks'] for f in data['frames'])
    elif kind in ('walker','tall-walker','class','battle','flip'):
        assert any(not f.get('masks') and not f['src'].startswith('data:') for f in data['frames'])


def test_station_colored_bars_are_above_complete_station_overlay(env):
    w,_,art,settings=env;c,face,override=example('station',['U','R'])
    frames=w.compiler.compile_face(c,face,0,override,settings,art['id'])['data']['frames']
    base=next(i for i,f in enumerate(frames) if f.get('src')=='/img/frames/station/a.png' and not f.get('masks'))
    for effect in ('Title','Type','Rules'):
        assert any(i<base and f.get('src')=='/img/frames/station/m.png' and any(m.get('name')==effect for m in f.get('masks',[])) for i,f in enumerate(frames))


def test_colorless_prepare_host_keeps_independent_blue_spell(env):
    w,_,art,settings=env
    host={'name':'Colorless Host','type_line':'Creature — Eldrazi','colors':[],'mana_cost':'{3}','oracle_text':'This creature becomes prepared.','power':'1','toughness':'1'}
    spell={'name':'Blue Spell','type_line':'Instant','mana_cost':'{U}','oracle_text':'Draw a card.'}
    c=sf('Colorless Host // Blue Spell',layout='prepare',colors=[],card_faces=[host,spell])
    data=w.compiler.compile_face(c,host,0,{},settings,art['id'])['data']
    spells=[f for f in data['frames'] if any('Prepare Spell' in m.get('name','') for m in f.get('masks',[]))]
    assert spells and all(f['src']=='/img/frames/prepare/regular/u.png' for f in spells)


@pytest.mark.parametrize('family',['modal/regular','modal/regular/back'])
def test_modal_boxes_recolor_without_changing_opposite_face_reminder(family):
    source='/img/frames/'+family+'/a.png'
    data={'frames':[{'src':source,'masks':[{'name':n,'src':'/'+n+'.png'} for n in ('Frame','Title','Type','Rules','Flipside')]}]}
    apply_universal_frame_color_treatment(data,{'types':['Artifact'],'colors':['U']})
    structural=next(f for f in data['frames'] if any(m['name']=='Flipside' for m in f['masks']))
    assert structural['src']==source
    boxes=next(f for f in data['frames'] if any(m['name']=='Title' for m in f['masks']))
    assert boxes['src']=='/img/frames/'+family+'/u.png'

@pytest.mark.parametrize('nickname',['','Custom Name'])
@pytest.mark.parametrize('legendary',[False,True])
def test_godzilla_final_pass_keeps_nickname_on_top(env,nickname,legendary):
    w,_,art,settings=env;c,face,override=example('godzilla',['U','R'])
    c['type_line']=('Legendary ' if legendary else '')+'Creature — Elf';c['flavor_name']=nickname
    frames=w.compiler.compile_face(c,c,0,override,settings,art['id'])['data']['frames']
    crowns=[f for f in frames if '/godzilla/Crown' in f.get('src','')]
    assert len(crowns)==(2 if legendary else 0)
    if nickname:
        assert '/godzilla/CrownJoined' in frames[0]['src'] if legendary else frames[0]['name']=='Nickname Title'


def test_colorless_prepared_spell_does_not_inherit_colored_host():
    data={'frames':[{'src':'/img/frames/prepare/regular/u.png','masks':[{'name':'Prepare Spell','src':'/spell.png'}]}]}
    apply_universal_frame_color_treatment(data,{'types':['Creature'],'colors':['U'],'prepared_spell':{'types':['Instant'],'colors':[]}})
    assert data['frames'][0]['src']=='/img/frames/prepare/regular/a.png'


def test_neutral_station_land_keeps_existing_native_neutral_asset():
    data={'frames':[{'src':'/img/frames/station/a.png','masks':[]}]}
    apply_universal_frame_color_treatment(data,{'types':['Land'],'colors':[],'land_colors':[]})
    assert data['frames']==[{'src':'/img/frames/station/a.png','masks':[]}]
