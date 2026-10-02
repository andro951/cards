"""Metadata import yields safely without partial decks or lost intervening edits."""
import json

import pytest

from foundry.browser import create_app,request
from foundry.domain import ConflictError,ValidationError
from foundry.network import Network
from foundry.sources import Sources
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.runtime import Runtime


CARDS=[{'id':f'11111111-1111-4111-8111-{index:012d}','name':f'Scheduled {index}',
    'layout':'normal','type_line':'Creature — Wizard','colors':['U'],'mana_cost':'{U}',
    'oracle_text':'Flying','rarity':'common','power':'1','toughness':'1','artist':'Test Artist'} for index in range(3)]


def transport(calls):
    def fetch(url):
        calls.append(url)
        card=next(card for card in CARDS if url.endswith(card['id']))
        return json.dumps(card).encode(),'application/json',{}
    return fetch


def drain(steps):
    while True:
        try:next(steps)
        except StopIteration as finished:return finished.value


def test_metadata_steps_preserve_duplicate_quantities_sections_and_sync_result(tmp_path):
    calls=[];source=Sources(Network(Store(tmp_path),transport=transport(calls),sleeper=lambda _:None))
    rows=[{'id':CARDS[0]['id'],'quantity':2},{'id':CARDS[0]['id'],'quantity':3},
        {'id':CARDS[0]['id'],'quantity':1,'section':'sideboard'},{'id':CARDS[1]['id']}]
    progress=[];steps=source.import_deck_steps(rows,progress=lambda *row:progress.append(row))
    next(steps);assert not calls
    for count in range(len(rows)):
        next(steps);assert progress[-1][0]==count+1
    with pytest.raises(StopIteration) as result:next(steps)
    scheduled=result.value.value;sync=source.import_deck(rows)
    def contents(deck):return [(card['name'],card['quantity'],card['section'],card['sourceIsExact']) for card in deck['cards']]
    assert contents(scheduled)==contents(sync)==[('Scheduled 0',5,'mainboard',True),('Scheduled 0',1,'sideboard',True),('Scheduled 1',1,'mainboard',True)]
    assert len(calls)==2 and all('api.scryfall.com/cards/' in url for url in calls)


def test_create_cancel_after_last_resolved_card_never_publishes_partial_deck(tmp_path):
    store=Store(tmp_path);calls=[];ws=Workspace(store,Network(store,transport=transport(calls),sleeper=lambda _:None))
    cancelled=[False];steps=ws.create_steps({'source':[{'id':card['id']} for card in CARDS]},cancel=lambda:cancelled[0])
    next(steps)
    for _ in CARDS:next(steps);assert not store.list('decks')
    cancelled[0]=True
    with pytest.raises(ValidationError,match='cancelled'):next(steps)
    assert not store.list('decks') and len(calls)==3
    #Completed metadata is cached even though the import was never published.
    finished=ws.create({'source':[{'id':card['id']} for card in CARDS]})
    assert len(finished['cards'])==3 and len(calls)==3


def test_add_cards_rejects_intervening_edit_without_overwriting_it(tmp_path):
    store=Store(tmp_path);ws=Workspace(store,Network(store,transport=transport([]),sleeper=lambda _:None))
    deck=ws.create({'source':CARDS[0]['id']})
    steps=ws.add_cards_steps(deck['id'],{'source':CARDS[1]['id'],'revision':deck['revision']})
    next(steps);next(steps)
    edited=store.get('decks',deck['id']);edited['name']='Keep the user edit';store.put('decks',edited,edited['revision'])
    with pytest.raises(ConflictError):next(steps)
    saved=store.get('decks',deck['id'])
    assert saved['name']=='Keep the user edit' and len(saved['cards'])==1


def test_browser_import_route_is_resumable_and_reads_work_between_rows(tmp_path):
    calls=[];app=create_app(tmp_path,transport(calls),'http://127.0.0.1')
    app.ws.net.sleeper=lambda _:None
    response=request(app,'POST','/api/decks/import',json.dumps({'source':[{'id':card['id']} for card in CARDS]}).encode())
    ident=json.loads(response['body'])['id'];assert not calls
    app.jobs.run_pending(limit=1);assert not calls
    app.jobs.run_pending(limit=1);assert len(calls)==1
    assert app.jobs.get(ident)['done']==1 and not app.store.list('decks')
    settings=request(app,'GET','/api/settings');assert settings['status']==200
    app.jobs.run_pending()
    deck=app.jobs.get(ident)['result'];assert len(deck['cards'])==3
    assert not any('compiled' in face for card in deck['cards'] for face in card['faces'])


def test_import_total_timing_spans_generator_chunks(tmp_path,monkeypatch):
    from foundry import timing
    from test_timing import capture,rows
    store=Store(tmp_path);stream=capture(store);clock=[0.0]
    monkeypatch.setattr(timing.time,'perf_counter',lambda:clock[0])
    source=Sources(Network(store,transport=transport([]),sleeper=lambda _:None))
    steps=source.import_deck_steps(CARDS[0]['id']);next(steps)
    clock[0]=2;next(steps);clock[0]=5
    result=drain(steps);assert len(result['cards'])==1
    timings=[row for row in rows(stream) if row['stage']=='deck.import']
    assert len(timings)==1 and timings[0]['seconds']==5 and timings[0]['outcome']=='ok'


def test_runtime_yields_between_dependencies_and_cancel_does_not_report_ready():
    runtime=Runtime(None);fetched=[];runtime.fetch=lambda path:fetched.append(path)
    cancelled=[False];steps=runtime.prepare_steps(cancel=lambda:cancelled[0])
    for count in range(len(runtime.SOURCE_FILES)):
        next(steps);assert fetched==list(runtime.SOURCE_FILES[:count+1])
    cancelled[0]=True
    with pytest.raises(ValidationError,match='cancelled'):next(steps)
    fetched.clear();result=runtime.prepare()
    assert fetched==list(runtime.SOURCE_FILES) and result['host']=='/runtime/host'
