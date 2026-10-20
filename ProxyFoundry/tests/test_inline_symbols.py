import copy
import pytest
from foundry.inline_symbols import has_untap_alias,normalize_untap_aliases
from test_preparation_cache import seeded


def test_untap_translation_preserves_other_symbols_and_handles_all_text_fields():
    data={'text':{'rules':{'text':'{U}, {Q}: Move a counter. ({Q} is the untap symbol.)'},
                  'flavor':{'text':'{q}'},'ability0':{'text':'{T}: Add {C}.'}},
          'bottomInfo':{'note':{'text':'{Q}'}},'frames':[{'name':'Unchanged'}]}
    assert has_untap_alias(data)
    normalize_untap_aliases(data)
    assert data['text']['rules']['text']=='{U}, {untap}: Move a counter. ({untap} is the untap symbol.)'
    assert data['text']['flavor']['text']=='{untap}'
    assert data['bottomInfo']['note']['text']=='{untap}'
    assert data['text']['ability0']['text']=='{T}: Add {C}.'
    assert not has_untap_alias(data)
    snapshot=copy.deepcopy(data);normalize_untap_aliases(data);assert data==snapshot


def test_untap_refresh_recompiles_only_affected_card_and_then_reuses_cache(tmp_path,monkeypatch):
    ws,deck,_,_=seeded(tmp_path);prepared=ws.prepare(deck['id'])
    #A saved override also needs the fix, independently of the Scryfall text.
    prepared['cards']=[{**copy.deepcopy(prepared['cards'][0]),'id':str(i)} for i in range(2)]
    changed=prepared['cards'][0]['faces'][0]
    changed['semanticOverrides']={'oracle_text':'{U}, {Q}: Move a counter. ({Q} is the untap symbol.)'}
    ws.store.put('decks',prepared,prepared['revision']);prepared=ws.prepare(deck['id'])
    fresh=prepared['cards'][0]['faces'][0]['compiled']['renderKey']
    #Simulate an earlier compiled card that still prints the raw token.
    old=ws.store.get('decks',deck['id'])
    old['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']=changed['semanticOverrides']['oracle_text']
    old['cards'][0]['faces'][0]['compiled']['renderKey']='old-untap-render'
    ws.store.put('decks',old,old['revision'])
    assert ws.deck(deck['id'])['status']=='draft'
    calls=[];compile_face=ws.compiler.compile_face
    def tracked(sf,*args,**kwargs):calls.append(sf['name']);return compile_face(sf,*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    updated=ws.prepare(deck['id'])
    assert len(calls)==1
    assert updated['cards'][0]['faces'][0]['compiled']['renderKey']==fresh
    assert updated['cards'][1]['faces'][0]['compiled']['renderKey']==prepared['cards'][1]['faces'][0]['compiled']['renderKey']
    assert '{Q}' in updated['cards'][0]['faces'][0]['semanticOverrides']['oracle_text']
    calls.clear();ws.prepare(deck['id']);assert calls==[]


@pytest.mark.parametrize('conversion',['none','copy-token','deck-tokens'])
def test_compiler_and_token_conversions_use_native_untap_token(tmp_path,monkeypatch,conversion):
    ws,deck,_,_=seeded(tmp_path)
    face=deck['cards'][0]['faces'][0]
    face['semanticOverrides']={'oracle_text':'{U}, {Q}: Move a counter. ({Q} is the untap symbol.)'}
    if conversion=='copy-token':deck['cards'][0]['tokenSpec']={}
    if conversion=='deck-tokens':deck['settings']['allCardsTokens']=True
    ws.store.put('decks',deck,deck['revision']);prepared=ws.prepare(deck['id'])
    face=prepared['cards'][0]['faces'][0]
    assert not face.get('error')
    assert face['compiled']['data']['text']['rules']['text'].count('{untap}')==2
    assert not has_untap_alias(face['compiled']['data'])
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Unchanged untap face recompiled'))
    ws.prepare(deck['id'])
