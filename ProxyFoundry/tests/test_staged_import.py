"""List-only import, background metadata publication and generation gates."""
import json,time
import pytest
from foundry.browser import create_app,request
from foundry.domain import ConflictError,ValidationError
from foundry.sources import Sources
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace
from test_import_scheduling import CARDS,transport,drain


def workspace(tmp_path):
    calls=[];store=Store(tmp_path);ws=Workspace(store,Network(store,transport=transport(calls),sleeper=lambda _:None))
    return ws,calls


def staged(ws):
    listing=ws.sources.read_deck_manifest([{'id':card['id'],'name':card['name']} for card in CARDS])
    return ws.create_staged({'manifest':listing})


def test_public_list_fetch_preserves_names_printings_and_quantities_without_card_requests(tmp_path):
    calls=[];card=CARDS[0]
    export={'name':'List first','entries':{'mainboard':[{'count':3,'card_digest':{'id':card['id'],'name':card['name']}}]}}
    def fetch(url):
        calls.append(url);assert '/decks/' in url
        return json.dumps(export).encode(),'application/json',{}
    source=Sources(Network(Store(tmp_path),transport=fetch,sleeper=lambda _:None))
    result=source.read_deck_manifest('https://scryfall.com/@you/decks/33333333-3333-4333-8333-333333333333')
    assert len(calls)==1 and result['name']=='List first'
    assert result['rows']==[{'source':card['id'],'quantity':3,'section':'mainboard','name':card['name']}]
    assert 'digests' not in result


def test_background_metadata_keeps_intervening_setup_and_uuid_data_file(tmp_path):
    ws,calls=workspace(tmp_path);deck=staged(ws);assert not calls
    steps=ws.resolve_metadata_steps(deck['id']);next(steps)
    edited=ws.save(deck['id'],{'revision':deck['revision'],'settings':{'artist':'Keep artist','templateRules':{'legendary':'godzilla-card'}},
        'cardData':[{'oracle_id':'22222222-2222-4222-8222-222222222222','nickname':'Later nickname'}]})
    result=drain(steps);saved=ws.deck(deck['id'])
    assert not result.get('pendingImport') and saved['settings']['artist']=='Keep artist'
    assert saved['settings']['templateRules']['legendary']=='godzilla-card'
    assert saved['cardData']==edited['cardData'] and len(calls)==3
    assert [card['id'] for card in saved['cards']]==[card['id'] for card in deck['cards']]
    assert not any('compiled' in face for card in saved['cards'] for face in card['faces'])
    # A UUID that was unavailable during metadata loading must still be checked before rendering.
    with pytest.raises(ValidationError,match='selector'):
        ws.prepare(deck['id'])


def test_metadata_only_revision_can_save_once_but_real_intervening_edit_conflicts(tmp_path):
    ws,calls=workspace(tmp_path);deck=staged(ws);ws.resolve_metadata(deck['id'])
    saved=ws.save(deck['id'],{'revision':deck['revision'],'settings':{'artist':'Typed before completion'}})
    assert saved['settings']['artist']=='Typed before completion'
    with pytest.raises(ConflictError):ws.save(deck['id'],{'revision':deck['revision'],'settings':{'artist':'Stale tab'}})


@pytest.mark.parametrize('action',['cancel','delete'])
def test_interrupted_metadata_is_resumable_and_cannot_republish_a_deleted_deck(tmp_path,action):
    ws,calls=workspace(tmp_path);deck=staged(ws);cancelled=[False]
    steps=ws.resolve_metadata_steps(deck['id'],cancel=lambda:cancelled[0]);next(steps)
    if action=='cancel':cancelled[0]=True
    else:ws.store.begin_delete('decks',deck['id'],deck['revision'])
    with pytest.raises(ValidationError):drain(steps)
    if action=='delete':assert not ws.store.get('decks',deck['id'])
    else:
        assert ws.deck(deck['id'])['pendingImport']
        result=ws.resolve_metadata(deck['id']);assert not result.get('pendingImport')
        assert len(calls)==3,'The successful first card metadata must be reused.'


def test_staged_metadata_rebuilds_two_faces_and_combines_duplicate_printings(tmp_path):
    ws,calls=workspace(tmp_path);card={**CARDS[0],'layout':'transform','name':'Front // Back','card_faces':[
        {**CARDS[0],'name':'Front'},{**CARDS[0],'name':'Back','type_line':'Land','colors':[],'mana_cost':'','oracle_text':'{T}: Add {U}.'}]}
    ws.net.transport=lambda url:(json.dumps(card).encode(),'application/json',{})
    listing=ws.sources.read_deck_manifest([{'id':card['id'],'quantity':2},{'id':card['id'],'quantity':3}])
    deck=ws.create_staged({'manifest':listing});result=ws.resolve_metadata(deck['id'])
    assert len(result['cards'])==1 and result['cards'][0]['quantity']==5
    saved=ws.deck(deck['id']);assert [face['group'] for face in saved['cards'][0]['faces']]==['transform-front','transform-back']
    assert saved['cards'][0]['sourceIsExact']


def test_browser_background_job_yields_for_settings_and_is_safe_after_reload(tmp_path):
    calls=[];app=create_app(tmp_path,transport(calls),'http://127.0.0.1');app.ws.net.sleeper=lambda _:None
    def post(path,payload):
        reply=request(app,'POST',path,json.dumps(payload).encode());assert reply['status']==200,reply
        return json.loads(reply['body'])
    list_job=post('/api/decks/manifest',{'source':[{'id':c['id'],'name':c['name']} for c in CARDS]})
    app.jobs.run_pending();listing=app.jobs.get(list_job['id'])['result'];assert not calls
    draft_job=post('/api/decks/import',{'manifest':listing});app.jobs.run_pending();deck=app.jobs.get(draft_job['id'])['result']
    metadata=post('/api/decks/'+deck['id']+'/metadata',{});assert app.jobs.get(metadata['id'])['priority']==1
    app.jobs.run_pending(limit=1);assert len(calls)==1
    saved=post('/api/decks/'+deck['id']+'/save',{'revision':deck['revision'],'settings':{'artist':'Foreground edit'}})
    assert saved['settings']['artist']=='Foreground edit'
    app.jobs.run_pending();result=app.ws.deck(deck['id']);assert result['settings']['artist']=='Foreground edit'
    assert not result.get('pendingImport') and not any('compiled' in f for c in result['cards'] for f in c['faces'])


def test_large_list_only_import_does_not_resolve_cards(tmp_path):
    ws,calls=workspace(tmp_path);started=time.perf_counter()
    listing=ws.sources.read_deck_manifest([{'source':f'Card {number}'} for number in range(5000)])
    assert len(listing['rows'])==5000 and not calls
    assert time.perf_counter()-started<2
