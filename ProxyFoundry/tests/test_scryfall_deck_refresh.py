import json

from foundry.network import Network
from foundry.sources import Sources
from foundry.storage import Store


DECK_ID='12345678-1234-1234-1234-123456789abc'
CARD_A='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
CARD_B='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
DECK_URL=f'https://scryfall.com/@tester/decks/{DECK_ID}'
EXPORT_URL=f'https://api.scryfall.com/decks/{DECK_ID}/export/json'


def card(ident,name,collector):
    return {
        'object':'card','id':ident,'name':name,'layout':'normal',
        'type_line':'Artifact','oracle_text':'','colors':[],'rarity':'common',
        'set':'tst','collector_number':collector,'artist':'Test Artist',
    }


def export(ident,name,collector):
    return {
        'name':'Live deck',
        'entries':{
            'mainboard':[{
                'count':1,'found':True,'raw_text':f'1 {name}',
                'card_digest':{
                    'id':ident,'name':name,'set':'tst',
                    'collector_number':collector,
                },
            }]
        },
    }


def test_same_scryfall_deck_url_is_fetched_live_on_every_import(tmp_path):
    store=Store(tmp_path)
    exports=[export(CARD_A,'Alpha', '1'),export(CARD_B,'Beta','2')]
    export_calls=[]
    def transport(url):
        if url==EXPORT_URL:
            export_calls.append(url)
            payload=exports[min(len(export_calls)-1,len(exports)-1)]
            return json.dumps(payload).encode(),'application/json',{}
        if url.endswith(CARD_A):
            return json.dumps(card(CARD_A,'Alpha','1')).encode(),'application/json',{}
        if url.endswith(CARD_B):
            return json.dumps(card(CARD_B,'Beta','2')).encode(),'application/json',{}
        raise AssertionError('unexpected URL '+url)

    net=Network(store,transport=transport,clock=lambda:1000.0,sleeper=lambda _:None)
    sources=Sources(net)

    first=sources.import_deck(DECK_URL)
    second=sources.import_deck(DECK_URL)

    assert [c['name'] for c in first['cards']]==['Alpha']
    assert [c['name'] for c in second['cards']]==['Beta']
    assert export_calls==[EXPORT_URL,EXPORT_URL]


def test_live_deck_export_does_not_disable_card_metadata_cache(tmp_path):
    store=Store(tmp_path)
    payload=export(CARD_A,'Alpha','1')
    calls=[]
    def transport(url):
        calls.append(url)
        if url==EXPORT_URL:
            return json.dumps(payload).encode(),'application/json',{}
        if url.endswith(CARD_A):
            return json.dumps(card(CARD_A,'Alpha','1')).encode(),'application/json',{}
        raise AssertionError('unexpected URL '+url)

    net=Network(store,transport=transport,clock=lambda:1000.0,sleeper=lambda _:None)
    sources=Sources(net)

    sources.import_deck(DECK_URL)
    sources.import_deck(DECK_URL)

    assert calls.count(EXPORT_URL)==2
    assert calls.count('https://api.scryfall.com/cards/'+CARD_A)==1
