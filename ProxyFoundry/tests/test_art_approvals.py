"""Portable visual approvals reuse exact content without invalidating preparation."""
import copy,json
import pytest
from foundry.card_data import parse_document
from foundry.domain import ValidationError,uid
from test_github_data_refresh import env


@pytest.mark.parametrize('value',[True,'a'*64,['bad'],[None],['A'*64],['a'*64]*1001])
def test_art_approval_schema_rejects_invalid_hash_lists(value):
    with pytest.raises(ValidationError):
        parse_document(json.dumps({'version':1,'cards':[{'name':'Angel','accepted_art':value}]}).encode())


def approved(env):
    ws,deck,remote=env;deck=ws.prepare(deck['id']);card=deck['cards'][0];face=card['faces'][0]
    face['compiled']['crop']={'warning':True}
    deck=ws.store.put('decks',deck,deck['revision'])
    ws.store.render_put(face['compiled']['renderKey'],ws.store.asset(face['artOverride']))
    result=ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':face['id'],
        'renderKey':face['compiled']['renderKey'],'acceptWarning':True})
    return ws,ws.deck(result['id']),remote


def test_acceptance_saves_portable_data_without_changing_preparation_or_render(env):
    ws,deck,_=approved(env);face=deck['cards'][0]['faces'][0];comp=face['compiled']
    entries=parse_document(json.dumps({'version':1,'cards':deck['cardData']}).encode())
    assert entries==[{'name':'Angel','accepted_art':[comp['contentRenderKey']]}]
    assert face['acceptedWarningKey']==comp['renderKey'] and comp['render']
    assert face['preparationKey'] and deck['status']!='draft'


def test_github_approval_updates_and_revocation_do_not_recompile_cards(env,monkeypatch):
    ws,deck,remote=env;deck=ws.prepare(deck['id']);face=deck['cards'][0]['faces'][0]
    key=face['compiled']['renderKey'];content=face['compiled']['contentRenderKey'];preparation=face['preparationKey']
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Approval invalidated preparation'))
    remote.commit='b'*40;remote.document['cards']=[{'name':'Angel','accepted_art':[content]}]
    result=ws.prepare(deck['id']);face=result['cards'][0]['faces'][0]
    assert face['acceptedWarningKey']==key and face['preparationKey']==preparation
    remote.commit='c'*40;remote.document['cards'][0]['accepted_art']=[]
    assert not ws.prepare(deck['id'])['cards'][0]['faces'][0].get('acceptedWarningKey')
    remote.commit='d'*40;remote.document['cards'][0].pop('accepted_art')
    assert not ws.prepare(deck['id'])['cards'][0]['faces'][0].get('acceptedWarningKey')


def test_approval_survives_new_deck_ids_but_does_not_approve_changed_art(env):
    ws,original,remote=approved(env);old=original['cards'][0]['faces'][0]['compiled']
    remote.commit='b'*40;remote.document['cards']=original['cardData']
    deck=ws.new_deck('Reimport');cards=[]
    for source in original['cards']:
        card=copy.deepcopy(source);card['id']=uid()
        for face in card['faces']:
            face['id']=uid()
            for field in ('compiled','lastRender','preparationKey','preparedAt','acceptedArt','acceptedWarningKey'):face.pop(field,None)
        cards.append(card)
    deck=ws.store.put('decks',{**deck,'cards':cards,'settings':copy.deepcopy(original['settings'])},deck['revision'])
    result=ws.prepare(deck['id']);card=result['cards'][0];face=card['faces'][0];comp=face['compiled']
    assert comp['contentRenderKey']==old['contentRenderKey'] and comp['renderKey']!=old['renderKey']
    assert face['acceptedWarningKey']==comp['renderKey']
    ws.mutate_card(deck['id'],card['id'],{'revision':result['revision'],'faceId':face['id'],'fit':{'artZoom':1.5}})
    changed=ws.prepare(deck['id'])['cards'][0]['faces'][0]
    assert changed['compiled']['contentRenderKey']!=old['contentRenderKey']
    assert changed.get('acceptedWarningKey')!=changed['compiled']['renderKey']


def test_multiple_approved_art_versions_accumulate_for_the_same_face(env):
    ws,deck,_=approved(env);first=deck['cardData'][0]['accepted_art'][0]
    other=copy.deepcopy(deck['cards'][0]);other['id']=uid();face=other['faces'][0];face['id']=uid();face['acceptedArt']=[]
    face['compiled'].update(contentRenderKey='f'*64,renderKey='new-version')
    ws.store.render_put('new-version',ws.store.asset(face['artOverride']))
    deck['cards'].append(other);deck=ws.store.put('decks',deck,deck['revision'])
    result=ws.mutate_card(deck['id'],other['id'],{'revision':deck['revision'],'faceId':face['id'],
        'renderKey':'new-version','acceptWarning':True})
    assert result['cardData'][0]['accepted_art']==[first,'f'*64]