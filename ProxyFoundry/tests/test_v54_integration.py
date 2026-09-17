"""Guard supplied v54 behavior, not a recreated approximation of its templates."""
import copy, hashlib, io, json
from pathlib import Path
import pytest
from PIL import Image
from foundry.compiler import Compiler, semantic, M15_SET_SYMBOL_VERTICAL_CENTER
from foundry.credits import SCRYFALL_ART
from foundry.domain import GENERATION_VERSION, ValidationError
from foundry.images import ingest_image, data_uri
from foundry.legacy import compiler as native, ingest
from foundry.network import Network
from foundry.orders import Orders
from foundry.storage import Store
from foundry.workspace import Workspace


def png(size=(1200,1000),color='#8599bd'):
    b=io.BytesIO();Image.new('RGB',size,color).save(b,'PNG');return b.getvalue()


def sf(name='A Card',**changes):
    return {'id':'11111111-1111-4111-8111-111111111111','name':name,'layout':'normal',
        'type_line':'Creature — Elf','colors':['G'],'mana_cost':'{1}{G}',
        'oracle_text':'Vigilance','power':'2','toughness':'2','rarity':'rare','artist':'Actual Artist',
        'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/image.jpg'},**changes}


@pytest.fixture
def env(tmp_path):
    store=Store(tmp_path);record=sf()
    def remote(url):
        if 'api.scryfall.com' in url:return json.dumps(record).encode(),'application/json',{}
        return png(),'image/png',{}
    net=Network(store,transport=remote,sleeper=lambda _:None)
    w=Workspace(store,net);a=ingest_image(store,png());sym=ingest_image(store,png((640,300)))
    settings={'symbols':{r:sym['id'] for r in ['common','uncommon','rare','mythic']},'artist':'Custom Artist','backAsset':a['id']}
    return w,record,a,settings


def test_vendor_exact_manifest():
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'docs/CARD_TOOLS_V58_MANIFEST.json').read_text())
    for name,expected in manifest['files'].items():
        assert hashlib.sha256((root/'vendor/card_tools'/name).read_bytes()).hexdigest()==expected['sha256'],name


@pytest.mark.parametrize('origin',[SCRYFALL_ART,'GitHub folder','computer folder','uploaded override'])
def test_source_driven_credit_kept_through_compiler_and_export(env,origin):
    w,c,a,s=env;s={**s,'modificationCredit':'Modified by ChatGPT'}
    r=w.compiler.compile_face(c,c,0,{'artistOverride':'Face Override'},s,a['id'],art_origin=origin)
    expected=('Actual Artist' if origin==SCRYFALL_ART else 'Face Override')+' · Modified by ChatGPT'
    assert r['artist']==r['credit']['display']==r['data']['infoArtist']==expected
    entry=w.sources.entry(c);entry['faces'][0]['compiled']=r
    d=w.store.put('decks',{'name':'Credits','status':'prepared','cards':[entry],'settings':s})
    assert json.loads(w.export_cc([d['id']]))[0]['data']['infoArtist']==expected


def test_scryfall_fallback_ignores_custom_deck_artist(env):
    w,c,a,s=env
    s={**s,'source':{'mode':'local','localFiles':{},'fallback':True},'modificationCredit':'Modified by ChatGPT'}
    d=w.create({'source':[{'id':c['id']}],'settings':s});d=w.prepare(d['id'])
    f=d['cards'][0]['faces'][0]
    assert f['compiled']['artOrigin']==SCRYFALL_ART
    assert f['compiled']['data']['infoArtist']=='Actual Artist · Modified by ChatGPT'
    assert c['artist']=='Actual Artist'


def test_local_custom_and_scryfall_art_in_same_deck_have_separate_credits(env):
    w,c,a,s=env
    s={**s,'source':{'mode':'local','localFiles':{'a_card':a['id']},'fallback':True},'modificationCredit':'Modified by ChatGPT'}
    d=w.create({'source':[{'id':c['id']}],'settings':s});d=w.prepare(d['id'])
    assert d['cards'][0]['faces'][0]['compiled']['data']['infoArtist']=='Custom Artist · Modified by ChatGPT'
    d=w.save(d['id'],{'revision':d['revision'],'settings':{'source':{'mode':'local','localFiles':{},'fallback':True}}});d=w.prepare(d['id'])
    assert d['cards'][0]['faces'][0]['compiled']['data']['infoArtist']=='Actual Artist · Modified by ChatGPT'


def test_old_generation_cannot_be_ordered_as_current(env):
    w,c,a,s=env;r=w.compiler.compile_face(c,c,0,{},s,a['id'])
    r.pop('generationVersion');w.store.render_put(r['renderKey'],a)
    entry=w.sources.entry(c);entry['faces'][0]['compiled']=r
    d=w.store.put('decks',{'name':'Old v48 output','status':'prepared','cards':[entry],'settings':s})
    assert w.deck(d['id'])['status']=='draft'
    assert w.deck(d['id'])['upgradeRequired']
    with pytest.raises(ValidationError,match='prepare'):Orders(w).plan([d['id']])
    assert w.store.render_get(r['renderKey']) # No historical PNG deleted.


def test_modification_changes_hash_but_back_quantity_do_not(env):
    w,c,a,s=env
    r=w.compiler.compile_face(c,c,0,{},s,a['id'],art_origin=SCRYFALL_ART)
    r2=w.compiler.compile_face(c,c,0,{},dict(s,backAsset='other',quantity=12),a['id'],art_origin=SCRYFALL_ART)
    r3=w.compiler.compile_face(c,c,0,{'modificationCreditOverride':'Modified by ChatGPT'},s,a['id'],art_origin=SCRYFALL_ART)
    assert r['renderKey']==r2['renderKey']!=r3['renderKey']


def test_modified_custom_template_keeps_geometry(env):
    w,c,a,s=env
    data=copy.deepcopy(native.LAYOUTS['creature']['data']);data['setSymbolX']=.68;data['text']['type']['width']=.5
    t=w.save_template({'data':data,'groups':['standard'],'name':'My untouched layout'})
    r=w.compiler.compile_face(c,c,0,{'templateOverride':t['id'],'modificationCreditOverride':'Modified by ChatGPT'},s,a['id'],art_origin=SCRYFALL_ART)
    assert r['data']['setSymbolX']==.68 and r['data']['text']['type']['width']==.5
    assert r['data']['infoArtist']=='Actual Artist · Modified by ChatGPT'


def flip_record():
    c=sf('Budoka Gardener // Dokai, Weaver of Life',layout='flip',card_faces=[
        {'name':'Budoka Gardener','type_line':'Creature — Human Monk','colors':['G'],'mana_cost':'{1}{G}','power':'2','toughness':'1','oracle_text':'Flip test upright rules.','flavor_text':'Top flavor','artist':'Flip Artist'},
        {'name':'Dokai, Weaver of Life','type_line':'Legendary Creature — Human Monk','colors':['G'],'mana_cost':'','power':'3','toughness':'3','oracle_text':'Flip test lower rules.','flavor_text':'Lower flavor','artist':'Flip Artist'}])
    return c


def test_flip_is_single_output_not_reverse(env):
    w,_,a,s=env;c=flip_record();entry=w.sources.entry(c,2)
    assert len(entry['faces'])==1
    result=w.compiler.compile_face(c,c['card_faces'][0],0,{},s,a['id'],art_origin=SCRYFALL_ART)
    data=result['data'];assert result['recipe']=='flip' and data['version']=='flip'
    assert data['text']['title2']['text']=='Dokai, Weaver of Life'
    assert data['text']['rules2']['rotation']==180
    assert data['text']['pt']['text']=='2/1' and data['text']['pt2']['text']=='3/3'
    assert sum('Flip Power/Toughness' in f.get('name','') for f in data['frames'])==2
    entry['faces'][0]['compiled']=result;w.store.render_put(result['renderKey'],a)
    d=w.store.put('decks',{'name':'One flip card','cards':[entry],'settings':s,'status':'prepared'})
    order=Orders(w).plan([d['id']]);assert order['count']==2
    assert all(x['backAsset']==s['backAsset'] for x in order['cards'])


def test_flip_ingestion_matches_supplied_nested_semantics():
    c=flip_record();sem=semantic(c,c['card_faces'][0])
    expected=ingest.build_nested_face_semantic(c,c['card_faces'][1],c['card_faces'][1],{})
    assert sem['flip_face']==expected


def test_iron_man_normal_artifact_recipe(env):
    w,_,a,s=env;c=sf('Iron Man, Titan of Innovation',type_line='Legendary Artifact Creature — Human',colors=['U','R'],mana_cost='{3}{U}{R}',power='4',toughness='4')
    r=w.compiler.compile_face(c,c,0,{},s,a['id'])
    assert r['recipe']!='iron_man_fullart_dual_creature'
    assert r['data']['version']=='m15Regular'
    assert r['recipe']==native.infer_layout(semantic(c,c),native.get_type_info(semantic(c,c)))


@pytest.mark.parametrize('legendary',[False,True])
def test_multicolor_vehicle_bars_are_gold_body_stays_vehicle(env,legendary):
    w,_,a,s=env;c=sf('Vehicle',type_line=('Legendary ' if legendary else '')+'Artifact — Vehicle',colors=['U','R'])
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    for f in d['frames']:
        if {'Title','Type'} & {m['name'] for m in f['masks']}:
            assert f['src'].endswith('m15FrameM.png')
    assert any('Vehicle' in f.get('name','') for f in d['frames'])


@pytest.mark.parametrize('name,type_line,layout',[
    ('Creature','Creature — Elf','normal'),('Artifact','Artifact','normal'),
    ('Land','Land','normal'),('Legendary Land','Legendary Land','normal')])
def test_symbol_right_edge_and_type_gap(env,name,type_line,layout):
    w,_,a,s=env;c=sf(name,type_line=type_line,layout=layout)
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data'];sym=w.store.asset(s['symbols']['rare'])
    width=sym['width']*d['setSymbolZoom']/d['width'];height=sym['height']*d['setSymbolZoom']/d['height']
    box=d['text']['type'];center=d['setSymbolY']+height/2
    if d.get('version')=='m15Regular':
        cw=d['width'];ch=d['height'];bounds=d['setSymbolBounds']
        rendered_w=sym['width']*d['setSymbolZoom'];rendered_h=sym['height']*d['setSymbolZoom']
        bounds_w=round(bounds['width']*cw);bounds_h=round(bounds['height']*ch)
        assert rendered_w<=bounds_w+.6 and rendered_h<=bounds_h+.6
        assert min(abs(rendered_w-bounds_w),abs(rendered_h-bounds_h))<=1.5
        assert d['setSymbolX']*cw+rendered_w==pytest.approx(round(bounds['x']*cw),abs=.6)
        assert center*ch==pytest.approx(round(M15_SET_SYMBOL_VERTICAL_CENTER*ch),abs=.7)
        assert bounds['y']==pytest.approx(M15_SET_SYMBOL_VERTICAL_CENTER)
    else:
        assert d['setSymbolX']+width==pytest.approx(.9213)
        assert center==pytest.approx(box['y']+box['height']/2)
    assert (d['setSymbolX']-(box['x']+box['width']))*d['width']==pytest.approx(.01*d['width'],abs=.6)


def test_m15_symbol_fit_matches_cardconjurer_reset_for_cropped_mythic(env):
    w,c,a,s=env
    raw=io.BytesIO();Image.new('RGBA',(869,1057),'#ff6600').save(raw,'PNG')
    symbol=ingest_image(w.store,raw.getvalue());s={**s,'symbols':{r:symbol['id'] for r in ['common','uncommon','rare','mythic']}}
    c=sf('Sol Ring',type_line='Artifact',colors=[],rarity='mythic')
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    assert d['version']=='m15Regular'
    assert d['setSymbolZoom']==pytest.approx(.109)
    assert d['setSymbolX']*2010==pytest.approx(1757)
    assert d['setSymbolY']*2814==pytest.approx(1606)
    assert 869*d['setSymbolZoom']==pytest.approx(94.721)
    assert 1057*d['setSymbolZoom']==pytest.approx(115.213)
    assert d['setSymbolY']*2814+(1057*d['setSymbolZoom'])/2==pytest.approx(1664,abs=.7)


def test_dfc_artist_is_per_face_and_does_not_follow_other_side(env):
    w,_,a,s=env
    front={'name':'Esika, God of the Tree','type_line':'Legendary Creature — God','colors':['G'],'power':'1','toughness':'4','mana_cost':'{1}{G}{G}','oracle_text':'Vigilance','artist':'Front Illustrator'}
    back={'name':'The Prismatic Bridge','type_line':'Legendary Enchantment','colors':['W','U','B','R','G'],'mana_cost':'{W}{U}{B}{R}{G}','oracle_text':'Upkeep test.','artist':'Back Illustrator'}
    record={'name':front['name']+' // '+back['name'],'layout':'modal_dfc','rarity':'mythic','card_faces':[front,back],'artist':'Top-Level Credit'}
    s=dict(s,modificationCredit='Modified by ChatGPT')
    for i,face in enumerate(record['card_faces']):
        r=w.compiler.compile_face(record,face,i,{},s,a['id'],art_origin=SCRYFALL_ART)
        assert r['data']['infoArtist']==face['artist']+' · Modified by ChatGPT'


def test_credit_fields_survive_style_defaults_duplicate_and_backup(env):
    from foundry.backup import Backups
    w,c,a,s=env;s=dict(s,modificationCredit='Modified by ChatGPT')
    w.set_global_settings({'defaults':s})
    d=w.create({'source':[{'id':c['id']}], 'name':'Credits saved'})
    f=d['cards'][0]['faces'][0]
    d=w.mutate_card(d['id'],d['cards'][0]['id'],{'revision':d['revision'],'faceId':f['id'],'artistCreditMode':'printing','modificationCreditOverride':'Extended by Isaac'})
    duplicated=w.duplicate(d['id'])
    assert duplicated['settings']['modificationCredit']=='Modified by ChatGPT'
    assert duplicated['cards'][0]['faces'][0]['modificationCreditOverride']=='Extended by Isaac'
    backups=Backups(w);out=backups.export();result=backups.restore(w.store.home/'backups'/out['filename'])
    restored=w.deck(result['ids'][0])
    assert restored['cards'][0]['faces'][0]['artistCreditMode']=='printing'
    assert restored['cards'][0]['faces'][0]['modificationCreditOverride']=='Extended by Isaac'
