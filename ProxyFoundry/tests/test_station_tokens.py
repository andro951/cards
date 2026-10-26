import copy

import pytest

from foundry.domain import ValidationError
from foundry.workspace import Workspace
from test_pipeline import workspace
from tests.test_v58_station import card


@pytest.mark.parametrize('scope',['card','deck','both'])
@pytest.mark.parametrize('style',['token-classic','token-full-art','token-borderless'])
def test_station_converts_without_aborting_deck_and_retains_all_rules(workspace,scope,style):
    store,art,settings=workspace;ws=Workspace(store)
    station=card();station['name']='The Seriema'
    entry=ws.sources.entry(station);entry['faces'][0]['artOverride']=art
    if scope in {'card','both'}:entry['tokenSpec']={'nonlegendary':True}
    following=ws.sources.entry({**station,'name':'Following card','type_line':'Artifact — Vehicle','oracle_text':'Vigilance'})
    following['faces'][0]['artOverride']=art
    deck=ws.new_deck('Station conversion regression')
    deck['settings']=ws.validate_settings({**settings,'allCardsTokens':scope in {'deck','both'},
        'templateRules':{'token':style}})
    deck['cards']=[entry,following];store.put('decks',deck,deck['revision'])
    prepared=ws.prepare(deck['id'])
    for converted in prepared['cards']:
        face=converted['faces'][0]
        assert not face.get('error')
        assert face['compiled'] and face['compiled']['renderKey']
    data=prepared['cards'][0]['faces'][0]['compiled']['data']
    assert data['version'].startswith('token')
    assert data['text']['pt']['text']=='5/5'
    assert 'Spacecraft' in data['text']['type']['text']
    rules=data['text']['rules']['text']
    for content in ('At the beginning of combat','Station','7+ |','Flying','Other artifacts you control have indestructible.'):
        assert content in rules
    assert not any(key.startswith('ability') for key in data['text'])
    assert 'station' not in data and not data.get('onload')
    assert ws.prepare(deck['id'])['cards']==prepared['cards']


def test_structured_layout_without_token_rules_is_a_validation_error(workspace):
    store,art,settings=workspace;ws=Workspace(store);station=card()
    comp=ws.compiler.compile_face(station,station,0,{},settings,art)
    original=copy.deepcopy(comp)
    with pytest.raises(ValidationError,match='compatible token template'):
        ws._apply_token_spec(comp,{},art,'Copy token')
    assert comp==original
