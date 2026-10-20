import copy

import pytest

from foundry.compiler import Compiler, center_short_token_rules, BUILTIN_TEMPLATE_VERSIONS, AUTO_TEMPLATE_VERSIONS
from foundry.workspace import Workspace
from test_pipeline import workspace, sf


@pytest.mark.parametrize('rules',['','Flying','{T}, Sacrifice this token: Add one mana of any color.'])
def test_automatic_token_uses_modern_full_art(workspace,rules):
    store,art,settings=workspace
    card={**sf('Token Creature — Bird',['U']),'name':'Bird','layout':'token','oracle_text':rules,'mana_cost':''}
    compiler=Compiler(store)
    automatic=compiler.compile_face(card,card,0,{},settings,art)
    modern=compiler.compile_face(card,card,0,{'templateOverride':'token-full-art'},settings,art)
    assert automatic['data']==modern['data']
    assert automatic['recipe']==modern['recipe']


@pytest.mark.parametrize('choice',[None,'auto'])
def test_automatic_conversion_uses_modern_full_art(workspace,choice):
    from foundry.compiler import semantic
    store,art,settings=workspace;ws=Workspace(store)
    card=sf('Creature — Angel',['W'])
    settings={**settings,'allCardsTokens':True,'templateRules':{} if choice is None else {'token':choice}}
    comp=Compiler(store).compile_face(card,card,0,{},settings,art)
    automatic=ws._apply_token_spec(copy.deepcopy(comp),ws._deck_token_spec(settings,comp),art,'Converted token',sem=semantic(card,card))
    modern=ws._apply_token_spec(copy.deepcopy(comp),{'token_frame_style':'token-full-art'},art,'Converted token',sem=semantic(card,card))
    individual=ws._apply_token_spec(copy.deepcopy(comp),{},art,'Converted token',sem=semantic(card,card))
    assert automatic['data']==modern['data']==individual['data']
    assert automatic['data']['version']=='tokenRegular'


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


@pytest.mark.parametrize('style',['token-full-art','token-classic','godzilla-card'])
@pytest.mark.parametrize('nickname',['','Lucifer, Fallen Archangel'])
@pytest.mark.parametrize('converted',[False,True])
def test_token_rules_and_flavor_fit_above_power_toughness(workspace,style,nickname,converted):
    from foundry.compiler import semantic
    store,art,settings=workspace
    card={**sf('Creature — Angel' if converted else 'Token Creature — Angel',['W']),
          'name':'Ob Nixilis, the Ascended','layout':'normal' if converted else 'token',
          'oracle_text':'Flying\nWhen this creature enters, destroy all tapped creatures your opponents control. You gain 1 life for each creature destroyed this way.\nAt the beginning of each end step, if you gained life this turn, create a 4/4 white Angel creature token with flying.',
          'flavor_text':'He never needed a throne to believe Heaven belonged to him.'}
    options={'templateOverride':'normal' if converted else style,'semanticOverrides':{'nickname':nickname}}
    comp=Compiler(store).compile_face(card,card,0,options,settings,art)
    if converted:
        sem=semantic(card,card);sem['nickname']=nickname
        comp=Workspace(store)._apply_token_spec(comp,{'token_frame_style':style if style.startswith('token-') else 'token-full-art'},art,'Converted token',False,sem)
    data=comp['data'];rules=data['text']['rules']
    badge=next(frame['bounds'] for frame in data['frames'] if 'Power/Toughness' in frame.get('name',''))
    assert rules['y']+rules['height']<=badge['y']-.008+1e-9
    assert card['flavor_text'] in rules['text']
    assert data['text']['pt']['text']=='2/3'


def test_noncreature_token_retains_full_rules_height(workspace):
    store,art,settings=workspace
    card={**sf('Token Artifact — Treasure',[]),'name':'Treasure','layout':'token','oracle_text':'Sacrifice this token: Add one mana of any color.'}
    card.pop('power');card.pop('toughness')
    data=Compiler(store).compile_face(card,card,0,{'templateOverride':'token-full-art'},settings,art)['data']
    assert data['text']['rules']['height']==.2048


def test_deck_wide_conversion_centers_short_rules_after_layout_rebuild(workspace):
    store,art,settings=workspace
    card={**sf('Creature — Angel',['W']),'name':'Angel','oracle_text':'Flying'}
    comp=Compiler(store).compile_face(card,card,0,{},settings,art)
    converted=Workspace(store)._apply_token_spec(comp,{'token_frame_style':'token-full-art'},art,'Deck-wide token',False)
    assert converted['data']['text']['rules']['align']=='center'


@pytest.mark.parametrize('style',[None,'token-classic','token-full-art','token-borderless'])
@pytest.mark.parametrize('nickname',['','Ring of Death'])
@pytest.mark.parametrize('legendary',[False,True])
def test_converted_noncreature_has_renderable_empty_pt(workspace,style,nickname,legendary):
    from foundry.compiler import semantic
    store,art,settings=workspace
    card={**sf('Artifact',[]),'name':'Sol Ring','oracle_text':'{T}: Add {C}{C}.'}
    card.pop('power',None);card.pop('toughness',None)
    comp=Compiler(store).compile_face(card,card,0,{'semanticOverrides':{'nickname':nickname}},settings,art)
    sem=semantic(card,card);sem['nickname']=nickname
    spec={'token_frame_style':style,'force_legendary':legendary,'nonlegendary':not legendary}
    result=Workspace(store)._apply_token_spec(comp,spec,art,'Converted token',False,sem)
    assert result['data']['text']['pt']['text']==''
    assert all(isinstance(field.get('text'),str) for field in result['data']['text'].values())


@pytest.mark.parametrize('pt',['2/3','*/1+*'])
def test_copy_token_preserves_existing_pt_and_explicit_override(workspace,pt):
    from foundry.legacy import tokens
    store,art,settings=workspace
    card=sf('Creature — Angel',['W'])
    comp=Compiler(store).compile_face(card,card,0,{},settings,art)
    comp['data']['text']['pt']['text']=pt
    source={'key':comp['name'],'data':comp['data']}
    assert tokens.build_token(source,{})['data']['text']['pt']['text']==pt
    assert tokens.build_token(source,{'power_toughness':'0/1'})['data']['text']['pt']['text']=='0/1'


def test_only_token_template_versions_are_advanced(workspace):
    store,_,_=workspace;compiler=Compiler(store)
    assert compiler.template_identity('token','auto')[1]==AUTO_TEMPLATE_VERSIONS['token']+3
    assert compiler.template_identity('standard','auto')[1]==AUTO_TEMPLATE_VERSIONS['standard']
    assert compiler.template_identity('token','godzilla-card')[1]==BUILTIN_TEMPLATE_VERSIONS['godzilla-card']+2
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
    def previous(group,choice,face=None):
        key,version,cache=current(group,choice,face)
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
