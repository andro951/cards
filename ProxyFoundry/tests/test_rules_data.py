import json

import pytest

from foundry.card_data import parse_document
from foundry.domain import ValidationError
from test_github_data_refresh import env


@pytest.mark.parametrize('text',['{T}: Draw a card.\nTest Card gains flying.',''])
def test_rules_data_schema_keeps_multiline_rules_and_explicit_reset(text):
    entries=parse_document(json.dumps({'version':1,'cards':[{'name':'Angel','oracle_text':text}]}).encode())
    assert entries==[{'name':'Angel','oracle_text':text}]


@pytest.mark.parametrize('text',[False,[], 'a'*20001,'Bad\x00rules'])
def test_rules_data_schema_rejects_invalid_override(text):
    with pytest.raises(ValidationError):parse_document(json.dumps({'version':1,'cards':[{'name':'Angel','oracle_text':text}]}).encode())


def test_github_rules_refresh_reset_and_removed_field_restore_official_rules(env):
    ws,deck,remote=env
    remote.document['cards']=[{'name':'Angel','nickname':'Fallen Seraph','oracle_text':'When Angel enters, draw a card.'}]
    first=ws.prepare(deck['id']);text=first['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
    assert 'When Fallen Seraph enters' in text
    assert first['cards'][0]['scryfall']['oracle_text']=='Flying'
    remote.commit='b'*40;remote.document['cards'][0]['oracle_text']=''
    second=ws.prepare(deck['id'])
    assert second['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']=='Flying'
    remote.commit='c'*40;remote.document['cards'][0]['oracle_text']='Vigilance'
    ws.prepare(deck['id']);remote.commit='d'*40;remote.document['cards'][0].pop('oracle_text')
    assert ws.prepare(deck['id'])['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']=='Flying'


def test_editor_rules_stay_on_the_selected_card_and_survive_local_preparation(env):
    ws,deck,_=env;deck['settings']['dataJsonSource']={'kind':'local','value':'data.json'}
    deck=ws.store.put('decks',deck,deck['revision']);card=deck['cards'][0];face=card['faces'][0]
    saved=ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':face['id'],
        'semanticOverrides':{'oracle_text':'Flying, vigilance'}})
    assert saved['cards'][0]['faces'][0]['rulesOverrideLocal']
    result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']=='Flying, vigilance'
    cleared=ws.mutate_card(deck['id'],card['id'],{'revision':result['revision'],'faceId':face['id'],'semanticOverrides':{}})
    assert 'oracle_text' not in cleared['cards'][0]['faces'][0]['semanticOverrides']
    assert ws.prepare(deck['id'])['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']=='Flying'


def test_rules_apply_to_one_face_without_mutating_source_or_other_face(env):
    ws,deck,_=env;card=deck['cards'][0]
    card['scryfall']['layout']='transform';card['scryfall']['card_faces']=[
        {'name':'Front','type_line':'Creature — Angel','oracle_text':'Flying','colors':['W'],'power':'4','toughness':'4'},
        {'name':'Back','type_line':'Creature — Angel','oracle_text':'Vigilance','colors':['W'],'power':'4','toughness':'4'}]
    entry=ws.sources.entry(card['scryfall']);deck['cards']=[entry]
    ws._apply_card_data(deck,[{'name':'Back','oracle_text':'Lifelink'}])
    assert 'semanticOverrides' not in entry['faces'][0]
    assert entry['faces'][1]['semanticOverrides']['oracle_text']=='Lifelink'
    assert card['scryfall']['card_faces'][1]['oracle_text']=='Vigilance'


def test_rules_survive_deck_wide_godzilla_token_rebuild(env):
    ws,deck,remote=env;deck['settings']['allCardsTokens']=True
    ws.store.put('decks',deck,deck['revision'])
    remote.document['cards']=[{'name':'Angel','oracle_text':'Lifelink'}]
    result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']=='Lifelink'


def test_remote_rule_update_replaces_saved_alias_before_later_setup_save(env):
    ws,deck,remote=env;card=deck['cards'][0]
    card['scryfall'].update(id='11111111-1111-4111-8111-111111111111',oracle_id='22222222-2222-4222-8222-222222222222')
    #Avoid fetching metadata: this regression only exercises source application.
    from foundry import github_data
    deck=ws.store.put('decks',deck,deck['revision'])
    remote.document['cards']=[{'name':'Angel','oracle_text':'Flying'}]
    deck=github_data.refresh(ws,deck)
    local=ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':card['faces'][0]['id'],
        'semanticOverrides':{'oracle_text':'Vigilance'}})
    local['cardData'].append({'name':'Angel','scryfall_id':card['scryfall']['id'],'oracle_text':'Vigilance'})
    remote.commit='b'*40;remote.document['cards'][0]['oracle_text']='Lifelink'
    updated=github_data.refresh(ws,local)
    saved=ws.save(deck['id'],{'revision':updated['revision'],'cardData':updated['cardData']})
    assert saved['cards'][0]['faces'][0]['semanticOverrides']['oracle_text']=='Lifelink'


@pytest.mark.parametrize('value',['',None])
def test_editor_empty_rules_normalize_to_reset_before_saving(env,value):
    ws,deck,_=env;card=deck['cards'][0];face=card['faces'][0]
    deck=ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':face['id'],
        'semanticOverrides':{'oracle_text':'Vigilance'}})
    reset=ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':face['id'],
        'semanticOverrides':{'oracle_text':value}})
    assert 'oracle_text' not in reset['cards'][0]['faces'][0]['semanticOverrides']
    assert reset['cards'][0]['faces'][0]['rulesOverrideLocal']


def test_unedited_setup_data_preserves_local_rules_but_new_import_replaces_them(env):
    ws,deck,_=env;card=deck['cards'][0];face=card['faces'][0]
    imported=ws.save(deck['id'],{'revision':deck['revision'],'cardData':[{'name':'Angel','oracle_text':'Flying'}]})
    local=ws.mutate_card(deck['id'],card['id'],{'revision':imported['revision'],'faceId':face['id'],
        'semanticOverrides':{'oracle_text':'Vigilance'}})
    saved=ws.save(deck['id'],{'revision':local['revision'],'cardData':local['cardData']})
    assert saved['cards'][0]['faces'][0]['semanticOverrides']['oracle_text']=='Vigilance'
    updated=ws.save(deck['id'],{'revision':saved['revision'],'cardData':[{'name':'Angel','oracle_text':'Lifelink'}]})
    assert updated['cards'][0]['faces'][0]['semanticOverrides']['oracle_text']=='Lifelink'
    assert not updated['cards'][0]['faces'][0].get('rulesOverrideLocal')
