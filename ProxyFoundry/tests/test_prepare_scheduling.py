"""Preparation yields between cards, batches durable saves, and respects edits."""
import copy
import io
import json

import pytest
from PIL import Image

from foundry.domain import ConflictError,ValidationError,uid
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace


def workspace(tmp_path):
    card={'id':'11111111-1111-4111-8111-111111111111','name':'Scheduled Creature',
        'layout':'normal','type_line':'Creature — Wizard','colors':['U'],
        'mana_cost':'{U}','oracle_text':'Flying','rarity':'common','power':'1',
        'toughness':'1','artist':'Test Artist','image_uris':{'art_crop':'https://cards.scryfall.io/test.png'}}
    image=io.BytesIO();Image.new('RGB',(900,650),'blue').save(image,'PNG')
    def transport(url):
        if 'api.scryfall.com' in url:return json.dumps(card).encode(),'application/json',{}
        return image.getvalue(),'image/png',{}
    store=Store(tmp_path)
    ws=Workspace(store,Network(store,transport=transport,sleeper=lambda _:None))
    deck=ws.create({'source':card['id']})
    second=copy.deepcopy(deck['cards'][0]);second['id']=uid();second['faces'][0]['id']=uid()
    deck['cards'].append(second);deck=ws.store.put('decks',deck,deck['revision'])
    return ws,deck


def test_prepare_yields_between_cards_and_matches_synchronous_output(tmp_path):
    ws,deck=workspace(tmp_path);steps=ws.prepare_steps(deck['id'])
    next(steps)
    assert all('compiled' not in card['faces'][0] for card in ws.deck(deck['id'])['cards'])
    next(steps)
    saved=ws.deck(deck['id'])
    assert 'compiled' not in saved['cards'][0]['faces'][0]
    assert 'compiled' not in saved['cards'][1]['faces'][0]
    next(steps)
    with pytest.raises(StopIteration) as finished:next(steps)
    scheduled=finished.value.value
    synchronous=ws.prepare(deck['id'])
    assert scheduled['status']==synchronous['status']=='prepared'
    assert [c['faces'][0]['compiled']['renderKey'] for c in scheduled['cards']]==[
        c['faces'][0]['compiled']['renderKey'] for c in synchronous['cards']]


def test_prepare_intervening_edit_is_preserved_instead_of_overwritten(tmp_path):
    ws,deck=workspace(tmp_path);steps=ws.prepare_steps(deck['id'])
    next(steps);next(steps)
    edited=ws.store.get('decks',deck['id']);edited['name']='User changed this'
    ws.store.put('decks',edited,edited['revision'])
    next(steps) # The next card can be staged, but the checkpoint must reject stale writes.
    with pytest.raises(ConflictError):next(steps)
    saved=ws.store.get('decks',deck['id'])
    assert saved['name']=='User changed this'
    assert 'compiled' not in saved['cards'][1]['faces'][0]


def test_cancel_after_last_card_does_not_finalize_deck(tmp_path):
    ws,deck=workspace(tmp_path);cancelled=[False]
    steps=ws.prepare_steps(deck['id'],cancel=lambda:cancelled[0])
    next(steps);next(steps);next(steps);cancelled[0]=True
    with pytest.raises(ValidationError,match='cancelled'):next(steps)
    saved=ws.store.get('decks',deck['id'])
    assert saved['status']=='draft'
    assert all('compiled' in card['faces'][0] for card in saved['cards'])
