import copy,io,json,pytest
from PIL import Image
from foundry.storage import Store
from foundry.images import ingest_image,rarity_variants,sanitize_svg
from foundry.compiler import Compiler,semantic,choose_builtin
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
def test_auto_same_as_v58(workspace):
    from foundry.images import data_uri
    s,a,settings=workspace;c=sf();result=Compiler(s).compile_face(c,c,0,{},settings,a)
    sem=semantic(c,c);sem.update(art=data_uri(s,a),art_local_path=str(s.asset_path(a)),set_symbol_source=data_uri(s,settings['symbols']['rare']))
    expected=native.build_one(sem,{'artist':'Test Artist'},True)['data']
    expected['artSource']='/api/assets/'+a
    expected['setSymbolSource']='/api/assets/'+settings['symbols']['rare']
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
    ordinary=sf('Creature — Human',['U'])
    ordinary_result=comp.compile_face(ordinary,ordinary,0,{},settings,landscape['id'])
    assert ordinary_result['crop']['warning'] and not ordinary_result['crop'].get('intentionalArtWindow')

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
    assert urza_card['faces'][0]['compiled']['group']=='legendary'
    assert might_card['faces'][0]['compiled']['group']=='legendary'
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
