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
def test_meld_import_uses_result_as_back_without_rendering_result(workspace):
    from foundry.workspace import Workspace
    from foundry.orders import Orders
    s,a,settings=workspace
    front_id='10000000-0000-4000-8000-000000000001';result_id='20000000-0000-4000-8000-000000000002'
    parts=[{'id':front_id,'component':'meld_part','name':'Urza, Lord Protector'},{'id':result_id,'component':'meld_result','name':'Urza, Planeswalker'}]
    front={'id':front_id,'name':'Urza, Lord Protector','layout':'meld','type_line':'Legendary Creature — Human Artificer','mana_cost':'{1}{W}{U}','oracle_text':'Artifact, instant, and sorcery spells you cast cost {1} less to cast. {7}: If you both own and control Urza, Lord Protector and an artifact named The Mightstone and Weakstone, exile them, then meld them into Urza, Planeswalker.','colors':['W','U'],'rarity':'mythic','power':'2','toughness':'4','set':'bro','collector_number':'225','artist':'Front Artist','all_parts':parts,'image_uris':{'art_crop':'https://cards.scryfall.io/front.jpg'}}
    result={'id':result_id,'name':'Urza, Planeswalker','layout':'meld','type_line':'Legendary Planeswalker — Urza','rarity':'mythic','set':'bro','collector_number':'238b','artist':'Back Artist','all_parts':parts,'image_uris':{'png':'https://cards.scryfall.io/result.png'}}
    front_png=io.BytesIO();Image.new('RGB',(900,650),'#556677').save(front_png,'PNG')
    result_image=Image.new('RGB',(900,1260),'#aa2211');result_image.paste('#1133aa',(0,630,900,1260));result_png=io.BytesIO();result_image.save(result_png,'PNG')
    calls=[]
    def transport(url):
        calls.append(url)
        if url.endswith(front_id):return json.dumps(front).encode(),'application/json',{}
        if url.endswith(result_id):return json.dumps(result).encode(),'application/json',{}
        if url.endswith('result.png'):return result_png.getvalue(),'image/png',{}
        return front_png.getvalue(),'image/png',{}
    net=Network(s,transport=transport,sleeper=lambda n:None);ws=Workspace(s,net)
    d=ws.create({'name':'Meld test','source':[{'id':front_id,'quantity':1}],'settings':settings});card=d['cards'][0]
    assert card['scryfall']['_meld_result']['name']=='Urza, Planeswalker'
    assert len(card['faces'])==1 and card['faces'][0]['name']=='Urza, Lord Protector'
    d=ws.prepare(d['id']);card=d['cards'][0];face=card['faces'][0]
    assert face['compiled']['group']=='legendary' and face['compiled']['name']=='Urza, Lord Protector'
    assert card.get('meldBackAsset') and s.asset(card['meldBackAsset'])
    meld_asset=s.asset(card['meldBackAsset']);assert (meld_asset['width'],meld_asset['height'])==(630,900)
    with Image.open(s.asset_path(card['meldBackAsset'])) as meld_image:assert meld_image.getpixel((100,100))[:3]==(170,34,17)
    bottom_sf={**front,'oracle_text':'(Melds with Urza, Lord Protector.)','_meld_result':card['scryfall']['_meld_result']}
    bottom_id=ws._meld_back(bottom_sf);bottom_asset=s.asset(bottom_id);assert (bottom_asset['width'],bottom_asset['height'])==(630,900)
    with Image.open(s.asset_path(bottom_id)) as bottom_image:assert bottom_image.getpixel((100,100))[:3]==(17,51,170)
    comp=face['compiled'];render=io.BytesIO();Image.new('RGB',(comp['data']['width'],comp['data']['height']),'#334455').save(render,'PNG');ws.save_render(comp['renderKey'],render.getvalue(),(comp['data']['width'],comp['data']['height']))
    plan=Orders(ws).plan([d['id']]);assert plan['cards'][0]['backAsset']==card['meldBackAsset']
    assert 'https://cards.scryfall.io/result.png' in calls

def test_exact_printing(workspace):
    s,a,settings=workspace;calls=[];card=sf()
    def transport(url):calls.append(url);return json.dumps(card).encode(),'application/json',{}
    src=Sources(Network(s,transport=transport,sleeper=lambda n:None))
    result=src.import_deck('2 Test Card (TST) 1')
    assert calls==['https://api.scryfall.com/cards/tst/1']
    assert result['cards'][0]['quantity']==2
