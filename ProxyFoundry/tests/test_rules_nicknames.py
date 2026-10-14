import copy,io,json
from pathlib import Path
import pytest
from PIL import Image
from foundry import rules_nicknames as names
from foundry.compiler import Compiler
from foundry.workspace import Workspace
from foundry.storage import Store
from foundry.images import ingest_image


def formatter(real,nick,**extra):
    return names.RulesNames([{'name':real,'nickname':nick,**extra}])


@pytest.mark.parametrize('real,nick,text,expected',[
    ('Avacyn, Angel of Horror','Castiel, Angel of the Lord','Avacyn, Angel of Horror dies. Avacyn returns.','Castiel, Angel of the Lord dies. Castiel returns.'),
    ('Avacyn, Angel of Horror','Castiel','Avacyn, Angel of Horror dies. Avacyn returns.','Castiel dies. Castiel returns.'),
    ('Brutal Cathar','Garth, Monster Hunter','Brutal Cathar enters.','Garth enters.'),
    ('Brutal Cathar','Garth','Brutal Cathar enters.','Garth enters.'),
    ('Tezzeret the Seeker','Tony, The Inventor','Tezzeret the Seeker enters. Tezzeret untaps.','Tony enters. Tony untaps.'),
    ('Tezzeret the Seeker','The Inventor','Tezzeret the Seeker enters. Tezzeret untaps.','The Inventor enters. The Inventor untaps.'),
    ('Tezzeret, Cruel Captain','Tony, The Inventor','Tezzeret, Cruel Captain enters. Tezzeret untaps.','Tony, The Inventor enters. Tony untaps.'),
    ('Tezzeret, Cruel Captain','The Inventor','Tezzeret, Cruel Captain enters. Tezzeret untaps.','The Inventor enters. The Inventor untaps.'),
])
def test_comma_mapping_and_longest_match_priority(real,nick,text,expected):
    assert formatter(real,nick,types=['Planeswalker'],subtypes=['Tezzeret']).format(text)==expected


def test_word_boundaries_possessives_and_other_card_names():
    f=formatter('Avacyn, Angel of Horror','Castiel, Angel of the Lord')
    text="Avacynian isn't Avacyn. Avacyn's power and Avacyn’s toughness. Search for a card named Spirit of Avacyn. Avacyn, Angel of Hope stays."
    assert f.format(text)=="Avacynian isn't Castiel. Castiel's power and Castiel’s toughness. Search for a card named Spirit of Avacyn. Avacyn, Angel of Hope stays."


def test_unknown_longer_planeswalker_names_are_protected():
    f=formatter('Tezzeret the Seeker','The Inventor',types=['Planeswalker'],subtypes=['Tezzeret'])
    assert f.format('Tezzeret the Schemer stays. Tezzeret the Seeker untaps. Tezzeret, Cruel Captain stays.')=='Tezzeret the Schemer stays. The Inventor untaps. Tezzeret, Cruel Captain stays.'


def test_no_guessing_short_names_on_ordinary_cards():
    assert formatter('Brutal Cathar','Garth').format('Brutal Cathar enters. Brutal damage.')=='Garth enters. Brutal damage.'


def test_one_pass_does_not_replace_inserted_true_name_again():
    assert formatter('Tezzeret, Cruel Captain','Tezzeret, The Inventor').format('Tezzeret, Cruel Captain returns. Tezzeret draws.')=='Tezzeret, The Inventor returns. Tezzeret draws.'
    assert formatter('Test Card','New Test Card').format('Test Card dies. Test Card returns.')=='New Test Card dies. New Test Card returns.'


def test_already_formatted_rules_are_safe_when_editing_raw_card_data():
    f=formatter('Test Card','New Test Card, The Inventor')
    once=f.format('Test Card dies. Test Card returns.')
    assert once=='New Test Card dies. New Test Card returns.'
    assert f.format(once)==once


def test_commands_and_mana_symbols_are_not_names():
    assert formatter('T','Nick').format('{T}: T gains haste.')=='{T}: Nick gains haste.'


def test_known_unrenamed_sibling_protects_its_longer_name():
    f=names.RulesNames([{'name':'Avacyn, Angel of Horror','nickname':'Castiel'}, {'name':'Avacyn, Angel of Hope','nickname':''}])
    assert f.format('Avacyn, Angel of Horror or Avacyn, Angel of Hope.')=='Castiel or Avacyn, Angel of Hope.'


def test_face_nickname_map_uses_overrides_and_staged_values_including_clearing():
    sf={'card_faces':[{'name':'Front','flavor_name':'Old Front'},{'name':'Back','flavor_name':'Old Back'}]}
    saved=[{'index':0,'semanticOverrides':{'nickname':'Saved Front'}},{'index':1,'semanticOverrides':{'nickname':''}}]
    assert names.face_nicknames(sf,saved)=={'Front':'Saved Front','Back':''}
    assert names.face_nicknames(sf,saved,{'Back':{'nickname':'Staged Back'}})=={'Front':'Saved Front','Back':'Staged Back'}


def test_face_nickname_map_matches_semantic_parent_fallback():
    sf={'flavor_name':'Parent Nickname','card_faces':[{'name':'Front'},{'name':'Back','flavor_name':''}]}
    assert names.face_nicknames(sf)=={'Front':'Parent Nickname','Back':''}


@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path);out=io.BytesIO();Image.new('RGB',(500,700),'gray').save(out,'PNG')
    return store,Workspace(store).validate_settings({'artist':'Test Artist'}),ingest_image(store,out.getvalue())['id']


def fixture(name):
    return json.loads((Path(__file__).parent/'fixtures/godzilla_special'/(name+'.json')).read_text(encoding='utf-8'))


@pytest.mark.parametrize('key',['Tezzeret','Tezzeret-the-Seeker'])
def test_planeswalker_rules_change_but_canonical_metadata_and_true_name_stay(setup,key):
    store,settings,art=setup;sf=fixture(key);original=copy.deepcopy(sf)
    result=Compiler(store).compile_face(sf,sf,0,{'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'Tony, The Inventor'}},settings,art)
    rows=[v['text'] for k,v in result['data']['text'].items() if k.startswith('ability')]
    assert not any('Tezzeret' in t for t in rows)
    if key=='Tezzeret':assert 'Tony' in rows[0]
    assert result['data']['text']['title']['text']==sf['name']
    assert result['data']['text']['nickname']['text']=='Tony, The Inventor'
    assert sf==original and result['nicknameRulesVersion']==names.VERSION


@pytest.mark.parametrize('group',['standard','token','class','saga'])
def test_nonlegendary_rules_surfaces_receive_nickname_before_layout(setup,group):
    store,settings,art=setup
    oracle={'standard':'When Test Card enters, draw a card.','token':'When Test Card dies, draw a card.',
            'class':'When Test Card enters, draw a card.\n{1}: Level 2\nTest Card has vigilance.\n{2}: Level 3\nTest Card has flying.',
            'saga':'I — Test Card deals 1 damage to any target.\nII — Test Card deals 2 damage to any target.\nIII — Test Card deals 3 damage to any target.'}[group]
    sf={'name':'Test Card','layout':'token' if group=='token' else 'saga' if group=='saga' else 'normal',
        'type_line':{'standard':'Creature — Human','token':'Token Creature — Human','class':'Enchantment — Class','saga':'Enchantment — Saga'}[group],
        'mana_cost':'{2}{U}','colors':['U'],'rarity':'rare','oracle_text':oracle,'power':'2','toughness':'2',
        'flavor_text':'Test Card appears in flavor.'}
    original=copy.deepcopy(sf)
    data=Compiler(store).compile_face(sf,sf,0,{'semanticOverrides':{'nickname':'New Test Card'}},settings,art)['data']
    fields=[v['text'].partition('{flavor}')[0] for k,v in data['text'].items() if k=='rules' or k.startswith('ability') or k.endswith('c')]
    assert any('New Test Card' in t for t in fields)
    assert not any('New New' in t for t in fields)
    assert sf==original
    if group=='standard':assert 'Test Card appears in flavor.' in data['text']['rules']['text']


def test_double_faced_rules_use_both_saved_nicknames(setup):
    store,settings,art=setup;sf=fixture('Bruce-Banner');original=copy.deepcopy(sf)
    sf['card_faces'][0]['oracle_text']+='\nThe Incredible Hulk gains haste.'
    options={'templateOverride':'godzilla-card','faceNicknames':{'Bruce Banner':'Scientist, Ordinary Human','The Incredible Hulk':'Goliath'},
             'semanticOverrides':{'nickname':'Scientist, Ordinary Human'}}
    data=Compiler(store).compile_face(sf,sf['card_faces'][0],0,options,settings,art)['data']
    assert 'Transform Scientist.' in data['text']['rules']['text']
    assert 'Goliath gains haste.' in data['text']['rules']['text']
    assert original['card_faces'][0]['oracle_text'] in sf['card_faces'][0]['oracle_text']


def test_semantic_helper_is_not_applied_twice_and_handles_nested_rules():
    sem={'name':'Host','nickname':'New Host','oracle_text':'Host returns.',
         'prepared_spell':{'name':'Spell','nickname':'New Spell','oracle_text':'Host copies Spell.'}}
    names.apply_semantic(sem);names.apply_semantic(sem)
    assert sem['oracle_text']=='New Host returns.'
    assert sem['prepared_spell']['oracle_text']=='New Host copies New Spell.'


def test_raw_rule_fields_preserve_titles_flavor_and_original_snapshot():
    raw={'text':{'title':{'text':'Test Card'},'rules':{'text':'Test Card dies.{flavor}Test Card in flavor.'},
                 'ability0':{'text':'Test Card untaps.'},'level1c':{'text':'Test Card returns.'}}}
    data=copy.deepcopy(raw);names.format_raw_rules(data,formatter('Test Card','Nick'))
    assert data['text']['title']['text']=='Test Card'
    assert data['text']['rules']['text']=='Nick dies.{flavor}Test Card in flavor.'
    assert data['text']['ability0']['text']=='Nick untaps.'
    assert raw['text']['level1c']['text']=='Test Card returns.'


def test_token_conversion_does_not_restore_original_rules_name(setup):
    from foundry.compiler import semantic
    store,settings,art=setup
    sf={'name':'Test Card','type_line':'Creature — Human','layout':'normal','colors':['U'],
        'mana_cost':'{1}{U}','oracle_text':'When Test Card dies, draw a card.','power':'2','toughness':'2','rarity':'common'}
    options={'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'New Test Card'}}
    comp=Compiler(store).compile_face(sf,sf,0,options,settings,art)
    sem=semantic(sf,sf);sem['nickname']='New Test Card'
    converted=Workspace(store)._apply_token_spec(comp,{'token_key_suffix':' Copy'},art,'Copy Token',False,sem)
    assert 'New Test Card dies' in converted['data']['text']['rules']['text']
    assert 'New New' not in converted['data']['text']['rules']['text']


def test_cache_upgrade_is_scoped_to_nicknamed_cards_and_reuses_after_refresh(tmp_path,monkeypatch):
    from tests.test_preparation_cache import seeded
    ws,deck,_,_=seeded(tmp_path);sf=deck['cards'][0]['scryfall']
    sf['oracle_text']='When One Card enters, draw a card.'
    # The overridden rules avoid the fake metadata transport's original Oracle.
    deck['cards'][0]['faces'][0]['semanticOverrides']={'nickname':'New One Card','oracle_text':sf['oracle_text']}
    plain=copy.deepcopy(deck['cards'][0]);plain['id']='plain';plain['faces'][0]['id']='plain-face';plain['faces'][0]['semanticOverrides']={}
    deck['cards'].append(plain);ws.store.put('decks',deck,deck['revision'])
    prepared=ws.prepare(deck['id']);saved=ws.store.get('decks',deck['id'])
    assert prepared['cards'][0]['faces'][0]['compiled']['nicknameRulesVersion']==names.VERSION
    assert 'nicknameRulesVersion' not in prepared['cards'][1]['faces'][0]['compiled']
    # Simulate an older nicknamed compilation with otherwise matching inputs.
    saved['cards'][0]['faces'][0]['compiled'].pop('nicknameRulesVersion')
    ws.store.put('decks',saved,saved['revision'])
    assert ws.deck(deck['id'])['upgradeRequired']
    calls=[];compile_face=ws.compiler.compile_face
    def tracked(*args,**kwargs):calls.append(args[3]['semanticOverrides'].get('nickname'));return compile_face(*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    refreshed=ws.prepare(deck['id'])
    assert calls==['New One Card']
    assert 'New One Card enters' in refreshed['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Current nickname rules recompiled'))
    ws.prepare(deck['id'])


def test_workspace_staged_modal_preview_receives_sibling_nickname(setup,monkeypatch):
    store,settings,art=setup;ws=Workspace(store);sf=fixture('Bruce-Banner')
    sf['card_faces'][0]['oracle_text']+='\nThe Incredible Hulk gains haste.'
    c=ws.sources.entry(sf)
    for f in c['faces']:f['artOverride']=art
    deck=ws.new_deck('Two-face nickname preview');deck=store.put('decks',{**deck,'cards':[c],'settings':settings},deck['revision'])
    monkeypatch.setattr(ws,'_prepare_sources',lambda *a:{})
    plan=ws.template_preview_targets(deck['id'],'modal-front',settings,
        [{'name':'Bruce Banner','nickname':'Scientist'},{'name':'The Incredible Hulk','nickname':'Goliath'}],choices={'godzilla-card'})
    assert not plan['errors']
    rules=plan['targets'][0]['data']['text']['rules']['text']
    assert 'Transform Scientist.' in rules and 'Goliath gains haste.' in rules


@pytest.mark.parametrize('style',['token-classic','token-full-art','token-borderless','godzilla-card'])
@pytest.mark.parametrize('real,color,rules,pt',[('Angel','W','Flying','4'),('Germ','B','','0')])
def test_imported_token_nickname_survives_preparation_and_cache(setup,style,real,color,rules,pt,monkeypatch):
    store,settings,art=setup;ws=Workspace(store)
    sf={'name':real,'layout':'token','type_line':'Token Creature — '+real,'colors':[color],
        'mana_cost':'','oracle_text':rules,'power':pt,'toughness':pt,'rarity':'common'}
    card=ws.sources.entry(sf);card['faces'][0]['artOverride']=art
    settings['templateRules']['token']=style
    deck=ws.new_deck('Token nickname regression')
    deck=store.put('decks',{**deck,'cards':[card],'settings':settings,
        'cardData':[{'name':real,'nickname':'Test '+real}]},deck['revision'])
    first=ws.prepare(deck['id']);comp=first['cards'][0]['faces'][0]['compiled'];data=comp['data']
    assert data['text']['nickname']['text']=='Test '+real
    assert data['text']['title']['text']==real
    assert any('NicknameTitle' in f.get('src','') or 'TitleJoined' in f.get('src','') for f in data['frames'])
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Cached token recompiled'))
    cached=ws.prepare(deck['id'])['cards'][0]['faces'][0]['compiled']
    assert cached['renderKey']==comp['renderKey']
    assert cached['data']['text']['nickname']['text']=='Test '+real
