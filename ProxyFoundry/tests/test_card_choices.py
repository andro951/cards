"""Artwork and official text choices preserve the imported card's source data."""
import io
import json
import pytest

from PIL import Image

from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.domain import ValidationError


ORIGINAL='11111111-1111-4111-8111-111111111111'
ALTERNATE='22222222-2222-4222-8222-222222222222'
ORACLE='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'


def test_art_and_official_text_choices_do_not_replace_printing(tmp_path):
    store=Store(tmp_path)
    def card(ident,rarity,artist,image,flavor):
        return {'id':ident,'oracle_id':ORACLE,'name':'Choice Creature','layout':'normal',
                'type_line':'Creature — Wizard','mana_cost':'{2}{U}','colors':['U'],
                'power':'2','toughness':'2','oracle_text':'Current wording','rarity':rarity,
                'artist':artist,'flavor_text':flavor,'image_uris':{'art_crop':image}}
    first=card(ORIGINAL,'rare','Artist One','https://cards.scryfall.io/first.png','Original flavor')
    second=card(ALTERNATE,'common','Artist Two','https://cards.scryfall.io/second.png','Alternate flavor')
    second['printed_text']='Older official wording'
    image=io.BytesIO();Image.new('RGB',(900,650),'#517092').save(image,'PNG')
    alternate_image=io.BytesIO();Image.new('RGB',(900,650),'#925170').save(alternate_image,'PNG')
    def transport(url):
        if ORIGINAL in url:return json.dumps(first).encode(),'application/json',{}
        if ALTERNATE in url:return json.dumps(second).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return (alternate_image if 'second' in url else image).getvalue(),'image/png',{}
        raise AssertionError(url)
    ws=Workspace(store,Network(store,transport=transport))
    deck=ws.create({'name':'Choice test','source':ORIGINAL})
    deck=ws.prepare(deck['id'])
    entry=deck['cards'][0];face=entry['faces'][0]
    before=face['compiled']['artId']

    deck=ws.mutate_card(deck['id'],entry['id'],{'revision':deck['revision'],'faceId':face['id'],
        'selectedArtPrintingId':ALTERNATE,
        'officialRulesSelection':{'printingId':ALTERNATE,'field':'printed_text'},
        'officialFlavorSelection':{'printingId':ALTERNATE,'field':'flavor_text'}})
    assert deck['cards'][0]['scryfall']['id']==ORIGINAL
    assert deck['cards'][0]['scryfall']['rarity']=='rare'
    assert not deck['cards'][0]['faces'][0].get('semanticOverrides')
    deck=ws.prepare(deck['id'])
    face=deck['cards'][0]['faces'][0]
    assert face['compiled']['artist'].startswith('Artist Two')
    assert face['compiled']['artId']!=before
    assert face['compiled']['data']['text']['rules']['text'].find('Older official wording')>=0
    assert face['compiled']['data']['text']['rules']['text'].find('Alternate flavor')>=0
    assert deck['cards'][0]['scryfall']['oracle_text']=='Current wording'

    settings={'showFlavorText':False}
    deck=ws.save(deck['id'],{'revision':deck['revision'],'settings':settings})
    deck=ws.prepare(deck['id'])
    assert 'Alternate flavor' not in deck['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
    deck=ws.save(deck['id'],{'revision':deck['revision'],'settings':{'showFlavorText':True}})
    deck=ws.prepare(deck['id'])
    assert 'Alternate flavor' in deck['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
    deck=ws.mutate_card(deck['id'],entry['id'],{'revision':deck['revision'],'faceId':face['id'],
        'semanticOverrides':{'oracle_text':'Typed rules','flavor_text':'Typed flavor'}})
    deck=ws.prepare(deck['id'])
    text=deck['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
    assert 'Typed rules' in text and 'Typed flavor' in text and 'Older official wording' not in text
    deck=ws.mutate_card(deck['id'],entry['id'],{'revision':deck['revision'],'faceId':face['id'],
        'semanticOverrides':{}})
    deck=ws.prepare(deck['id'])
    assert 'Older official wording' in deck['cards'][0]['faces'][0]['compiled']['data']['text']['rules']['text']
    with pytest.raises(ValidationError):
        ws.mutate_card(deck['id'],entry['id'],{'revision':deck['revision'],'faceId':face['id'],
            'selectedArtPrintingId':'not-a-scryfall-id'})
