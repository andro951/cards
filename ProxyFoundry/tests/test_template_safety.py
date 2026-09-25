import io
import pytest
from PIL import Image
from foundry.domain import ValidationError
from foundry.workspace import Workspace
from foundry.storage import Store
from foundry.compiler import Compiler
from foundry.images import ingest_image,rarity_variants

def setup(tmp_path):
    s=Store(tmp_path);w=Workspace(s);b=io.BytesIO();Image.new('RGB',(900,650),'#656595').save(b,'PNG');a=ingest_image(s,b.getvalue())
    return w,a,{'symbols':rarity_variants(s,a['id'])}
def test_template_edit_and_delete_invalidates_only_its_decks(tmp_path):
    w,art,settings=setup(tmp_path)
    t=w.save_template({'name':'Test','data':w.template_seed(),'groups':['standard']})
    d=w.new_deck('Uses template');other=w.new_deck('Unrelated')
    d=w.store.put('decks',{**d,'status':'prepared','settings':{**d['settings'],'templateRules':{'standard':t['id']}}},d['revision'])
    revision=d['revision'];other_revision=other['revision'];t=w.save_template({**t,'name':'Renamed'})
    assert w.deck(d['id'])['status']=='draft' and w.deck(d['id'])['revision']==revision+1
    assert w.deck(other['id'])['revision']==other_revision
    d=w.store.get('decks',d['id']);w.store.put('decks',{**d,'status':'prepared'},d['revision'])
    w.delete_template(t['id'],t['revision'])
    assert w.deck(d['id'])['status']=='draft'
    assert w.store.get('templates',t['id']) is None

def test_land_seed_is_not_a_basic_land_recipe(tmp_path):
    w,_,_=setup(tmp_path);seed=w.template_seed('land')
    assert seed['version']!='eoeBasics'
    assert not any('Forest Symbol' in f.get('name','') for f in seed['frames'])
    assert 'rules' in seed['text']

def test_unapproved_modal_dfc_fails_closed(tmp_path):
    w,a,settings=setup(tmp_path)
    front={'name':'Other DFC','type_line':'Creature — Wizard','colors':['G'],'power':'2','toughness':'3','mana_cost':'{2}{G}','oracle_text':'Vigilance'}
    back={'name':'Other Reverse','type_line':'Land','mana_cost':'','oracle_text':'{T}: Add {G}.'}
    sf={'name':'Other DFC // Other Reverse','layout':'modal_dfc','rarity':'rare','card_faces':[front,back]}
    with pytest.raises(ValidationError,match='Approved built-in pairs'):Compiler(w.store).compile_face(sf,front,0,{},settings,a['id'])

def test_esika_approved_modal_pair_unchanged(tmp_path):
    w,a,settings=setup(tmp_path)
    front={'name':'Esika, God of the Tree','type_line':'Legendary Creature — God','colors':['G'],'power':'1','toughness':'4','mana_cost':'{1}{G}{G}','oracle_text':'Vigilance'}
    back={'name':'The Prismatic Bridge','type_line':'Legendary Enchantment','colors':['W','U','B','R','G'],'mana_cost':'{W}{U}{B}{R}{G}','oracle_text':'At the beginning of your upkeep, do a thing.'}
    sf={'name':front['name']+' // '+back['name'],'layout':'modal_dfc','rarity':'mythic','card_faces':[front,back]}
    x=Compiler(w.store).compile_face(sf,front,0,{},settings,a['id'])
    assert x['data']['text']['flipSideReminder']['text']=='{W}{U}{B}{R}{G}'
    assert x['data']['text']['flipsideType']['text']=='Enchantment'
    y=Compiler(w.store).compile_face(sf,back,1,{},settings,a['id'])
    assert y['data']['text']['flipSideReminder']['text']=='{1}{G}{G}'
    assert y['data']['text']['flipsideType']['text']=='God'
    assert x['data']['text']['flipsideType']['width'] < y['data']['text']['flipsideType']['width']


def test_bruce_banner_incredible_hulk_modal_pair_uses_its_own_semantics(tmp_path):
    w,a,settings=setup(tmp_path)
    front={
        'name':'Bruce Banner',
        'type_line':'Legendary Creature — Human Scientist Hero',
        'colors':['U'],'power':'1','toughness':'1','mana_cost':'{U}',
        'oracle_text':'{X}{X}, {T}: Draw X cards. Activate only as a sorcery.\n{2}{R}{R}{G}{G}: Transform Bruce Banner. Activate only as a sorcery.',
    }
    back={
        'name':'The Incredible Hulk',
        'type_line':'Legendary Creature — Gamma Berserker Hero',
        'colors':['R','G'],'power':'8','toughness':'8','mana_cost':'{2}{R}{R}{G}{G}',
        'oracle_text':"Reach, trample\nEnrage — Whenever The Incredible Hulk is dealt damage, put a +1/+1 counter on him. If he's attacking, untap him and there is an additional combat phase after this phase.",
    }
    sf={
        'name':'Bruce Banner // The Incredible Hulk',
        'layout':'modal_dfc','rarity':'mythic','card_faces':[front,back],
    }

    front_result=Compiler(w.store).compile_face(sf,front,0,{},settings,a['id'])
    back_result=Compiler(w.store).compile_face(sf,back,1,{},settings,a['id'])
    assert front_result['group']=='modal-front' and front_result['recipe']=='modal_dfc_front'
    assert back_result['group']=='modal-back' and back_result['recipe']=='modal_dfc_back'

    front_data=front_result['data'];back_data=back_result['data']
    assert front_data['text']['flipSideReminder']['text']=='{2}{R}{R}{G}{G}'
    assert front_data['text']['flipsideType']['text']=='8/8 Creature'
    assert back_data['text']['flipSideReminder']['text']=='{U}'
    assert back_data['text']['flipsideType']['text']=='1/1 Creature'
    assert front_data['text']['flipsideType']['width'] < back_data['text']['flipsideType']['width']
    assert front_data['text']['pt']['text']=='1/1'
    assert back_data['text']['pt']['text']=='8/8'

    def layer(data,mask_name):
        return next(
            frame for frame in data['frames']
            if any(mask.get('name')==mask_name for mask in frame.get('masks',[]) if isinstance(mask,dict))
        )

    # Bruce is blue; his opposite-face strip previews the R/G multicolor Hulk.
    assert layer(front_data,'Frame')['src']=='/img/frames/modal/regular/u.png'
    assert layer(front_data,'Flipside')['src']=='/img/frames/modal/regular/m.png'
    assert any(frame.get('src')=='/img/frames/m15/regular/m15PTU.png' for frame in front_data['frames'])

    # Hulk is R/G: structural body is multicolor, the reminder strip previews blue Bruce,
    # and the universal two-color policy supplies the R/G gradient pinline/crown treatment.
    assert layer(back_data,'Frame')['src']=='/img/frames/modal/regular/back/m.png'
    assert layer(back_data,'Flipside')['src']=='/img/frames/modal/regular/back/u.png'
    assert any(frame.get('src')=='/img/frames/m15/regular/m15PTM.png' for frame in back_data['frames'])
    assert layer(back_data,'Pinline')['src'].startswith('data:image/svg+xml;utf8,')


def test_sowing_mycospawn_uses_green_devoid_frame(tmp_path):
    w,a,settings=setup(tmp_path)
    card={
        'name':'Sowing Mycospawn',
        'layout':'normal',
        'rarity':'rare',
        'type_line':'Creature — Eldrazi Fungus',
        'mana_cost':'{3}{G}',
        'colors':[],
        'keywords':['Devoid','Kicker'],
        'oracle_text':'Devoid (This card has no color.)\nKicker {1}{C}\nWhen you cast this spell, search your library for a land card, put it onto the battlefield, then shuffle.',
        'power':'3','toughness':'3',
        'artist':'Slawomir Maniak',
    }
    result=Compiler(w.store).compile_face(card,card,0,{},settings,a['id'])
    data=result['data']
    assert result['group']=='standard'
    assert data['version']=='m15Devoid'
    assert data['artBounds']=={'x':0.04,'y':0.1039,'width':0.92,'height':0.9229}
    assert any(frame.get('src')=='/img/frames/m15/devoid/m15DevoidFrameG.png' for frame in data['frames'])
    assert any(frame.get('src')=='/img/frames/m15/devoid/m15DevoidPT.png' for frame in data['frames'])
    assert result['artist']=='Slawomir Maniak'


def test_colorless_eldrazi_without_devoid_keeps_normal_frame_family(tmp_path):
    w,a,settings=setup(tmp_path)
    card={
        'name':'Plain Eldrazi',
        'layout':'normal','rarity':'rare',
        'type_line':'Creature — Eldrazi',
        'mana_cost':'{5}','colors':[],'keywords':[],
        'oracle_text':'Trample','power':'5','toughness':'5',
    }
    data=Compiler(w.store).compile_face(card,card,0,{},settings,a['id'])['data']
    assert data.get('version')!='m15Devoid'
    assert not any('/m15/devoid/' in str(frame.get('src') or '') for frame in data['frames'])
