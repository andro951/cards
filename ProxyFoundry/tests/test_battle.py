import io

from PIL import Image

from foundry.compiler import Compiler
from foundry.domain import type_group
from foundry.images import ingest_image,rarity_variants
from foundry.storage import Store


def png(size=(1600,1100),color='#557744'):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return out.getvalue()


def invasion_of_ikoria():
    return {
        'object':'card',
        'id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        'name':'Invasion of Ikoria // Zilortha, Apex of Ikoria',
        'layout':'transform',
        'rarity':'rare',
        'set':'mom',
        'collector_number':'190',
        'artist':'Antonio José Manzanedo',
        'card_faces':[
            {
                'name':'Invasion of Ikoria',
                'mana_cost':'{X}{G}{G}',
                'type_line':'Battle — Siege',
                'oracle_text':'When Invasion of Ikoria enters the battlefield, search your library and/or graveyard for a non-Human creature card with mana value X or less and put it onto the battlefield. If you search your library this way, shuffle.',
                'colors':['G'],
                'defense':'6',
                'artist':'Antonio José Manzanedo',
            },
            {
                'name':'Zilortha, Apex of Ikoria',
                'mana_cost':'',
                'type_line':'Legendary Creature — Dinosaur',
                'oracle_text':'Reach\nFor each non-Human creature you control, you may have that creature assign its combat damage as though it weren’t blocked.',
                'colors':['G'],
                'power':'8',
                'toughness':'8',
                'artist':'Antonio José Manzanedo',
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


def test_transform_battle_front_classifies_as_battle_and_back_as_transform():
    card=invasion_of_ikoria()
    assert type_group(card['card_faces'][0],card,0)=='battle'
    assert type_group(card['card_faces'][1],card,1)=='transform-back'


def test_invasion_of_ikoria_uses_native_battle_front_and_transform_back(tmp_path):
    store,art,settings=env(tmp_path)
    card=invasion_of_ikoria()
    compiler=Compiler(store)

    front=compiler.compile_face(card,card['card_faces'][0],0,{},settings,art,art_origin='Scryfall selected printing')
    back=compiler.compile_face(card,card['card_faces'][1],1,{},settings,art,art_origin='Scryfall selected printing')

    assert front['group']=='battle'
    assert front['recipe']=='m15_battle'
    assert front['templateVersion']==2
    assert front['data']['version']=='battle'
    assert front['data']['landscape'] is True
    assert (front['data']['width'],front['data']['height'])==(2814,2010)
    assert front['data']['artBounds']=={
        'x':167/2100,'y':60/1500,'width':1873/2100,'height':1371/1500,
    }
    assert front['data']['text']['type']['text']=='Battle — Siege'
    assert front['data']['text']['defense']['text']=='6'
    assert front['data']['text']['reminder']['text']=='8/8'
    for piece in ('Pinline','Title','Type','Rules','Defense','Border'):
        assert sources_for_mask(front['data'],piece)==['/img/frames/m15/battle/g.png']
    assert any(f.get('src')=='/img/frames/m15/battle/holostamp.png' for f in front['data']['frames'])

    assert back['group']=='transform-back'
    assert back['recipe']=='m15_transform_back'
    assert back['data']['version']=='m15TransformFront'
    assert sources_for_mask(back['data'],'Frame')==['/img/frames/m15/transform/regular/new/backG.png']
    assert back['data']['text']['pt']['text']=='8/8'


def test_two_color_battle_keeps_battle_structure_and_gets_universal_gradient(tmp_path):
    store,art,settings=env(tmp_path)
    card=invasion_of_ikoria()
    front=card['card_faces'][0]
    front['colors']=['G','U']
    front['mana_cost']='{X}{G}{U}'
    data=Compiler(store).compile_face(card,front,0,{},settings,art,art_origin='Scryfall selected printing')['data']

    assert sources_for_mask(data,'Defense')==['/img/frames/m15/battle/m.png']
    assert sources_for_mask(data,'Border')==['/img/frames/m15/battle/m.png']
    for piece in ('Title','Type','Rules'):
        assert sources_for_mask(data,piece)==['/img/frames/m15/battle/m.png']
    pinline=sources_for_mask(data,'Pinline')
    assert len(pinline)==1 and pinline[0].startswith('data:image/svg+xml;utf8,')
