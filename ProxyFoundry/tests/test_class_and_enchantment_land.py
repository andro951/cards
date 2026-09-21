import io

from PIL import Image

from foundry.compiler import Compiler, semantic
from foundry.images import ingest_image, rarity_variants
from foundry.storage import Store


def png(size=(1200,1600), color='#556677'):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,'PNG');return out.getvalue()


def env(tmp_path):
    store=Store(tmp_path)
    art=ingest_image(store,png())
    symbols=rarity_variants(store,art['id'])
    return store,art['id'],{'symbols':symbols,'artist':''}


def cleric_class():
    return {
        'object':'card','id':'11111111-1111-4111-8111-111111111111',
        'name':'Cleric Class','layout':'class','rarity':'uncommon','set':'afr','collector_number':'6',
        'artist':'Alayna Danner','type_line':'Enchantment — Class','mana_cost':'{W}','colors':['W'],
        'oracle_text':'(Gain the next level as a sorcery to add its ability.)\n'
                      'If you would gain life, you gain that much life plus 1 instead.\n'
                      '{3}{W}: Level 2\n'
                      'Whenever you gain life, put a +1/+1 counter on target creature you control.\n'
                      '{4}{W}: Level 3\n'
                      "When this Class becomes level 3, return target creature card from your graveyard to the battlefield. You gain life equal to that creature's toughness.",
    }


def valgavoths_lair():
    return {
        'object':'card','id':'22222222-2222-4222-8222-222222222222',
        'name':"Valgavoth's Lair",'layout':'normal','rarity':'rare','set':'dsk','collector_number':'271',
        'artist':'Ivan Shavrin','type_line':'Enchantment Land','mana_cost':'','colors':[],
        'oracle_text':'Hexproof\nThis land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.',
        'produced_mana':['W','U','B','R','G'],
    }


def test_cleric_class_uses_native_cardconjurer_class_frame(tmp_path):
    store,art,settings=env(tmp_path);card=cleric_class()
    result=Compiler(store).compile_face(card,card,0,{},settings,art,art_origin='Scryfall selected printing')
    data=result['data'];frames=data['frames'];text=data['text']

    assert result['group']=='class'
    assert result['recipe']=='class'
    assert result['templateVersion']==2
    assert data['version']=='class'
    assert data['onload']=='/js/frames/versionClass.js'
    assert data['class']=={'x':0.5014,'width':0.422,'count':2}
    assert data['artBounds']=={'x':0.0753,'y':0.1124,'width':0.4247,'height':0.7253}
    assert data['setSymbolBounds']=={'x':0.9227,'y':0.8739,'width':0.12,'height':0.0381,'vertical':'center','horizontal':'right'}
    assert frames[0]['src']=='/img/frames/class/w.png'
    assert [m['src'] for m in frames[0]['masks']]==[
        '/img/frames/class/pinline.svg',
        '/img/frames/m15/regular/m15MaskTitle.png',
        '/img/frames/saga/sagaMaskType.png',
        '/img/frames/class/frame.svg',
        '/img/frames/class/text.svg',
        '/img/frames/class/textRight.png',
        '/img/frames/class/border.svg',
    ]
    assert text['title']['text']=='Cleric Class'
    assert text['type']['text']=='Enchantment — Class'
    assert text['level1a']['text']=='{3}{W}:'
    assert text['level1b']['text']=='Level 2'
    assert 'Whenever you gain life' in text['level1c']['text']
    assert text['level2a']['text']=='{4}{W}:'
    assert text['level2b']['text']=='Level 3'
    assert 'return target creature card' in text['level2c']['text']
    assert text['level3c']['height']==0
    assert 'Gain the next level as a sorcery' in text['level0c']['text']
    assert 'If you would gain life' in text['level0c']['text']


def test_valgavoths_lair_is_land_family_with_five_color_mana_identity(tmp_path):
    store,art,settings=env(tmp_path);card=valgavoths_lair()
    sem=semantic(card,card)
    assert sem['types']==['Enchantment','Land']
    assert sem['land_colors']==list('WUBRG')

    result=Compiler(store).compile_face(card,card,0,{},settings,art,art_origin='Scryfall selected printing')
    data=result['data']
    assert result['group']=='land'
    assert result['recipe']=='land_five_color'
    assert data['text']['type']['text']=='Enchantment Land'
    assert result['templateVersion']==1
