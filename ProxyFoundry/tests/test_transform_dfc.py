import io

import pytest
from PIL import Image

from foundry.compiler import Compiler
from foundry.domain import ValidationError
from foundry.images import ingest_image,rarity_variants
from foundry.storage import Store


def png(size=(1200,1600),color='#556677'):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return out.getvalue()


def everflowing_pair():
    return {
        'object':'card',
        'id':'bf573fb7-fa6c-4df7-8e5e-1e071585361e',
        'oracle_id':'1f57a9f1-6b95-4395-bdf0-c5289b786ab1',
        'name':'The Everflowing Well // The Myriad Pools',
        'layout':'transform',
        'rarity':'rare',
        'set':'lci',
        'collector_number':'56',
        'artist':'David Álvarez',
        'card_faces':[
            {
                'name':'The Everflowing Well',
                'mana_cost':'{2}{U}',
                'type_line':'Legendary Artifact',
                'oracle_text':'When The Everflowing Well enters, mill two cards, then draw two cards.\nDescend 8 — At the beginning of your upkeep, if there are eight or more permanent cards in your graveyard, transform The Everflowing Well.',
                'colors':['U'],
                'artist':'David Álvarez',
            },
            {
                'name':'The Myriad Pools',
                'mana_cost':'',
                'type_line':'Legendary Artifact Land',
                'oracle_text':'(Transforms from The Everflowing Well.)\n{T}: Add {U}.\nWhenever you cast a permanent spell using mana produced by The Myriad Pools, up to one other target permanent you control becomes a copy of that spell until end of turn.',
                'colors':[],
                'produced_mana':['U'],
                'artist':'David Álvarez',
            },
        ],
    }


def env(tmp_path):
    store=Store(tmp_path)
    art=ingest_image(store,png())
    symbols=rarity_variants(store,art['id'])
    return store,art['id'],{'symbols':symbols,'artist':''}


def test_everflowing_well_pair_uses_real_cardconjurer_transform_assets(tmp_path):
    store,art,settings=env(tmp_path);card=everflowing_pair();compiler=Compiler(store)
    front=compiler.compile_face(card,card['card_faces'][0],0,{},settings,art,art_origin='Scryfall selected printing')
    back=compiler.compile_face(card,card['card_faces'][1],1,{},settings,art,art_origin='Scryfall selected printing')

    assert front['group']=='transform-front' and front['recipe']=='m15_transform_front'
    assert back['group']=='transform-back' and back['recipe']=='m15_transform_back'
    assert front['templateVersion']==4 and back['templateVersion']==4
    assert front['data']['version']=='m15TransformFront'
    assert back['data']['version']=='m15TransformFront'

    front_sources=[f.get('src','') for f in front['data']['frames']]
    back_sources=[f.get('src','') for f in back['data']['frames']]
    assert '/img/frames/m15/transform/icons/default.png' in front_sources
    assert any('/img/frames/m15/transform/regular/frontA.png'==x for x in front_sources)
    assert any('/img/frames/m15/transform/regular/new/backA.png'==x for x in back_sources)
    assert any('/img/frames/m15/transform/crowns/regular/u.png'==x for x in front_sources)
    assert any('/img/frames/m15/transform/crowns/regular/new/a.png'==x for x in back_sources)
    assert '/img/frames/m15/transform/icons/default.png' not in back_sources
    assert front['data']['text']['title']['x']==0.16
    assert back['data']['text']['title']['x']==0.0854
    assert back['data']['text']['title']['color']=='white'
    assert back['data']['text']['type']['color']=='white'
    assert front['renderKey']!=back['renderKey']


def test_transform_structural_faces_still_require_compatible_template(tmp_path):
    store,art,settings=env(tmp_path)
    card={
        'object':'card','id':'11111111-1111-4111-8111-111111111111',
        'name':'Saga Transform Test // Back','layout':'transform','rarity':'rare',
        'set':'tst','collector_number':'1','artist':'Test Artist',
        'card_faces':[
            {'name':'Saga Transform Test','type_line':'Enchantment — Saga','mana_cost':'{2}{W}',
             'oracle_text':'I — Draw a card.','colors':['W'],'artist':'Test Artist'},
            {'name':'Back','type_line':'Creature — Spirit','mana_cost':'','oracle_text':'Flying',
             'colors':['W'],'power':'3','toughness':'3','artist':'Test Artist'},
        ],
    }
    with pytest.raises(ValidationError,match='structural subtype'):
        Compiler(store).compile_face(card,card['card_faces'][0],0,{},settings,art,art_origin='Scryfall selected printing')
