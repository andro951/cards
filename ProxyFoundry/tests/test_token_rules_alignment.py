import copy

import pytest

from foundry.compiler import Compiler, center_short_token_rules, BUILTIN_TEMPLATE_VERSIONS, AUTO_TEMPLATE_VERSIONS
from foundry.workspace import Workspace
from test_pipeline import workspace, sf


@pytest.mark.parametrize('style',['auto','token-classic','token-full-art','token-borderless','godzilla-card'])
@pytest.mark.parametrize('nickname',['','Fallen Seraph'])
def test_short_token_rules_center_without_changing_their_text_or_box(workspace,style,nickname):
    store,art,settings=workspace
    card={**sf('Token Creature — Angel',['W']),'name':'Angel','layout':'token','oracle_text':'Flying','mana_cost':''}
    data=Compiler(store).compile_face(card,card,0,{'templateOverride':style,'semanticOverrides':{'nickname':nickname}},settings,art)['data']
    assert data['text']['rules']['text']=='Flying'
    assert data['text']['rules']['align']=='center'
    field=copy.deepcopy(data['text']['rules']);center_short_token_rules(data)
    assert data['text']['rules']==field


@pytest.mark.parametrize('rules,flavor',[
    ('Flying, vigilance, lifelink',''),
    ('Flying\nVigilance',''),
    ('{T}, Sacrifice this token: Add one mana of any color.',''),
    ('Flying','This angel protects the innocent.'),
])
def test_long_token_rules_and_flavor_keep_existing_alignment(workspace,rules,flavor):
    store,art,settings=workspace
    card={**sf('Token Creature — Angel',['W']),'name':'Angel','layout':'token','oracle_text':rules,'flavor_text':flavor}
    data=Compiler(store).compile_face(card,card,0,{'templateOverride':'token-full-art'},settings,art)['data']
    assert data['text']['rules'].get('align','left')=='left'


def test_deck_wide_conversion_centers_short_rules_after_layout_rebuild(workspace):
    store,art,settings=workspace
    card={**sf('Creature — Angel',['W']),'name':'Angel','oracle_text':'Flying'}
    comp=Compiler(store).compile_face(card,card,0,{},settings,art)
    converted=Workspace(store)._apply_token_spec(comp,{'token_frame_style':'token-full-art'},art,'Deck-wide token',False)
    assert converted['data']['text']['rules']['align']=='center'


def test_only_token_template_versions_are_advanced(workspace):
    store,_,_=workspace;compiler=Compiler(store)
    assert compiler.template_identity('token','auto')[1]==AUTO_TEMPLATE_VERSIONS['token']+1
    assert compiler.template_identity('standard','auto')[1]==AUTO_TEMPLATE_VERSIONS['standard']
    assert compiler.template_identity('token','godzilla-card')[1]==BUILTIN_TEMPLATE_VERSIONS['godzilla-card']+1
    assert compiler.template_identity('standard','godzilla-card')[1]==BUILTIN_TEMPLATE_VERSIONS['godzilla-card']


@pytest.mark.parametrize('converted',[False,True])
def test_previous_token_preparation_is_refreshed_once(workspace,monkeypatch,converted):
    store,art,settings=workspace;ws=Workspace(store)
    settings={**settings,'allCardsTokens':converted,'templateRules':{'token':'token-full-art'}}
    card=sf('Creature — Angel' if converted else 'Token Creature — Angel',['W'])
    card.pop('id');card.update(name='Angel',layout='normal' if converted else 'token',oracle_text='Flying')
    entry=ws.sources.entry(card);entry['faces'][0]['artOverride']=art
    deck=ws.new_deck('Token alignment cache')
    store.put('decks',{**deck,'cards':[entry],'settings':settings},deck['revision'])
    current=ws.compiler.template_identity
    def previous(group,choice):
        key,version,cache=current(group,choice)
        return (key,version-1,cache-1) if group=='token' else (key,version,cache)
    monkeypatch.setattr(ws.compiler,'template_identity',previous)
    old=ws.prepare(deck['id'])['cards'][0]['faces'][0]['compiled']['renderKey']
    monkeypatch.setattr(ws.compiler,'template_identity',current)
    compile_face=ws.compiler.compile_face;calls=[]
    def tracked(*a,**k):calls.append(True);return compile_face(*a,**k)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    refreshed=ws.prepare(deck['id'])['cards'][0]['faces'][0]['compiled']
    assert calls==[True]
    if not converted:assert refreshed['renderKey']!=old
    assert refreshed['data']['text']['rules']['align']=='center'
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Current token recompiled'))
    ws.prepare(deck['id'])
