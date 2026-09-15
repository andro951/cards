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
    with pytest.raises(ValidationError,match='approved built-in pair'):Compiler(w.store).compile_face(sf,front,0,{},settings,a['id'])

def test_esika_approved_modal_pair_unchanged(tmp_path):
    w,a,settings=setup(tmp_path)
    front={'name':'Esika, God of the Tree','type_line':'Legendary Creature — God','colors':['G'],'power':'1','toughness':'4','mana_cost':'{1}{G}{G}','oracle_text':'Vigilance'}
    back={'name':'The Prismatic Bridge','type_line':'Legendary Enchantment','colors':['W','U','B','R','G'],'mana_cost':'{W}{U}{B}{R}{G}','oracle_text':'At the beginning of your upkeep, do a thing.'}
    sf={'name':front['name']+' // '+back['name'],'layout':'modal_dfc','rarity':'mythic','card_faces':[front,back]}
    x=Compiler(w.store).compile_face(sf,front,0,{},settings,a['id'])
    assert x['data']['text']['flipSideReminder']['text']=='{W}{U}{B}{R}{G}'
    y=Compiler(w.store).compile_face(sf,back,1,{},settings,a['id'])
    assert y['data']['text']['flipSideReminder']['text']=='{1}{G}{G}'
