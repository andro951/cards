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


def sources_for_mask(data,name):
    return [
        frame.get('src','') for frame in data.get('frames',[])
        if name in {
            mask.get('name') for mask in frame.get('masks',[])
            if isinstance(mask,dict)
        }
    ]


def test_everflowing_well_pair_uses_real_cardconjurer_transform_assets(tmp_path):
    store,art,settings=env(tmp_path);card=everflowing_pair();compiler=Compiler(store)
    front=compiler.compile_face(card,card['card_faces'][0],0,{},settings,art,art_origin='Scryfall selected printing')
    back=compiler.compile_face(card,card['card_faces'][1],1,{},settings,art,art_origin='Scryfall selected printing')

    assert front['group']=='transform-front' and front['recipe']=='m15_transform_front'
    assert back['group']=='transform-back' and back['recipe']=='m15_transform_back'
    assert front['templateVersion']==7 and back['templateVersion']==7
    assert front['data']['version']=='m15TransformFront'
    assert back['data']['version']=='m15TransformFront'

    front_sources=[f.get('src','') for f in front['data']['frames']]
    back_sources=[f.get('src','') for f in back['data']['frames']]
    assert '/img/frames/m15/transform/icons/default.png' in front_sources
    assert '/img/frames/m15/transform/regular/frontA.png' in sources_for_mask(front['data'],'Frame')
    assert '/img/frames/m15/transform/regular/new/backL.png' in sources_for_mask(back['data'],'Frame')
    for piece in ('Title','Type','Rules','Pinline'):
        assert sources_for_mask(front['data'],piece)==['/img/frames/m15/transform/regular/frontU.png']
        assert sources_for_mask(back['data'],piece)==['/img/frames/m15/transform/regular/new/backU.png']
    assert any('/img/frames/m15/transform/crowns/regular/u.png'==x for x in front_sources)
    assert any('/img/frames/m15/transform/crowns/regular/new/u.png'==x for x in back_sources)
    assert '/img/frames/m15/transform/icons/default.png' not in back_sources
    assert front['data']['text']['title']['x']==0.16
    assert back['data']['text']['title']['x']==0.0854
    assert back['data']['text']['title']['color']=='white'
    assert back['data']['text']['type']['color']=='white'
    assert front['renderKey']!=back['renderKey']


def test_search_for_azcanta_uses_transform_enchantment_front_and_land_back(tmp_path):
    store,art,settings=env(tmp_path)
    card={
        'object':'card','id':'22222222-2222-4222-8222-222222222222',
        'name':'Search for Azcanta // Azcanta, the Sunken Ruin','layout':'transform',
        'rarity':'rare','set':'xln','collector_number':'74','artist':'Magali Villeneuve',
        'frame_effects':['compasslanddfc'],
        'card_faces':[
            {'name':'Search for Azcanta','type_line':'Legendary Enchantment','mana_cost':'{1}{U}',
             'oracle_text':'At the beginning of your upkeep, surveil 1. Then if you have seven or more cards in your graveyard, you may transform Search for Azcanta.',
             'colors':['U'],'artist':'Magali Villeneuve'},
            {'name':'Azcanta, the Sunken Ruin','type_line':'Legendary Land','mana_cost':'',
             'oracle_text':'(Transforms from Search for Azcanta.)\n{T}: Add {U}.\n{2}{U}, {T}: Look at the top four cards of your library.',
             'colors':[],'produced_mana':['U'],'artist':'Magali Villeneuve'},
        ],
    }
    compiler=Compiler(store)
    front=compiler.compile_face(card,card['card_faces'][0],0,{},settings,art,art_origin='Scryfall selected printing')
    back=compiler.compile_face(card,card['card_faces'][1],1,{},settings,art,art_origin='Scryfall selected printing')
    front_sources=[f.get('src','') for f in front['data']['frames']]
    back_sources=[f.get('src','') for f in back['data']['frames']]
    assert front['templateVersion']==7 and back['templateVersion']==7
    assert '/img/frames/m15/transform/regular/frontU.png' in front_sources
    assert '/img/frames/m15/transform/regular/new/backL.png' in back_sources
    for piece in ('Title','Type','Rules','Pinline'):
        assert sources_for_mask(back['data'],piece)==['/img/frames/m15/transform/regular/new/backU.png']
    assert '/img/frames/m15/transform/crowns/regular/u.png' in front_sources
    assert '/img/frames/m15/transform/crowns/regular/new/u.png' in back_sources
    assert '/img/frames/m15/transform/icons/compass.svg' in front_sources
    assert '/img/frames/m15/transform/icons/land.svg' in back_sources
    assert front['data']['text']['type']['text']=='Legendary Enchantment'
    assert back['data']['text']['type']['text']=='Legendary Land'


def test_multicolor_transform_artifact_keeps_gold_accents_and_gradient_pinline(tmp_path):
    store,art,settings=env(tmp_path);card=everflowing_pair()
    front=card['card_faces'][0]
    front['colors']=['U','R'];front['mana_cost']='{1}{U}{R}'
    data=Compiler(store).compile_face(card,front,0,{},settings,art,art_origin='Scryfall selected printing')['data']
    for piece in ('Title','Type','Rules'):
        assert sources_for_mask(data,piece)==['/img/frames/m15/transform/regular/frontM.png']
    pinline_sources=sources_for_mask(data,'Pinline')
    assert len(pinline_sources)==1 and pinline_sources[0].startswith('data:image/svg+xml;utf8,')
    pinline=next(frame for frame in data['frames'] if 'Pinline' in {
        mask.get('name') for mask in frame.get('masks',[]) if isinstance(mask,dict)
    })
    assert pinline['masks']==[{'src':'/img/frames/m15/transform/regular/maskPinlineFront.png','name':'Pinline'}]
    assert '/img/frames/m15/transform/regular/frontA.png' in sources_for_mask(data,'Frame')
    crowns=[f for f in data['frames'] if '/transform/crowns/regular/' in str(f.get('src',''))]
    assert [f['src'] for f in crowns]==[
        '/img/frames/m15/transform/crowns/regular/r.png',
        '/img/frames/m15/transform/crowns/regular/u.png',
    ]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert crowns[1]['masks']==[]


def test_colorless_transform_land_keeps_land_crown(tmp_path):
    store,art,settings=env(tmp_path)
    card={
        'object':'card','id':'33333333-3333-4333-8333-333333333333',
        'name':'Front // Empty Back','layout':'transform','rarity':'rare','artist':'Test Artist',
        'card_faces':[
            {'name':'Front','type_line':'Legendary Creature — Human','mana_cost':'{1}{W}',
             'oracle_text':'Transform this permanent.','colors':['W'],'power':'2','toughness':'2','artist':'Test Artist'},
            {'name':'Empty Back','type_line':'Legendary Land','mana_cost':'',
             'oracle_text':'{T}: Add {C}.','colors':[],'produced_mana':['C'],'artist':'Test Artist'},
        ],
    }
    back=Compiler(store).compile_face(card,card['card_faces'][1],1,{},settings,art,art_origin='Scryfall selected printing')
    sources=[f.get('src','') for f in back['data']['frames']]
    assert '/img/frames/m15/transform/crowns/regular/new/l.png' in sources


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
