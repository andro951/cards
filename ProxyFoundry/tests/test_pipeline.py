import copy,io,json,pytest
from PIL import Image
from foundry.storage import Store
from foundry.images import ingest_image,rarity_variants,sanitize_svg
from foundry.compiler import Compiler,semantic,choose_builtin,align_m15_set_symbol_vertical,FULL_ART_NONLAND_BOUNDS
from foundry.legacy import compiler as native
from foundry.domain import ValidationError
from foundry.sources import Sources
from foundry.network import Network

@pytest.fixture
def workspace(tmp_path):
    s=Store(tmp_path);b=io.BytesIO();Image.new('RGBA',(900,900),'#888888').save(b,'PNG');a=ingest_image(s,b.getvalue());symbols=rarity_variants(s,a['id'])
    return s,a['id'],{'symbols':symbols,'artist':'Test Artist'}
def sf(types='Legendary Creature — Human',colors=['G']):
    return {'id':'00000000-0000-4000-8000-000000000001','name':'Test Card','type_line':types,'mana_cost':'{2}{G}','oracle_text':'Vigilance','colors':colors,'rarity':'rare','power':'2','toughness':'3','set':'tst','collector_number':'1','artist':'Source Artist'}
def test_generated_pinline_red_uses_sampled_mtg_reference_color():
    assert native.DUAL_EASE_SOLID_HEX['R']=='e43c24'
    assert native.DUAL_PALETTE['R'][0]=='e43c24'
    assert 'e43c24' in native.dual_gradient_fill_src('R','U')


def test_auto_same_as_v58(workspace):
    from foundry.images import data_uri
    s,a,settings=workspace;c=sf();result=Compiler(s).compile_face(c,c,0,{},settings,a)
    sem=semantic(c,c);sem.update(art=data_uri(s,a),art_local_path=str(s.asset_path(a)),set_symbol_source=data_uri(s,settings['symbols']['rare']))
    expected=native.build_one(sem,{'artist':'Test Artist'},True)['data']
    expected['artSource']='/api/assets/'+a
    expected['setSymbolSource']='/api/assets/'+settings['symbols']['rare']
    align_m15_set_symbol_vertical(expected,s.asset(settings['symbols']['rare']))
    assert result['data']==expected
@pytest.mark.parametrize('choice',['auto','normal','land','legend-land'])
def test_nonlegendary_choices(workspace,choice):
    s,a,settings=workspace;c=sf('Creature — Human');r=Compiler(s).compile_face(c,c,0,{'templateOverride':choice},settings,a)
    assert r['data']['text']['pt']['text']=='2/3'
    assert len([f for f in r['data']['frames'] if 'Power/Toughness' in f.get('name','')])==1
    assert not any('Legend Crown' in f.get('name','') for f in r['data']['frames'])
def test_legendary_no_invalid_land(workspace):
    s,a,settings=workspace;c=sf()
    with pytest.raises(ValidationError):Compiler(s).compile_face(c,c,0,{'templateOverride':'land'},settings,a)
def test_artist_and_back_hash(workspace):
    s,a,settings=workspace;c=sf();comp=Compiler(s)
    x=comp.compile_face(c,c,0,{},settings,a)
    y=comp.compile_face(c,c,0,{},dict(settings,backAsset='changed'),a)
    assert x['renderKey']==y['renderKey']
    z=comp.compile_face(c,c,0,{'artistOverride':'Other'},settings,a)
    assert x['renderKey']!=z['renderKey']
@pytest.mark.parametrize('raw',[b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'])
def test_active_svg_rejected(raw):
    with pytest.raises(ValidationError):sanitize_svg(raw)

def test_planeswalker_landscape_art_window_crop_does_not_warn(workspace):
    s,_,settings=workspace
    b=io.BytesIO();Image.new('RGB',(1000,600),'#556677').save(b,'PNG');landscape=ingest_image(s,b.getvalue())
    walker={'id':'00000000-0000-4000-8000-000000000099','name':'Walker Test','type_line':'Legendary Planeswalker — Tester','mana_cost':'{2}{U}{U}','oracle_text':'+1: Draw a card.\n-2: Return target creature to its owner\'s hand.\n-7: Draw seven cards.','colors':['U'],'rarity':'mythic','loyalty':'4','artist':'Source Artist'}
    comp=Compiler(s)
    result=comp.compile_face(walker,walker,0,{},settings,landscape['id'],art_origin='Scryfall selected printing')
    assert result['group']=='planeswalker' and result['recipe']=='planeswalker_regular_3'
    assert result['crop']['cropX']>.20 and not result['crop']['warning']
    assert result['crop']['intentionalArtWindow'] is True
    manual=comp.compile_face(walker,walker,0,{'fit':{'artZoom':1.2}},settings,landscape['id'])
    assert manual['crop']['warning'] and not manual['crop'].get('intentionalArtWindow')
    custom=comp.compile_face(walker,walker,0,{},settings,landscape['id'],art_origin='uploaded override')
    assert custom['data']['artBounds']==FULL_ART_NONLAND_BOUNDS
    assert custom['crop']['warning'] and not custom['crop'].get('intentionalArtWindow')
    wide=io.BytesIO();Image.new('RGB',(1600,400),'#775533').save(wide,'PNG');wide_art=ingest_image(s,wide.getvalue())
    ordinary=sf('Creature — Human',['U'])
    ordinary_result=comp.compile_face(ordinary,ordinary,0,{},settings,wide_art['id'])
    assert ordinary_result['crop']['warning'] and not ordinary_result['crop'].get('intentionalArtWindow')

def test_tall_planeswalker_scryfall_keeps_native_art_window_fit(workspace):
    from foundry.images import data_uri
    s,_,settings=workspace
    raw=io.BytesIO();Image.new('RGB',(1000,600),'#445566').save(raw,'PNG')
    art=ingest_image(s,raw.getvalue())
    walker={
        'id':'00000000-0000-4000-8000-000000000198',
        'name':'Tall Walker Test',
        'type_line':'Legendary Planeswalker — Tester',
        'mana_cost':'{3}{U}{U}',
        'oracle_text':'+2: Draw a card.\n+1: Scry 2.\n-3: Return target permanent.\n-8: Draw seven cards.',
        'colors':['U'],'rarity':'mythic','loyalty':'5','artist':'Source Artist',
    }

    sem=semantic(walker,walker,0)
    sem.update(
        art=data_uri(s,art['id']),
        art_local_path=str(s.asset_path(art['id'])),
        set_symbol_source=data_uri(s,settings['symbols']['mythic']),
    )
    expected=native.build_one(copy.deepcopy(sem),{'artist':'Source Artist'},True)['data']

    result=Compiler(s).compile_face(
        walker,walker,0,{},settings,art['id'],art_origin='Scryfall selected printing'
    )
    assert result['group']=='planeswalker'
    assert result['recipe']=='planeswalker_tall_4'
    data=result['data']
    for key in ('artBounds','artX','artY','artZoom','artRotate'):
        assert data[key]==expected[key]
    assert result['crop']['warning'] is False
    assert result['crop']['intentionalArtWindow'] is True


def test_tall_planeswalker_custom_art_uses_shared_full_art_area(workspace):
    s,_,settings=workspace
    raw=io.BytesIO();Image.new('RGB',(1000,1400),'#667788').save(raw,'PNG')
    art=ingest_image(s,raw.getvalue())
    walker={
        'id':'00000000-0000-4000-8000-000000000199',
        'name':'Tall Walker Custom',
        'type_line':'Legendary Planeswalker — Tester',
        'mana_cost':'{3}{U}{U}',
        'oracle_text':'+2: Draw a card.\n+1: Scry 2.\n-3: Return target permanent.\n-8: Draw seven cards.',
        'colors':['U'],'rarity':'mythic','loyalty':'5','artist':'Source Artist',
    }
    result=Compiler(s).compile_face(
        walker,walker,0,{},settings,art['id'],art_origin='uploaded override'
    )
    assert result['recipe']=='planeswalker_tall_4'
    assert result['data']['artBounds']==FULL_ART_NONLAND_BOUNDS
    expected_zoom=(native.CARD_WIDTH-160)/art['width']
    assert result['data']['artZoom']==pytest.approx(expected_zoom)
    assert result['data']['artX']*native.CARD_WIDTH==pytest.approx(80)
    assert not result['crop'].get('intentionalArtWindow')

def test_short_saga_creature_scryfall_art_uses_approved_trim(workspace):
    from foundry.workspace import Workspace
    s,_,settings=workspace
    raw=io.BytesIO();Image.new('RGB',(1000,700),'#345678').save(raw,'PNG')
    card=sf('Enchantment Creature — Saga Leviathan',['U'])
    card.update(
        name='Source Saga',layout='saga',
        oracle_text='I — Test.\nII, III — Test.\nWard {2}',
        image_uris={'art_crop':'https://cards.scryfall.io/source-saga.jpg'},
    )
    def transport(url):
        if url.endswith('source-saga.jpg'):return raw.getvalue(),'image/jpeg',{}
        raise AssertionError(url)
    ws=Workspace(s,Network(s,transport=transport,sleeper=lambda n:None))
    configured={**settings,'source':{'mode':'scryfall','localFiles':{},'fallback':True}}
    art_id,origin,_=ws._art(card,card,{},configured,{}, {})
    stored=s.asset(art_id)
    assert origin=='Scryfall selected printing'
    assert (stored['width'],stored['height'])==(
        1000,
        700-ingest.SAGA_CREATURE_RULES_ART_TRIM_TOP-ingest.SAGA_CREATURE_RULES_ART_TRIM_BOTTOM,
    )


def test_meld_import_uses_real_urza_pair_text_and_physical_half_backs(workspace):
    from foundry.workspace import Workspace
    from foundry.orders import Orders
    s,a,settings=workspace
    urza_id='10000000-0000-4000-8000-000000000001';might_id='10000000-0000-4000-8000-000000000002';result_id='20000000-0000-4000-8000-000000000003'
    parts=[
        {'id':urza_id,'component':'meld_part','name':'Urza, Lord Protector'},
        {'id':might_id,'component':'meld_part','name':'The Mightstone and Weakstone'},
        {'id':result_id,'component':'meld_result','name':'Urza, Planeswalker'}]
    urza={'id':urza_id,'name':'Urza, Lord Protector','layout':'meld','type_line':'Legendary Creature — Human Artificer','mana_cost':'{1}{W}{U}','oracle_text':'Artifact, instant, and sorcery spells you cast cost {1} less to cast.\n{7}: If you both own and control Urza, Lord Protector and an artifact named The Mightstone and Weakstone, exile them, then meld them into Urza, Planeswalker. Activate only as a sorcery.','colors':['W','U'],'rarity':'mythic','power':'2','toughness':'4','set':'bro','collector_number':'225','artist':'Ryan Pancoast','all_parts':parts,'image_uris':{'art_crop':'https://cards.scryfall.io/urza-front.jpg'}}
    might={'id':might_id,'name':'The Mightstone and Weakstone','layout':'meld','type_line':'Legendary Artifact — Powerstone','mana_cost':'{5}','oracle_text':"When The Mightstone and Weakstone enters the battlefield, choose one —\n• Draw two cards.\n• Target creature gets -5/-5 until end of turn.\n{T}: Add {C}{C}. This mana can't be spent to cast nonartifact spells.\n(Melds with Urza, Lord Protector.)",'colors':[],'rarity':'rare','set':'bro','collector_number':'238a','artist':'Ryan Pancoast','all_parts':parts,'image_uris':{'art_crop':'https://cards.scryfall.io/might-front.jpg'}}
    result={'id':result_id,'name':'Urza, Planeswalker','layout':'meld','type_line':'Legendary Planeswalker — Urza','rarity':'mythic','set':'bro','collector_number':'238b','artist':'Ryan Pancoast','all_parts':parts,'image_uris':{'png':'https://cards.scryfall.io/result.png'}}
    front_png=io.BytesIO();Image.new('RGB',(900,650),'#556677').save(front_png,'PNG')
    result_image=Image.new('RGB',(900,1260),'#aa2211');result_image.paste('#1133aa',(0,630,900,1260));result_png=io.BytesIO();result_image.save(result_png,'PNG')
    calls=[]
    def transport(url):
        calls.append(url)
        if url.endswith(urza_id):return json.dumps(urza).encode(),'application/json',{}
        if url.endswith(might_id):return json.dumps(might).encode(),'application/json',{}
        if url.endswith(result_id):return json.dumps(result).encode(),'application/json',{}
        if url.endswith('result.png'):return result_png.getvalue(),'image/png',{}
        return front_png.getvalue(),'image/png',{}
    net=Network(s,transport=transport,sleeper=lambda n:None);ws=Workspace(s,net)
    d=ws.create({'name':'Meld test','source':[{'id':urza_id,'quantity':1},{'id':might_id,'quantity':1}],'settings':settings})
    urza_card,might_card=d['cards']
    assert 'Melds with' not in urza_card['scryfall']['oracle_text']
    assert '(Melds with Urza, Lord Protector.)' in might_card['scryfall']['oracle_text']
    assert urza_card['scryfall']['_meld_result']['name']=='Urza, Planeswalker'
    assert might_card['scryfall']['_meld_result']['name']=='Urza, Planeswalker'
    assert [c['faces'][0]['name'] for c in d['cards']]==['Urza, Lord Protector','The Mightstone and Weakstone']
    d=ws.prepare(d['id']);urza_card,might_card=d['cards']
    assert urza_card['faces'][0]['compiled']['group']=='meld'
    assert might_card['faces'][0]['compiled']['group']=='meld'
    for card in (urza_card,might_card):
        comp=card['faces'][0]['compiled']
        assert comp['recipe']=='m15_meld_front'
        assert comp['templateVersion']==4
        icons=[f for f in comp['data']['frames'] if f.get('name')=='Meld']
        assert icons==[{'name':'Meld','src':'/img/frames/m15/transform/icons/hammer.png','masks':[],'bounds':{'x':0.0594,'y':0.0505,'width':0.0734,'height':0.0524}}]
        assert comp['data']['text']['title']['x']==0.16
    urza_frames=urza_card['faces'][0]['compiled']['data']['frames']
    might_frames=might_card['faces'][0]['compiled']['data']['frames']
    assert any(f.get('src')=='/img/frames/m15/transform/regular/frontM.png' for f in urza_frames)
    assert any(f.get('src')=='/img/frames/m15/transform/regular/frontA.png' for f in might_frames)

    # Urza is a two-color legendary Meld front. The transform-shell conversion
    # must preserve the native W/U layered crown rather than flattening both
    # native crown layers to multicolor/gold before the universal pass.
    urza_crowns=[f for f in urza_frames if '/img/frames/m15/transform/crowns/regular/' in str(f.get('src',''))]
    assert [f['src'] for f in urza_crowns]==[
        '/img/frames/m15/transform/crowns/regular/u.png',
        '/img/frames/m15/transform/crowns/regular/w.png',
    ]
    assert urza_crowns[0]['masks'][0]['name']=='Right Blend'
    assert urza_crowns[0]['masks'][0]['src'].startswith('data:image/svg+xml;utf8,')
    assert urza_crowns[1]['masks']==[]
    urza_pinlines=[
        f for f in urza_frames
        if any(str(m.get('name','')).lower()=='pinline' for m in f.get('masks',[]) if isinstance(m,dict))
    ]
    assert len(urza_pinlines)==1
    assert urza_pinlines[0]['src'].startswith('data:image/svg+xml;utf8,')
    urza_back=s.asset(urza_card['meldBackAsset']);might_back=s.asset(might_card['meldBackAsset'])
    assert (urza_back['width'],urza_back['height'])==(630,900)
    assert (might_back['width'],might_back['height'])==(630,900)
    with Image.open(s.asset_path(urza_card['meldBackAsset'])) as im:assert im.getpixel((100,100))[:3]==(170,34,17)
    with Image.open(s.asset_path(might_card['meldBackAsset'])) as im:assert im.getpixel((100,100))[:3]==(17,51,170)
    for card in (urza_card,might_card):
        comp=card['faces'][0]['compiled'];render=io.BytesIO();Image.new('RGB',(comp['data']['width'],comp['data']['height']),'#334455').save(render,'PNG');ws.save_render(comp['renderKey'],render.getvalue(),(comp['data']['width'],comp['data']['height']))
    plan=Orders(ws).plan([d['id']])
    assert [x['backAsset'] for x in plan['cards']]==[urza_card['meldBackAsset'],might_card['meldBackAsset']]
    assert 'https://cards.scryfall.io/result.png' in calls

def test_exact_printing(workspace):
    s,a,settings=workspace;calls=[];card=sf()
    def transport(url):calls.append(url);return json.dumps(card).encode(),'application/json',{}
    src=Sources(Network(s,transport=transport,sleeper=lambda n:None))
    result=src.import_deck('2 Test Card (TST) 1')
    assert calls==['https://api.scryfall.com/cards/tst/1']
    assert result['cards'][0]['quantity']==2




def test_custom_colorless_clara_covers_full_art_nonland_area_and_centers_overflow(workspace):
    s,_,settings=workspace
    b=io.BytesIO();Image.new('RGB',(1024,1536),'#556677').save(b,'PNG');art=ingest_image(s,b.getvalue())
    clara=sf('Legendary Creature — Human Advisor',[])
    clara.update(name='Clara Oswald',mana_cost='{6}',power='2',toughness='6',oracle_text='Doctor companion test.')
    comp=Compiler(s)

    scryfall=comp.compile_face(clara,clara,0,{},settings,art['id'],art_origin='Scryfall selected printing')
    custom=comp.compile_face(clara,clara,0,{},settings,art['id'],art_origin='GitHub folder')
    data=custom['data']

    assert scryfall['recipe']=='colorless_creature_legendary'
    assert scryfall['data']['artBounds']=={'x':0.0767,'y':0.1129,'width':0.8476,'height':0.4429}
    expected_zoom=1850/1024
    expected_height=1536*expected_zoom
    assert data['artZoom']==pytest.approx(expected_zoom)
    assert data['artX']*data['width']==pytest.approx(80)
    assert data['artY']*data['height']==pytest.approx((2814-expected_height)/2)
    assert data['artBounds']['x']*data['width']==pytest.approx(80)
    assert data['artBounds']['y']*data['height']==pytest.approx(80)
    assert data['artBounds']['width']*data['width']==pytest.approx(1850)
    assert data['artBounds']['height']*data['height']==pytest.approx(2654)


def test_full_art_nonland_centers_only_the_axis_that_overflows():
    from foundry.compiler import full_art_nonland_placement
    portrait=full_art_nonland_placement({'width':1024,'height':1536})
    pzoom=1850/1024
    assert portrait['artX']*2010==pytest.approx(80)
    assert portrait['artY']*2814==pytest.approx((2814-1536*pzoom)/2)
    assert portrait['artZoom']==pytest.approx(pzoom)

    landscape=full_art_nonland_placement({'width':1536,'height':1024})
    lzoom=2654/1024
    assert landscape['artX']*2010==pytest.approx((2010-1536*lzoom)/2)
    assert landscape['artY']*2814==pytest.approx(80)
    assert landscape['artZoom']==pytest.approx(lzoom)

def test_urzas_saga_uses_saga_recipe_instead_of_enchantment_land_recipe(workspace):
    s,a,settings=workspace
    card={
        'id':'00000000-0000-4000-8000-000000000777',
        'name':"Urza's Saga",
        'type_line':"Enchantment Land — Urza's Saga",
        'layout':'normal',
        'mana_cost':'',
        'oracle_text':"(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n"
                      "I — Urza's Saga gains “{T}: Add {C}.”\n"
                      "II — Urza's Saga gains “{2}, {T}: Create a 0/0 colorless Construct artifact creature token with ‘This creature gets +1/+1 for each artifact you control.’”\n"
                      "III — Search your library for an artifact card with mana cost {0} or {1}, put it onto the battlefield, then shuffle.",
        'colors':[],
        'rarity':'rare',
        'set':'mh2',
        'collector_number':'259',
        'artist':'Mark Tedin',
        'produced_mana':['C'],
    }
    result=Compiler(s).compile_face(card,card,0,{},settings,a)
    assert result['group']=='saga'
    assert result['recipe']=='saga'
    assert result['data']['version']=='sagaRegular'
    assert any('/img/frames/saga/' in str(frame.get('src','')) for frame in result['data']['frames'])


def test_morophon_no_longer_forces_wubrg_onto_a_new_line(workspace):
    s,a,settings=workspace
    card=sf('Legendary Creature — Shapeshifter',[])
    card.update(
        name='Morophon, the Boundless',mana_cost='{7}',power='6',toughness='6',
        oracle_text='Changeling (This card is every creature type.)\n'
                    'As Morophon, the Boundless enters, choose a creature type.\n'
                    'Spells of the chosen type you cast cost {W}{U}{B}{R}{G} less to cast. '
                    'This effect reduces only the amount of colored mana you pay.\n'
                    'Other creatures you control of the chosen type get +1/+1.',
    )
    result=Compiler(s).compile_face(card,card,0,{},settings,a)
    rules=result['data']['text']['rules']['text']
    assert result['recipe']=='colorless_creature_legendary'
    assert 'cost {W}{U}{B}{R}{G} less to cast' in rules
    assert 'cost\n{W}{U}{B}{R}{G}' not in rules


@pytest.mark.parametrize('type_line,colors,expected_mask',[
    ('Enchantment — Saga',['U','G'],'/img/frames/saga/sagaMaskPinline.png'),
    ('Enchantment Creature — Saga Dragon',['U','R'],'/img/frames/saga/creature/masks/sagaMaskPinline.png'),
])
def test_dual_color_sagas_use_standard_eased_gradient_pinline(workspace,type_line,colors,expected_mask):
    s,a,settings=workspace
    card=sf(type_line,colors)
    card.update(
        layout='saga',
        oracle_text=('I — Draw a card.\nII — Add one mana.\nIII — Scry 2.'
                     + ('\nWard {2}' if 'Creature' in type_line else '')),
        mana_cost='{1}{U}{G}',
    )
    if 'Creature' in type_line:
        card.update(power='3',toughness='3')
    result=Compiler(s).compile_face(card,card,0,{},settings,a)
    assert result['group'] in {'saga','saga-creature'}
    ordered=native.canonical_dual_color_order(colors)
    expected_src=native.dual_gradient_fill_src(*ordered)
    gradient=[
        frame for frame in result['data']['frames']
        if frame.get('src')==expected_src
        and any(mask.get('src')==expected_mask and mask.get('name')=='Pinline' for mask in frame.get('masks',[]))
    ]
    assert len(gradient)==1
    assert 'Gradient Saga Pinline' in gradient[0]['name']
    tassels=[
        frame for frame in result['data']['frames']
        if any(mask.get('name') in {'Saga Tassel 1','Saga Tassel 2'} for mask in frame.get('masks',[]))
    ]
    assert len(tassels)==2
    first,second=ordered
    by_mask={frame['masks'][0]['name']:frame for frame in tassels}
    assert native.COLOR_NAMES[first] in by_mask['Saga Tassel 1']['name']
    assert native.COLOR_NAMES[second] in by_mask['Saga Tassel 2']['name']
    frames=result['data']['frames']
    assert frames.index(by_mask['Saga Tassel 2']) < frames.index(by_mask['Saga Tassel 1'])
    if result['group']=='saga':
        assert by_mask['Saga Tassel 1']['src']==f'/img/frames/saga/regular/sagaFrame{first}.png'
        assert by_mask['Saga Tassel 2']['src']==f'/img/frames/saga/regular/sagaFrame{second}.png'
        assert by_mask['Saga Tassel 1']['masks'][0]['src']=='/img/frames/saga/sagaMaskBanner.png'
        assert by_mask['Saga Tassel 2']['masks'][0]['src']=='/img/frames/saga/sagaMaskBannerRight.png'
        assert any(frame.get('src')=='/img/frames/saga/regular/sagaFrameM.png' for frame in result['data']['frames'])
    else:
        assert by_mask['Saga Tassel 1']['src']==f'/img/frames/saga/creature/{first.lower()}.png'
        assert by_mask['Saga Tassel 2']['src']==f'/img/frames/saga/creature/{second.lower()}.png'
        assert by_mask['Saga Tassel 1']['masks'][0]['src']=='/img/frames/saga/creature/masks/sagaMaskBanner.png'
        assert by_mask['Saga Tassel 2']['masks'][0]['src']=='/img/frames/saga/creature/masks/sagaMaskBannerRight.png'
        base=next(frame for frame in result['data']['frames'] if frame.get('src')=='/img/frames/saga/creature/m.png')
        assert base['masks']==[]
        assert result['data']['artBounds']=={
            'x':1009/native.CARD_WIDTH,'y':588/native.CARD_HEIGHT,
            'width':844/native.CARD_WIDTH,'height':1533/native.CARD_HEIGHT,
        }
        assert result['data']['text']['rules2']['text']=='Ward {2}'
        assert result['data']['text']['rules2']['y']==2333/native.CARD_HEIGHT
        assert any(frame.get('src')=='/img/frames/m15/regular/m15PTM.png' for frame in result['data']['frames'])

def test_saga_creature_short_frame_regex_matches_real_asset_paths():
    import re
    pattern=r'/img/frames/saga/creature/[wubrgmcl]\.png'
    assert re.fullmatch(pattern,'/img/frames/saga/creature/u.png')
    assert re.fullmatch(pattern,'/img/frames/saga/creature/m.png')
    assert not re.fullmatch(pattern,'/img/frames/saga/creature/u\\.png')


def test_summon_leviathan_signature_uses_short_creature_saga_frame(workspace):
    s,a,settings=workspace
    card=sf('Enchantment Creature — Saga Leviathan',['U'])
    card.update(
        name='Summon: Leviathan',layout='saga',mana_cost='{4}{U}{U}',
        power='6',toughness='6',
        oracle_text=(
            '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n'
            "I — Return each creature that isn't a Kraken, Leviathan, Merfolk, Octopus, or Serpent to its owner's hand.\n"
            'II, III — Until end of turn, whenever a Kraken, Leviathan, Merfolk, Octopus, or Serpent attacks, draw a card.\n'
            'Ward {2}'
        ),
    )
    result=Compiler(s).compile_face(card,card,0,{},settings,a)
    assert result['group']=='saga-creature'
    assert result['recipe']=='saga_creature'
    data=result['data']
    frame=next(f for f in data['frames'] if f.get('src')=='/img/frames/saga/creature/u.png')
    assert frame['masks']==[]
    assert data['artBounds']=={
        'x':1009/native.CARD_WIDTH,'y':588/native.CARD_HEIGHT,
        'width':844/native.CARD_WIDTH,'height':1533/native.CARD_HEIGHT,
    }
    assert data['text']['rules2']['text']=='Ward {2}'
    assert data['text']['rules2']['y']==2333/native.CARD_HEIGHT
    expected_zoom=1533/900
    scaled_w=900*expected_zoom
    assert data['artZoom']==pytest.approx(expected_zoom)
    assert data['artX']*native.CARD_WIDTH==pytest.approx(1009+(844-scaled_w)/2)
    assert data['artY']*native.CARD_HEIGHT==pytest.approx(588)
    assert result['crop']['cropX']>0
    assert result['crop']['cropY']==0
    # Default/direct test art is custom. Cover-fit may crop it, but custom art
    # must retain the normal review warning.
    assert result['crop']['warning'] is True
    assert not result['crop'].get('scryfallShortSagaFit')


def test_short_saga_scryfall_uses_centered_cover_fit_and_skips_review_warning(workspace):
    s,_,settings=workspace
    # Model the already-trimmed Scryfall art passed from Workspace._art().
    trimmed_h=700-ingest.SAGA_CREATURE_RULES_ART_TRIM_TOP-ingest.SAGA_CREATURE_RULES_ART_TRIM_BOTTOM
    raw=io.BytesIO();Image.new('RGB',(1000,trimmed_h),'#345678').save(raw,'PNG')
    art=ingest_image(s,raw.getvalue())
    card=sf('Enchantment Creature — Saga Leviathan',['U'])
    card.update(
        name='Scryfall Summon',layout='saga',mana_cost='{4}{U}{U}',power='6',toughness='6',
        oracle_text='I — Test chapter.\nII, III — Test chapter.\nWard {2}',
    )
    result=Compiler(s).compile_face(
        card,card,0,{},settings,art['id'],art_origin='Scryfall selected printing'
    )
    data=result['data'];bounds=data['artBounds']
    window_x=bounds['x']*data['width'];window_y=bounds['y']*data['height']
    window_w=bounds['width']*data['width'];window_h=bounds['height']*data['height']
    scaled_w=art['width']*data['artZoom'];scaled_h=art['height']*data['artZoom']
    assert scaled_w>=window_w-1e-6
    assert scaled_h>=window_h-1e-6
    assert min(abs(scaled_w-window_w),abs(scaled_h-window_h))==pytest.approx(0,abs=1e-6)
    assert data['artX']*data['width']==pytest.approx(window_x+(window_w-scaled_w)/2)
    assert data['artY']*data['height']==pytest.approx(window_y+(window_h-scaled_h)/2)
    assert result['crop']['warning'] is False
    assert result['crop']['scryfallShortSagaFit'] is True


def test_saga_creature_cover_fit_uses_width_when_source_is_tall(workspace):
    s,_,settings=workspace
    raw=io.BytesIO();Image.new('RGBA',(500,1400),'#56789a').save(raw,'PNG')
    art=ingest_image(s,raw.getvalue())
    card=sf('Enchantment Creature — Saga Leviathan',['U'])
    card.update(
        name='Tall Summon',layout='saga',mana_cost='{4}{U}{U}',power='6',toughness='6',
        oracle_text=(
            '(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\n'
            'I — Test chapter.\nII, III — Test chapter.\nWard {2}'
        ),
    )
    result=Compiler(s).compile_face(card,card,0,{},settings,art['id'])
    data=result['data']
    expected_zoom=844/500
    scaled_h=1400*expected_zoom
    assert data['artZoom']==pytest.approx(expected_zoom)
    assert data['artX']*native.CARD_WIDTH==pytest.approx(1009)
    assert data['artY']*native.CARD_HEIGHT==pytest.approx(588+(1533-scaled_h)/2)
    assert result['crop']['cropX']==0
    assert result['crop']['cropY']>0
    assert result['crop']['warning'] is True
    assert not result['crop'].get('scryfallShortSagaFit')


def test_doctor_who_saga_chapter_groupings_and_ability_boxes():
    from foundry.legacy import compiler as native
    cases=[
      ('An Unearthly Child','(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II, III — Reveal cards from the top of your library until you reveal a Doctor card.',(3,),[3,0,0,0],1),
      ('The Girl in the Fireplace','(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create a 1/1 white Human Noble creature token.\nII — Create a 2/2 white Horse creature token.\nIII — Whenever a creature you control deals combat damage to a player this turn, time travel.',(1,1,1),[1,1,1,0],3),
      ('Trial of a Time Lord','(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III — Exile target nontoken creature an opponent controls until this Saga leaves the battlefield.\nIV — Starting with you, each player votes for innocent or guilty.',(3,1),[3,1,0,0],2),
      ('Death in Heaven','(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Target player mills two cards, then exiles their graveyard.\nIII — Put all creature cards exiled with Death in Heaven onto the battlefield face down under your control.',(2,1),[2,1,0,0],2),
    ]
    for name,oracle,signature,chapter_groups,ability_count in cases:
        card={'name':name,'type_line':'Enchantment — Saga','layout':'saga','colors':['W'],'mana_cost':'{2}{W}','oracle_text':oracle}
        meta=native.saga_layout_metadata(card)
        assert meta['signature']==signature
        data=native.recipe_data('saga',card,native.get_type_info(card))['data']
        native.apply_saga_text_layout(data,meta)
        assert data['saga']['abilities']==chapter_groups
        assert data['saga']['count']==ability_count
        assert sum(1 for i in range(4) if data['text'][f'ability{i}']['height']>0)==ability_count


def test_normal_scryfall_creature_token_uses_real_token_frame(workspace):
    s,a,settings=workspace
    beast={
        'id':'90000000-0000-4000-8000-000000000001',
        'name':'Beast','layout':'token','type_line':'Token Creature — Beast',
        'mana_cost':'','oracle_text':'','colors':['G'],'rarity':'common',
        'power':'3','toughness':'3','set':'ttst','collector_number':'1',
        'artist':'Token Artist',
    }
    result=Compiler(s).compile_face(beast,beast,0,{},settings,a,art_origin='Scryfall selected printing')
    data=result['data']
    assert result['group']=='token'
    assert result['recipe']=='token_regular'
    assert result['templateVersion']==2
    assert data['version']=='tokenRegular'
    assert data['text']['title']['text']=='Beast'
    assert data['text']['type']['text']=='Token Creature — Beast'
    assert data['text']['pt']['text']=='3/3'
    token=[f for f in data['frames'] if f.get('name')=='Green Token Frame']
    assert len(token)==1
    assert token[0]['src']=='/img/frames/token/regular/tokenFrameGRegular.png'
    assert {m['name'] for m in token[0]['masks']}=={'Pinline','Title','Type','Rules','Border','Bevel'}
    pt=[f for f in data['frames'] if 'Power/Toughness' in f.get('name','')]
    assert len(pt)==1 and pt[0]['src']=='/img/frames/m15/regular/m15PTG.png'
    assert data['artBounds']=={'x':0.04,'y':0.0286,'width':0.92,'height':0.8953}


def test_normal_scryfall_noncreature_token_keeps_rules_and_artifact_frame(workspace):
    s,a,settings=workspace
    treasure={
        'id':'90000000-0000-4000-8000-000000000002',
        'name':'Treasure','layout':'token','type_line':'Token Artifact — Treasure',
        'mana_cost':'','oracle_text':'{T}, Sacrifice this artifact: Add one mana of any color.',
        'colors':[],'rarity':'common','set':'ttst','collector_number':'2',
        'artist':'Token Artist',
    }
    result=Compiler(s).compile_face(treasure,treasure,0,{},settings,a,art_origin='Scryfall selected printing')
    data=result['data']
    assert result['group']=='token' and result['recipe']=='token_regular'
    assert data['text']['rules']['text']=='{T}, Sacrifice this artifact: Add one mana of any color.'
    assert any(f.get('src')=='/img/frames/token/regular/tokenFrameARegular.png' for f in data['frames'])
    assert not any('Power/Toughness' in f.get('name','') for f in data['frames'])


def test_two_color_legendary_token_still_gets_universal_dual_crown_and_pinline(workspace):
    s,a,settings=workspace
    token={
        'id':'90000000-0000-4000-8000-000000000003',
        'name':'Hero','layout':'token','type_line':'Legendary Token Creature — Human',
        'mana_cost':'','oracle_text':'Vigilance','colors':['W','U'],'rarity':'rare',
        'power':'2','toughness':'2','set':'ttst','collector_number':'3',
        'artist':'Token Artist',
    }
    data=Compiler(s).compile_face(token,token,0,{},settings,a)['data']
    pinline=next(f for f in data['frames'] if any(
        'pinline' in str(m.get('name','')).lower() for m in f.get('masks',[]) if isinstance(m,dict)
    ))
    assert pinline['src'].startswith('data:image/svg+xml;utf8,')
    crowns=[f for f in data['frames'] if 'Legend Crown' in f.get('name','') and 'Outline' not in f.get('name','') and 'Border' not in f.get('name','') and 'Cutout' not in f.get('name','')]
    assert len(crowns)==2
    assert crowns[0]['masks'][0]['name']=='Right Blend'
