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
def test_auto_same_as_v48(workspace):
    from foundry.images import data_uri
    s,a,settings=workspace;c=sf();result=Compiler(s).compile_face(c,c,0,{},settings,a)
    sem=semantic(c,c);sem.update(art=data_uri(s,a),art_local_path=str(s.asset_path(a)),set_symbol_source=data_uri(s,settings['symbols']['rare']))
    expected=native.build_one(sem,{'artist':'Test Artist'},True)['data']
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
def test_exact_printing(workspace):
    s,a,settings=workspace;calls=[];card=sf()
    def transport(url):calls.append(url);return json.dumps(card).encode(),'application/json',{}
    src=Sources(Network(s,transport=transport,sleeper=lambda n:None))
    result=src.import_deck('2 Test Card (TST) 1')
    assert calls==['https://api.scryfall.com/cards/tst/1']
    assert result['cards'][0]['quantity']==2
