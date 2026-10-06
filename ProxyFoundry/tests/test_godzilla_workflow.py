import io

import pytest
from PIL import Image

from foundry.compiler import Compiler
from foundry.domain import ValidationError
from foundry.github_setup import import_card_data_url,parse_card_data_json,validate_card_data_for_deck
from foundry.images import ingest_image
from foundry.storage import Store
from foundry.workspace import Workspace


def image(store):
    out=io.BytesIO()
    Image.new('RGB',(1000,1400),'#345678').save(out,'PNG')
    return ingest_image(store,out.getvalue())['id']


def card(name='Test Card',type_line='Creature — Human',colors=None,layout='normal'):
    value={'name':name,'type_line':type_line,'mana_cost':'{1}{B}',
           'oracle_text':'Deathtouch','flavor_text':'A line of flavor.',
           'colors':['B'] if colors is None else colors,'rarity':'rare',
           'power':'2','toughness':'3','layout':layout,'artist':'Artist'}
    return value


def test_direct_data_json_uses_existing_schema_and_checks_deck_names(tmp_path):
    ws=Workspace(Store(tmp_path))
    deck=ws.new_deck('Names')
    entry={'id':'card-id','name':'Test Card','quantity':1,'scryfall':card(),
           'faces':[{'id':'face-id','name':'Test Card','index':0}]}
    ws.store.put('decks',{**deck,'cards':[entry]},deck['revision'])
    raw=b'{"version":1,"cards":[{"name":"Test Card","nickname":"Reskin","flavor_text":"New flavor"}]}'
    assert validate_card_data_for_deck(ws,deck['id'],parse_card_data_json(raw))[0]['nickname']=='Reskin'
    with pytest.raises(ValidationError,match='not found'):
        validate_card_data_for_deck(ws,deck['id'],[{'name':'Missing','nickname':'X'}])

    class Remote:
        def fetch(self,url,**kwargs):
            assert url=='https://raw.githubusercontent.com/owner/repo/main/project/data.json'
            return raw,'application/json',{}
    ws.net=Remote()
    result=import_card_data_url(ws,{'deckId':deck['id'],
        'url':'https://github.com/owner/repo/blob/main/project/data.json'})
    assert result[0]['flavor_text']=='New flavor'
    with pytest.raises(ValidationError,match='named data.json'):
        import_card_data_url(ws,{'deckId':deck['id'],
            'url':'https://github.com/owner/repo/blob/main/project/other.json'})


@pytest.mark.parametrize('type_line,colors,choice,frame',[
    ('Creature — Human',['B'],'godzilla-card','m15NicknameFrameB.png'),
    ('Land',[],'godzilla-land','m15NicknameFrameL.png'),
    ('Creature — Human',[],'godzilla-card','m15NicknameFrameA.png'),
    ('Legendary Creature — Human',['B'],'godzilla-card','m15NicknameFrameB.png'),
])
def test_explicit_godzilla_uses_complete_frame_and_outlined_text(tmp_path,type_line,colors,choice,frame):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(type_line=type_line,colors=colors)
    if type_line=='Land':source.pop('power');source.pop('toughness')
    settings=ws.validate_settings({})
    result=Compiler(store).compile_face(
        source,source,0,{'templateOverride':choice,'semanticOverrides':{'nickname':'Alternate Name'}},
        settings,art,art_origin='computer folder')
    data=result['data']
    assert len(data['frames'])>=2
    assert any(item['src'].endswith(frame) and item['masks']==[] for item in data['frames'])
    if type_line=='Land':
        assert any(item['src'].endswith('TitleJoinedL.png') for item in data['frames'])
    elif not colors:
        assert any(item['src'].endswith('TitleJoinedA.png') for item in data['frames'])
    assert all(item.get('masks')==[] for item in data['frames'])
    if type_line!='Land':
        assert data['frames'][1]['src'].endswith('m15PTC.png' if not colors else 'm15NicknamePTB.png')
    assert data['text']['nickname']['text']=='Alternate Name'
    assert data['text']['title']['text']=='Test Card'
    for key in ('type','rules'):
        assert data['text'][key]['color']=='white'
        assert data['text'][key]['outlineColor']=='black'
        assert data['text'][key]['outlineWidth']>0


def test_token_conversion_adds_nickname_without_replacing_selected_frame(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store);settings=ws.validate_settings({})
    source=card()
    compiled=Compiler(store).compile_face(source,source,0,
        {'semanticOverrides':{'nickname':'Alternate Name'}},settings,art)
    converted=ws._apply_token_spec(compiled,{'output_key':'Test Card','token_key_suffix':''},
                                   art,'Deck-wide token',sem={**source,'types':['Creature'],
                                   'legendary':False,'nickname':'Alternate Name','name':'Test Card'})
    data=converted['data']
    assert data['frames'][0]['src'].endswith('/nickname/addons/m15NicknameTitleB.png')
    assert any('/img/frames/token/' in item['src'] for item in data['frames'][1:])
    assert not any('m15NicknameFrame' in item['src'] for item in data['frames'])
    assert data['text']['nickname']['text']=='Alternate Name'



@pytest.mark.parametrize('colors',[['W'],['U'],['B'],['R'],['G'],[],['W','U']])
@pytest.mark.parametrize('nickname',[False,True])
@pytest.mark.parametrize('convert',[False,True])
@pytest.mark.parametrize('rules',['','Flying'])
def test_modern_token_text_is_black_except_white_unoutlined_names(tmp_path,nickname,convert,colors,rules):
    store=Store(tmp_path);ws=Workspace(store);art=image(store);settings=ws.validate_settings({})
    source=card(type_line='Creature — Zombie',layout='token',colors=colors)
    source.update(oracle_text=rules,flavor_text='')
    if nickname:source['flavor_name']='Alternate Name'
    compiled=Compiler(store).compile_face(source,source,0,{'templateOverride':'token-full-art'},settings,art)
    if convert:
        compiled=ws._apply_token_spec(compiled,{'token_frame_style':'token-full-art','output_key':'Test Card','token_key_suffix':''},art,'Deck-wide token',sem={**source,'types':['Creature'],'legendary':False,'nickname':'Alternate Name' if nickname else ''})
    data=compiled['data']
    for key,field in data['text'].items():
        expected='white' if key=='title' and nickname else ('white' if key in {'title','nickname'} and colors!=['W'] else 'black')
        assert field['color']==expected
        assert field['outlineWidth']==0 and field['shadowX']==0 and field['shadowY']==0


@pytest.mark.parametrize('type_line,style',[('Artifact — Equipment','godzilla-card'),('Land','godzilla-land'),('Basic Land — Mountain','godzilla-land')])
def test_noncreature_godzilla_frame_has_an_empty_pt_text_box(tmp_path,type_line,style):
    store=Store(tmp_path);ws=Workspace(store);art=image(store);settings=ws.validate_settings({})
    source=card(type_line=type_line);source.pop('power');source.pop('toughness')
    if 'Land' in type_line:source.update(colors=[],mana_cost='',oracle_text='{T}: Add {R}.')
    data=Compiler(store).compile_face(source,source,0,{'templateOverride':style},settings,art)['data']
    assert data['version']=='m15Nickname'
    assert data['text']['pt']['text']==''
    assert all(isinstance(field['text'],str) for field in data['text'].values())
    assert not any('Power/Toughness' in frame['name'] for frame in data['frames'])
    if 'Basic' in type_line:
        assert data['text']['mana']['text']==''
        assert data['text']['type']['text']=='Basic Land - Mountain'
        assert '{R}' in data['text']['rules']['text']


def test_token_picker_groups_automatic_with_classic_and_keeps_modern_previews_distinct(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store);deck=ws.new_deck('Token previews')
    source=card(type_line='Token Creature — Bird',layout='token');source['oracle_text']='Flying'
    source['flavor_text']=''
    source['colors']=['U']
    entry={'id':'card-id','name':source['name'],'quantity':1,'scryfall':source,
           'faces':[{'id':'face-id','name':source['name'],'index':0}]}
    ws.store.put('decks',{**deck,'cards':[entry]},deck['revision'])
    settings=ws.validate_settings({'source':{'mode':'local','localFiles':{'test_card':art}}})
    plan=ws.template_preview_targets(deck['id'],'token',settings,[])
    assert not plan['errors']
    by_choice={target['choice']:target for target in plan['targets']}
    assert by_choice['auto']['choices']==['auto','token-classic']
    assert by_choice['auto']['data']['version']=='tokenTextlessM15'
    assert by_choice['token-full-art']['data']['version']=='tokenRegular'
    assert by_choice['token-borderless']['data']['version']=='tokenTextlessBorderless'


def test_preview_targets_use_a_card_from_requested_layout(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    deck=ws.new_deck('Examples')
    source=card()
    entry={'id':'card-id','name':source['name'],'quantity':1,'scryfall':source,
           'faces':[{'id':'face-id','name':source['name'],'index':0}]}
    ws.store.put('decks',{**deck,'cards':[entry]},deck['revision'])
    settings=ws.validate_settings({'source':{'mode':'local','localFiles':{'test_card':art}}})
    plan=ws.template_preview_targets(deck['id'],'standard',settings,
        [{'name':'Test Card','nickname':'Staged preview name'}])
    assert any(t['choice']=='godzilla-card' for t in plan['targets'])
    assert all(t['preview'] for t in plan['targets'])
    assert len({t['key'] for t in plan['targets']})==len(plan['targets'])
    godzilla=next(t for t in plan['targets'] if t['choice']=='godzilla-card')
    assert godzilla['data']['text']['nickname']['text']=='Staged preview name'


def test_commander_picker_keeps_distinct_frames_and_groups_matching_choices(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    deck=ws.new_deck('Commander preview')
    source=card('Syr Gwyn, Hero of Ashvale','Legendary Creature — Human Knight',['W','B','R'])
    source['mana_cost']='{3}{R}{W}{B}'
    entry={'id':'card-id','name':source['name'],'quantity':1,'scryfall':source,
           'faces':[{'id':'face-id','name':source['name'],'index':0}]}
    ws.store.put('decks',{**deck,'cards':[entry]},deck['revision'])
    settings=ws.validate_settings({'source':{'mode':'local','localFiles':{'syr_gwyn_hero_of_ashvale':art}}})
    plan=ws.template_preview_targets(deck['id'],'legendary',settings,
        [{'name':source['name'],'nickname':'Test Commander Nickname'}])
    assert len(plan['targets'])==3
    by_choice={target['choice']:target for target in plan['targets']}
    assert by_choice['auto']['choices']==['auto','normal']
    assert by_choice['auto']['data']['version']=='m15Regular'
    assert by_choice['legend-land']['data']['version']=='genericShowcase'
    assert by_choice['legend-land']['data']['text']['rules']['outlineColor']=='black'
    assert by_choice['godzilla-card']['data']['version']=='m15Nickname'
    assert all(target['data']['text']['nickname']['text']=='Test Commander Nickname'
               for target in plan['targets'])
    assert all(target['data']['text']['nickname']['x']+target['data']['text']['nickname']['width']<0.70
               for target in plan['targets'])


@pytest.mark.parametrize('choice,type_line',[('godzilla-card','Creature - Human'),('godzilla-land','Land')])
def test_godzilla_base_has_no_real_name_strip_without_nickname(tmp_path,choice,type_line):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(type_line=type_line)
    compiled=Compiler(store).compile_face(source,source,0,{'templateOverride':choice},ws.validate_settings({}),art)
    data=compiled['data']
    assert data['version']=='m15Nickname'
    assert 'nickname' not in data['text'] and data['text']['title']['text']==source['name']
    assert any('/proxy-foundry/godzilla/' in f['src'] for f in data['frames'])
    assert not any('/nickname/addons/' in f['src'] for f in data['frames'])


@pytest.mark.parametrize('choice',['auto','token-classic','token-full-art','token-borderless','godzilla-card'])
def test_nickname_is_only_a_topmost_addon_and_preserves_selected_token_frame(tmp_path,choice):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(type_line='Token Creature - Spirit',layout='token')
    settings=ws.validate_settings({});compiler=Compiler(store)
    plain=compiler.compile_face(source,source,0,{'templateOverride':choice},settings,art)['data']
    named=compiler.compile_face(source,source,0,{'templateOverride':choice,'semanticOverrides':{'nickname':'Ghost'}},settings,art)['data']
    assert named['version']==plain['version']
    if choice=='godzilla-card':
        assert named['frames'][0]['src'].endswith('TitleJoinedB.png')
        assert named['frames'][1:]==[f for f in plain['frames'] if '/godzilla/Title' not in f['src']]
    else:
        assert named['frames'][1:]==plain['frames']
    assert named['frames'][0]['src'].endswith('TitleJoinedB.png' if choice=='godzilla-card' else '/nickname/addons/m15NicknameTitleB.png')
    assert named['text']['nickname']['text']=='Ghost' and named['text']['title']['text']==source['name']
    for field in ('type','rules','pt'):
        assert named['text'][field]==plain['text'][field]


@pytest.mark.parametrize('nickname',['','Alternate Name'])
@pytest.mark.parametrize('has_pt',[False,True])
def test_godzilla_rules_and_flavor_reserve_visible_pt_space(tmp_path,nickname,has_pt):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(type_line='Legendary Creature — Human Warrior' if has_pt else 'Legendary Artifact')
    source['oracle_text']='When this permanent enters, look at the top seven cards of your library. You may reveal an Equipment or Vehicle card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nEquipment you control have equip {1}.\nVehicles you control have crew 1.'
    source['flavor_text']='Heaven had rules. Balthazar preferred souvenirs.'
    if not has_pt:
        source.pop('power');source.pop('toughness')
    data=Compiler(store).compile_face(source,source,0,
        {'templateOverride':'godzilla-card','semanticOverrides':{'nickname':nickname}},
        ws.validate_settings({}),art)['data']
    rules=data['text']['rules']
    assert source['flavor_text'] in rules['text']
    if has_pt:
        overlay=next(frame for frame in data['frames'] if 'Power/Toughness' in frame['name'])
        assert rules['y']+rules['height'] <= overlay['bounds']['y']-.008+1e-9
    else:
        assert rules['height']==.2875


@pytest.mark.parametrize('nickname',['','Custom land name'])
@pytest.mark.parametrize('legendary',[False,True])
def test_dual_land_godzilla_title_and_real_name_blend_land_colors(tmp_path,nickname,legendary):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(name='Bloodstained Mire',type_line=('Legendary ' if legendary else '')+'Land',colors=[])
    source.pop('power');source.pop('toughness')
    source.update(mana_cost='',oracle_text='{T}, Pay 1 life, Sacrifice this land: Search your library for a Swamp or Mountain card, put it onto the battlefield, then shuffle.')
    data=Compiler(store).compile_face(source,source,0,
        {'templateOverride':'godzilla-land','semanticOverrides':{'nickname':nickname}},
        ws.validate_settings({}),art)['data']
    kind='Crown' if legendary else 'Title'
    bars=[f for f in data['frames'] if '/godzilla/'+kind in f['src']]
    assert len(bars)==2
    assert [f['src'][-5] for f in bars]==['R','B']
    assert bars[0]['masks'][0]['name']=='Right Blend'
    assert bars[0]['bounds']==bars[1]['bounds']
    real=[f for f in data['frames'] if '/nickname/addons/' in f['src']]
    assert len(real)==0
    if nickname and legendary:
        assert all('/CrownJoined' in f['src'] for f in bars)
        assert data['frames'][:2]==bars
    if nickname and not legendary:
        assert all('/TitleJoined' in f['src'] for f in bars)
        assert data['frames'][:2]==bars
        assert bars[0]['bounds']['height']==pytest.approx(.1053)


@pytest.mark.parametrize('style',['auto','godzilla-card'])
def test_dual_nonland_real_name_bar_uses_same_color_blend(tmp_path,style):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(colors=['U','R'])
    data=Compiler(store).compile_face(source,source,0,
        {'templateOverride':style,'semanticOverrides':{'nickname':'Alternate'}},
        ws.validate_settings({}),art)['data']
    real=[f for f in data['frames'] if ('/godzilla/TitleJoined' if style=='godzilla-card' else '/nickname/addons/') in f['src']]
    assert [f['src'][-5] for f in real]==['R','U']
    assert real[0]['masks'][0]['name']=='Right Blend'


@pytest.mark.parametrize('colors,code',[(['W'],'W'),(['U'],'U'),(['B'],'B'),(['R'],'R'),(['G'],'G'),(['U','R'],'M'),([],'A'),([],'C')])
@pytest.mark.parametrize('convert',[False,True])
def test_godzilla_uses_selected_pt_family_and_unoutlined_numbers(tmp_path,colors,code,convert):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(type_line='Legendary Artifact Creature — Human' if code=='A' else 'Legendary Creature — Human',colors=colors)
    source['flavor_name']='Alternate Name'
    result=Compiler(store).compile_face(source,source,0,{'templateOverride':'godzilla-card'},ws.validate_settings({}),art)
    if convert:
        result=ws._apply_token_spec(result,{'output_key':'Test Card','token_key_suffix':''},art,'Token conversion',sem={**source,'types':['Artifact','Creature'] if code=='A' else ['Creature'],'legendary':True,'nickname':'Alternate Name'})
    data=result['data']
    box=next(frame for frame in data['frames'] if 'Power/Toughness' in frame['name'])
    normal=code in 'WAC'
    prefix='/img/frames/m15/regular/m15PT' if normal else '/img/frames/m15/nickname/m15NicknamePT'
    assert box['src']==prefix+code+'.png'
    pt=data['text']['pt']
    assert pt['color']==('black' if normal else 'white') and pt['outlineWidth']==0
    assert pt['shadowX']==0 and pt['shadowY']==0
    assert data['text']['rules']['y']+data['text']['rules']['height'] < box['bounds']['y']


@pytest.mark.parametrize('mana_cost',['','{W}','{3}{W}{W}','{W}{U}{B}{R}{G}'])
@pytest.mark.parametrize('style',['normal','auto'])
def test_normal_nickname_bar_keeps_full_width_with_mana(tmp_path,mana_cost,style):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(colors=['W']);source['mana_cost']=mana_cost
    data=Compiler(store).compile_face(source,source,0,
        {'templateOverride':style,'semanticOverrides':{'nickname':'Guardian'}},
        ws.validate_settings({}),art)['data']
    bar=data['frames'][0]['bounds']
    assert bar['width']==pytest.approx(.9014)
    assert bar['x']+bar['width']/2==pytest.approx(.5001)
    true_name=data['text']['title']
    assert true_name['x']+true_name['width']/2==pytest.approx(.5)
    assert true_name['align']=='center'


def test_nicknamed_nonlegendary_godzilla_uses_one_intact_joined_title(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store)
    source=card(colors=['W'])
    data=Compiler(store).compile_face(source,source,0,
        {'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'Garth'}},
        ws.validate_settings({}),art)['data']
    assert data['frames'][0]['src']=='/img/frames/proxy-foundry/godzilla/TitleJoinedW.png'
    assert data['frames'][0]['bounds']=={'x':.0494,'y':.0405,'width':.9014,'height':.1053}
    assert not any('/nickname/addons/' in f['src'] or '/godzilla/TitleW.png' in f['src'] for f in data['frames'])
