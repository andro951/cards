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
        assert any(item['src'].endswith('m15NicknameTitleL.png') for item in data['frames'])
    elif not colors:
        assert any(item['src'].endswith('m15NicknameTitleA.png') for item in data['frames'])
    assert all(item.get('masks')==[] for item in data['frames'])
    assert data['text']['nickname']['text']=='Alternate Name'
    assert data['text']['title']['text']=='Test Card'
    for key in ('type','rules'):
        assert data['text'][key]['color']=='white'
        assert data['text'][key]['outlineColor']=='black'
        assert data['text'][key]['outlineWidth']>0


def test_token_conversion_restores_full_nickname_frame_after_vendor_replaces_layers(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store);settings=ws.validate_settings({})
    source=card()
    compiled=Compiler(store).compile_face(source,source,0,
        {'semanticOverrides':{'nickname':'Alternate Name'}},settings,art)
    converted=ws._apply_token_spec(compiled,{'output_key':'Test Card','token_key_suffix':''},
                                   art,'Deck-wide token',sem={**source,'types':['Creature'],
                                   'legendary':False,'nickname':'Alternate Name','name':'Test Card'})
    data=converted['data']
    assert any(item['src'].endswith('m15NicknameFrameB.png') for item in data['frames'])
    assert all(item.get('masks')==[] for item in data['frames'])
    assert data['artBounds']['height']>.9
    assert data['text']['nickname']['text']=='Alternate Name'
    for key in ('title','type','rules'):
        assert data['text'][key]['color']=='white'
        assert data['text'][key]['outlineWidth']>0


def test_native_token_text_gets_white_black_outline(tmp_path):
    store=Store(tmp_path);ws=Workspace(store);art=image(store);settings=ws.validate_settings({})
    source=card(type_line='Creature — Zombie',layout='token')
    data=Compiler(store).compile_face(source,source,0,{},settings,art)['data']
    for key in ('type','rules'):
        assert data['text'][key]['color']=='white'
        assert data['text'][key]['outlineColor']=='black'


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
