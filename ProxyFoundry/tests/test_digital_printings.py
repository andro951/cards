import json
from foundry.network import Network
from foundry.sources import Sources
from foundry.storage import Store

DIGITAL_ID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

def digital_memory_jar():
    return {
        'object':'card','id':DIGITAL_ID,'oracle_id':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        'name':'Memory Jar','layout':'normal','digital':True,'games':['mtgo'],
        'set':'vma','collector_number':'276','rarity':'mythic','type_line':'Artifact',
        'mana_cost':'{5}','oracle_text':'{T}, Sacrifice Memory Jar: Each player exiles their hand face down and draws seven cards.',
        'artist':'Donato Giancola','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/a/test.jpg'}
    }

def make_sources(tmp_path):
    store=Store(tmp_path);calls=[]
    def transport(url):
        calls.append(url)
        assert url.startswith('https://api.scryfall.com/cards/')
        return json.dumps(digital_memory_jar()).encode(),'application/json',{}
    return Sources(Network(store,transport=transport,sleeper=lambda _:None)),calls

def test_exact_digital_printing_is_valid_proxy_source(tmp_path):
    sources,calls=make_sources(tmp_path)
    card=sources.resolve_card(DIGITAL_ID)
    assert card['id']==DIGITAL_ID
    assert card['digital'] is True
    assert card['set']=='vma' and card['collector_number']=='276'
    assert calls==['https://api.scryfall.com/cards/'+DIGITAL_ID]

def test_scryfall_deck_export_preserves_exact_digital_printing(tmp_path):
    sources,calls=make_sources(tmp_path)
    export={
      'name':'Digital printing selected intentionally',
      'entries':{
        'mainboard':[
          {'count':1,'found':True,'raw_text':'Memory Jar',
           'card_digest':{'id':DIGITAL_ID,'name':'Memory Jar','set':'vma','collector_number':'276'}}
        ]
      }
    }
    result=sources.import_deck(export)
    assert len(result['cards'])==1
    entry=result['cards'][0]
    assert entry['sourceIsExact'] is True
    assert entry['scryfall']['id']==DIGITAL_ID
    assert entry['scryfall']['digital'] is True
    assert entry['digest']['set']=='vma' and entry['digest']['collector_number']=='276'
    assert calls==['https://api.scryfall.com/cards/'+DIGITAL_ID]

def test_name_lookup_may_also_return_digital_without_being_rejected(tmp_path):
    sources,calls=make_sources(tmp_path)
    card=sources.resolve_card('Memory Jar')
    assert card['digital'] is True
    assert calls==['https://api.scryfall.com/cards/named?exact=Memory%20Jar']
