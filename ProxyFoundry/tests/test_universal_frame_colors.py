from foundry.compiler import apply_universal_frame_color_treatment


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
    crown=next(frame for frame in data['frames'] if 'Gradient Legend Crown' in frame.get('name',''))
    assert crown['src']==pinline['src']
    assert crown['masks']==[{'src':'/img/frames/m15/crowns/m15CrownAFloating.png','name':'Legend Crown'}]
    assert crown['ogBounds']=={'x':0,'y':0,'width':1,'height':1}


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


def test_masked_regular_crown_also_uses_dual_gradient():
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
    crown=next(frame for frame in data['frames'] if 'Gradient Legend Crown' in frame.get('name',''))
    pinline=layers(data,'Pinline')[0]
    assert crown['src']==pinline['src']
    assert crown['src'].startswith('data:image/svg+xml;utf8,')
    assert crown['masks']==crown_masks
