import pytest
from pathlib import Path
from foundry.compiler import apply_universal_frame_color_treatment,_crown_color_variant


def mask(name,src='/mask.png'):
    return {'name':name,'src':src}


def layers(data,name):
    return [
        frame for frame in data['frames']
        if name in {
            item.get('name') for item in frame.get('masks',[])
            if isinstance(item,dict)
        }
    ]


def test_dual_color_universal_pass_splits_structure_and_colors_all_five_effects():
    data={'frames':[
        {
            'name':'Mixed Artifact Layer',
            'src':'/img/frames/m15/regular/m15FrameA.png',
            'masks':[mask('Frame'),mask('Title'),mask('Type'),mask('Rules'),mask('Pinline')],
        },
        {
            'name':'Legend Crown',
            'src':'/img/frames/m15/crowns/m15CrownAFloating.png',
            'masks':[],
        },
    ]}
    sem={'types':['Artifact'],'subtypes':['Vehicle'],'colors':['U','R'],'land_colors':[]}
    apply_universal_frame_color_treatment(data,sem)

    assert layers(data,'Frame')[0]['src'].endswith('m15FrameA.png')
    for effect in ('Title','Type','Rules'):
        assert layers(data,effect)[0]['src'].endswith('m15FrameM.png')
    pinline=layers(data,'Pinline')[0]
    assert pinline['src'].startswith('data:image/svg+xml;utf8,')
    crowns=[frame for frame in data['frames'] if '/crowns/' in str(frame.get('src',''))]
    assert [frame['src'] for frame in crowns]==[
        '/img/frames/m15/crowns/m15CrownRFloating.png',
        '/img/frames/m15/crowns/m15CrownUFloating.png',
    ]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert crowns[0]['opacity']==crowns[1]['opacity']==85


def test_universal_pass_uses_same_semantics_across_frame_families():
    data={'frames':[
        {
            'name':'Transform',
            'src':'/img/frames/m15/transform/regular/frontA.png',
            'masks':[mask('Frame'),mask('Title'),mask('Rules'),mask('Pinline')],
        },
        {
            'name':'Saga',
            'src':'/img/frames/saga/regular/sagaFrameW.png',
            'masks':[mask('Frame'),mask('Type'),mask('Text','/img/frames/saga/sagaMaskText.png')],
        },
        {
            'name':'Planeswalker',
            'src':'/img/frames/planeswalker/regular/planeswalkerFrameR.png',
            'masks':[mask('Frame'),mask('Title')],
        },
        {
            'name':'Transform Crown',
            'src':'/img/frames/m15/transform/crowns/regular/a.png',
            'masks':[],
        },
    ]}
    sem={'types':['Artifact'],'subtypes':[],'colors':['G']}
    apply_universal_frame_color_treatment(data,sem)

    assert layers(data,'Rules')[0]['src']=='/img/frames/m15/transform/regular/frontG.png'
    assert layers(data,'Pinline')[0]['src']=='/img/frames/m15/transform/regular/frontG.png'
    assert layers(data,'Type')[0]['src']=='/img/frames/saga/regular/sagaFrameG.png'
    saga_text=[
        frame for frame in data['frames']
        if 'Text' in {
            item.get('name') for item in frame.get('masks',[])
            if isinstance(item,dict)
        }
    ]
    assert saga_text[0]['src']=='/img/frames/saga/regular/sagaFrameG.png'
    assert any(
        frame.get('src')=='/img/frames/planeswalker/regular/planeswalkerFrameG.png'
        for frame in data['frames']
    )
    assert any(
        frame.get('src')=='/img/frames/m15/transform/crowns/regular/g.png'
        for frame in data['frames']
    )


def test_colorless_land_uses_neutral_effects_without_recoloring_structure():
    data={'frames':[
        {
            'name':'Academy Style',
            'src':'/img/frames/m15/genericShowcase/m15GenericShowcaseFrameU.png',
            'masks':[mask('Border'),mask('Title')],
        },
        {
            'name':'Blue Land Accents',
            'src':'/img/frames/m15/boxTopper/short/ul.png',
            'masks':[mask('Pinline'),mask('Type'),mask('Rules')],
        },
        {
            'name':'Blue Crown',
            'src':'/img/frames/m15/crowns/m15CrownUFloating.png',
            'masks':[],
        },
    ]}
    sem={'types':['Land'],'subtypes':[],'colors':[],'land_colors':[]}
    apply_universal_frame_color_treatment(data,sem)

    assert layers(data,'Title')[0]['src']=='/img/frames/m15/genericShowcase/m15GenericShowcaseFrameL.png'
    for effect in ('Pinline','Type','Rules'):
        assert layers(data,effect)[0]['src']=='/img/frames/m15/boxTopper/short/l.png'
    # Border is structural and therefore remains from the selected structural frame.
    assert layers(data,'Border')[0]['src'].endswith('FrameU.png')
    assert any(
        frame.get('src')=='/img/frames/m15/crowns/m15CrownLFloating.png'
        for frame in data['frames']
    )


def test_single_regular_crown_fallback_restores_old_two_native_png_blend():
    crown_masks=[
        {'src':'/img/frames/m15/crowns/m15MaskLegendCrown.png','name':'Crown Without Pinlines'},
        {'src':'/img/frames/m15/crowns/m15MaskLegendCrownPinline.png','name':'Crown With Pinlines'},
    ]
    data={'frames':[
        {'name':'Artifact Legend Crown','src':'/img/frames/m15/crowns/m15CrownA.png','masks':crown_masks},
        {'name':'Artifact Pinline','src':'/img/frames/m15/regular/m15FrameA.png','masks':[mask('Pinline')]},
    ]}
    sem={'types':['Artifact'],'subtypes':[],'colors':['W','U']}
    apply_universal_frame_color_treatment(data,sem)
    crowns=[frame for frame in data['frames'] if '/crowns/' in str(frame.get('src',''))]
    assert [frame['src'] for frame in crowns]==[
        '/img/frames/m15/crowns/m15CrownU.png',
        '/img/frames/m15/crowns/m15CrownW.png',
    ]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert crowns[1]['masks']==[]
    assert layers(data,'Pinline')[0]['src'].startswith('data:image/svg+xml;utf8,')


def test_existing_old_dual_crown_stack_is_preserved_byte_for_byte():
    right={
        'name':'Red Legend Crown (Right Blend)',
        'src':'/img/frames/m15/crowns/m15CrownR.png',
        'masks':[{'src':'data:image/svg+xml;utf8,OLDMASK','name':'Right Blend'}],
        'bounds':{'height':0.1667,'width':0.9454,'x':0.0274,'y':0.0191},
    }
    left={
        'name':'Blue Legend Crown',
        'src':'/img/frames/m15/crowns/m15CrownU.png',
        'masks':[],
        'bounds':{'height':0.1667,'width':0.9454,'x':0.0274,'y':0.0191},
    }
    data={'frames':[right,left,{'name':'Pinline','src':'/img/frames/m15/regular/m15FrameM.png','masks':[mask('Pinline')]}]}
    before=[right.copy(),left.copy()]
    apply_universal_frame_color_treatment(data,{'types':['Creature'],'subtypes':[],'colors':['U','R']})
    crowns=[frame for frame in data['frames'] if '/crowns/' in str(frame.get('src',''))]
    assert crowns[0]==right
    assert crowns[1]==left


def test_modal_crown_family_uses_native_layered_dual_blend():
    data={'frames':[
        {
            'name':'Artifact Legend Crown',
            'src':'/img/frames/modal/crowns/regular/a.png',
            'masks':[],
            'bounds':{'x':0.0274,'y':0.0191,'width':0.9454,'height':0.1667},
            'complementary':8,
        },
        {'name':'Pinline','src':'/img/frames/m15/regular/m15FrameM.png','masks':[mask('Pinline')]},
    ]}
    apply_universal_frame_color_treatment(
        data,{'types':['Creature'],'subtypes':[],'colors':['W','U']}
    )
    crowns=[f for f in data['frames'] if '/modal/crowns/regular/' in str(f.get('src',''))]
    assert [f['src'] for f in crowns]==[
        '/img/frames/modal/crowns/regular/u.png',
        '/img/frames/modal/crowns/regular/w.png',
    ]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert crowns[1]['masks']==[]
    assert crowns[0]['bounds']==crowns[1]['bounds']=={'x':0.0274,'y':0.0191,'width':0.9454,'height':0.1667}


def test_ub_floating_crown_family_uses_same_native_layered_dual_blend():
    data={'frames':[
        {
            'name':'Artifact Legend Crown',
            'src':'/img/frames/m15/ub/crowns/floating/a.png',
            'masks':[],
            'bounds':{'x':0.0307,'y':0.0191,'width':0.9387,'height':0.1024},
            'opacity':85,
        },
    ]}
    apply_universal_frame_color_treatment(
        data,{'types':['Artifact'],'subtypes':[],'colors':['U','R']}
    )
    crowns=[f for f in data['frames'] if '/ub/crowns/floating/' in str(f.get('src',''))]
    assert [f['src'] for f in crowns]==[
        '/img/frames/m15/ub/crowns/floating/r.png',
        '/img/frames/m15/ub/crowns/floating/u.png',
    ]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[1]['masks']==[]
    assert crowns[0]['opacity']==crowns[1]['opacity']==85


def test_showcase_ucrown_filename_family_is_also_detected():
    data={'frames':[
        {
            'name':'Blue Legend Crown',
            'src':'/img/frames/m15/oilslick/uCrown.png',
            'masks':[],
            'bounds':{'x':0,'y':0,'width':1,'height':1},
        },
    ]}
    apply_universal_frame_color_treatment(
        data,{'types':['Creature'],'subtypes':[],'colors':['B','G']}
    )
    crowns=[f for f in data['frames'] if '/oilslick/' in str(f.get('src',''))]
    assert [f['src'] for f in crowns]==[
        '/img/frames/m15/oilslick/gCrown.png',
        '/img/frames/m15/oilslick/bCrown.png',
    ]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[1]['masks']==[]


def test_crown_family_color_variant_detection_is_filename_agnostic():
    cases={
        '/img/frames/m15/crowns/m15CrownAFloatingAlt.png':
            '/img/frames/m15/crowns/m15CrownGFloatingAlt.png',
        '/img/frames/modal/crowns/regular/a.png':
            '/img/frames/modal/crowns/regular/g.png',
        '/img/frames/m15/ub/crowns/floating/a.png':
            '/img/frames/m15/ub/crowns/floating/g.png',
        '/img/frames/m15/oilslick/aCrown.png':
            '/img/frames/m15/oilslick/gCrown.png',
        '/img/frames/m15/praetors/aCrown.png':
            '/img/frames/m15/praetors/gCrown.png',
        '/img/frames/m15/nickname/m15NicknameCrownA.png':
            '/img/frames/m15/nickname/m15NicknameCrownG.png',
        '/img/frames/m15/zendikarRising/m15ZendikarRisingCrownA.png':
            '/img/frames/m15/zendikarRising/m15ZendikarRisingCrownG.png',
    }
    for source,expected in cases.items():
        assert _crown_color_variant(source,'G')==expected
    assert _crown_color_variant('/img/frames/m15/crowns/m15MaskLegendCrown.png','G') is None
    assert _crown_color_variant('/img/frames/m15/crowns/m15CrownFloatingOutline.png','G') is None
    assert _crown_color_variant('/img/frames/m15/innerCrowns/m15InnerCrownANyx.png','G')=='/img/frames/m15/innerCrowns/m15InnerCrownGNyx.png'
    assert _crown_color_variant('/img/frames/m15/mid/bCrown.png','G') is None
    assert _crown_color_variant('/img/frames/dndSourcebook/crown.png','G') is None


def test_compiler_source_is_single_complete_module():
    source=(Path(__file__).resolve().parents[1]/'foundry/compiler.py').read_text(encoding='utf-8')
    assert source.count('class Compiler:')==1
    assert source.count('def apply_universal_frame_color_treatment')==1
    assert source.count('def _crown_color_variant')==1
    compile(source,'foundry/compiler.py','exec')


@pytest.mark.parametrize('source,expected_right,expected_left',[
    (
        '/img/frames/m15/nickname/m15NicknameCrownA.png',
        '/img/frames/m15/nickname/m15NicknameCrownR.png',
        '/img/frames/m15/nickname/m15NicknameCrownU.png',
    ),
    (
        '/img/frames/m15/oilslick/aCrown.png',
        '/img/frames/m15/oilslick/rCrown.png',
        '/img/frames/m15/oilslick/uCrown.png',
    ),
    (
        '/img/frames/m15/praetors/aCrown.png',
        '/img/frames/m15/praetors/rCrown.png',
        '/img/frames/m15/praetors/uCrown.png',
    ),
    (
        '/img/frames/m15/zendikarRising/m15ZendikarRisingCrownA.png',
        '/img/frames/m15/zendikarRising/m15ZendikarRisingCrownR.png',
        '/img/frames/m15/zendikarRising/m15ZendikarRisingCrownU.png',
    ),
])
def test_filename_crown_families_receive_native_dual_layers(source,expected_right,expected_left):
    data={'frames':[{
        'name':'Artifact Legend Crown',
        'src':source,
        'masks':[],
        'bounds':{'x':0.0274,'y':0.0191,'width':0.9454,'height':0.1667},
    }]}
    apply_universal_frame_color_treatment(
        data,{'types':['Creature'],'subtypes':[],'colors':['U','R']}
    )
    crowns=[f for f in data['frames'] if 'Legend Crown' in f.get('name','')]
    assert [f['src'] for f in crowns]==[expected_right,expected_left]
    assert crowns[0]['masks'][0]['name']=='Right Blend'
    assert crowns[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert crowns[1]['masks']==[]


def test_outer_dual_crown_does_not_suppress_inner_crown_coloring():
    outer_right={
        'name':'Red Legend Crown (Right Blend)',
        'src':'/img/frames/m15/crowns/m15CrownR.png',
        'masks':[{'src':'data:image/svg+xml;utf8,OLDMASK','name':'Right Blend'}],
        'bounds':{'height':0.1667,'width':0.9454,'x':0.0274,'y':0.0191},
    }
    outer_left={
        'name':'Blue Legend Crown',
        'src':'/img/frames/m15/crowns/m15CrownU.png',
        'masks':[],
        'bounds':{'height':0.1667,'width':0.9454,'x':0.0274,'y':0.0191},
    }
    inner={
        'name':'Artifact Inner Crown (Nyx)',
        'src':'/img/frames/m15/innerCrowns/new/nyx/a.png',
        'masks':[],
        'bounds':{'x':329/2010,'y':70/2814,'width':1353/2010,'height':64/2814},
    }
    data={'frames':[outer_right,outer_left,inner]}
    apply_universal_frame_color_treatment(
        data,{'types':['Artifact','Enchantment'],'subtypes':[],'colors':['U','R']}
    )

    outer=[f for f in data['frames'] if '/m15/crowns/m15Crown' in str(f.get('src',''))]
    assert outer==[outer_right,outer_left]

    inner_layers=[f for f in data['frames'] if '/innerCrowns/new/nyx/' in str(f.get('src',''))]
    assert [f['src'] for f in inner_layers]==[
        '/img/frames/m15/innerCrowns/new/nyx/r.png',
        '/img/frames/m15/innerCrowns/new/nyx/u.png',
    ]
    assert inner_layers[0]['masks'][0]['name']=='Right Blend'
    assert inner_layers[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert inner_layers[1]['masks']==[]


def test_inner_crown_monocolor_is_universal_too():
    data={'frames':[{
        'name':'Artifact Inner Crown (Companion)',
        'src':'/img/frames/etched/regular/innerCrowns/companion/a.png',
        'masks':[],
        'bounds':{'x':.16,'y':.02,'width':.68,'height':.03},
    }]}
    apply_universal_frame_color_treatment(
        data,{'types':['Artifact'],'subtypes':[],'colors':['G']}
    )
    assert data['frames'][0]['src']=='/img/frames/etched/regular/innerCrowns/companion/g.png'
