from __future__ import annotations
import copy
import pytest
from foundry.domain import *
from foundry.storage import Store
from foundry.network import Network, validate_remote_url


def test_cache_boundaries():
    assert cache_is_fresh(0, 365 * DAY - 1)
    assert not cache_is_fresh(0, 365 * DAY)
    assert cache_is_fresh(0, 7 * DAY - 1, True)
    assert not cache_is_fresh(0, 7 * DAY, True)
    assert not cache_is_fresh(None, 10)
    assert cache_is_fresh(100, 0)


@pytest.mark.parametrize('value', ['C:\\cards\\art', 'file:///C:/cards', 'http://github.com/a/b', 'https://evil.test/a/b', 'https://github.com/a/b/tree/main/../secret'])
def test_invalid_github_source(value):
    with pytest.raises(ValidationError): github_location(value)


def test_github_folders():
    x = github_location('https://github.com/andro951/cards/tree/main/doctor_who/art')
    assert x['repo'] == 'andro951/cards' and x['folder'] == 'doctor_who/art'
    assert github_location('a/b/c', branch='art/v2')['ref'] == 'art/v2'
    assert github_location('https://raw.githubusercontent.com/a/b/main/Images')['folder'] == 'Images'


def test_deck_text():
    x = parse_deck_text('Commander\n1 Esika, God of the Tree (KHM) 168\nDeck\n4x Forest\n1 Fire // Ice\nSideboard\n1 Bad\nOutside The Game\n1 Wish')
    assert [r['quantity'] for r in x] == [1, 4, 1]
    assert x[0]['source'] == 'khm:168'
    assert x[2]['name'] == 'Fire // Ice'
    assert len(parse_deck_text('Outside The Game\n1 Wish', True)) == 1


@pytest.mark.parametrize('types,layout,index,expected', [
    ('Artifact Creature — Myr','normal',0,'standard'), ('Legendary Artifact — Equipment','normal',0,'legendary'),
    ('Artifact Land','normal',0,'land'), ('Legendary Land','normal',0,'legendary-land'),
    ('Enchantment Land','normal',0,'land'), ("Enchantment Land — Urza's Saga",'saga',0,'saga'), ('Creature Land','normal',0,'special-land'),
    ('Basic Snow Land — Forest','normal',0,'basic-land'), ('Enchantment Creature — Saga','normal',0,'saga-creature'),
    ('Enchantment — Saga','saga',0,'saga'), ('Legendary Planeswalker — Jace','normal',0,'planeswalker'),
    ('Land','modal_dfc',1,'modal-back'), ('Creature','transform',0,'transform-front'),
    ('Enchantment — Room','split',0,'room'), ('Battle — Siege','normal',0,'battle')])
def test_groups(types,layout,index,expected):
    assert type_group({'type_line':types}, {'layout':layout},index) == expected


def test_urzas_saga_structural_priority_beats_land():
    card={'name':"Urza's Saga",'type_line':"Enchantment Land — Urza's Saga",'layout':'saga'}
    assert type_group(card,card,0)=='saga'


def test_crop_threshold():
    d = {'width':1000,'height':1000,'artBounds':{'width':1,'height':1}}
    assert not crop_metrics(1000,1000,d)['warning']
    assert not crop_metrics(1250,1000,d)['warning']
    assert crop_metrics(1251,1000,d)['warning']
    assert crop_metrics(1000,2000,d)['cropY'] == .5
    assert crop_metrics(2000,1000,d)['cropX'] == .5


def test_render_hash_quantity_independent():
    cc = {'artSource':'image-a','frames':[]}
    a = render_key(cc,'a')
    assert a == render_key(copy.deepcopy(cc),'a')
    assert a == render_key(copy.deepcopy(cc),'a',1)  # v1 preserves historical cache keys
    assert a != render_key(cc,'b')
    assert a != render_key(cc,'a',2)


def test_store_revisions_and_trash(tmp_path):
    store=Store(tmp_path)
    d=store.put('decks',{'name':'One','cards':[]})
    assert d['revision']==1
    two=store.put('decks',{**d,'name':'Two'},d['revision'])
    with pytest.raises(ConflictError): store.put('decks',{**d,'name':'Wrong'},d['revision'])
    assert store.get('decks',d['id'])['name']=='Two'
    store.trash('decks',d['id'],two['revision'])
    assert store.get('decks',d['id']) is None
    store.trash('decks',d['id'],restore=True)
    assert store.get('decks',d['id'])['name']=='Two'


def test_cache_read_through(tmp_path):
    clock=[1000.]; calls=[]
    def fetch(url): calls.append(url); return b'{"id":"one"}','application/json',{}
    store=Store(tmp_path); net=Network(store,transport=fetch,clock=lambda:clock[0],sleeper=lambda n:None)
    url='https://api.scryfall.com/cards/example'
    assert net.json(url)=={'id':'one'}
    assert net.json(url)=={'id':'one'} and len(calls)==1
    clock[0]+=7*DAY
    net.json(url); assert len(calls)==1
    net.json(url,refresh=True); assert len(calls)==2


@pytest.mark.parametrize('url',['file:///etc/passwd','https://127.0.0.1/','https://user:pass@api.scryfall.com/a','https://raw.githubusercontent.com/a/../b','https://evil.com/'])
def test_network_rejects_nonpublic_sources(url):
    with pytest.raises(ValidationError): validate_remote_url(url)
