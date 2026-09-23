"""Guard supplied v54 behavior, not a recreated approximation of its templates."""
import copy, hashlib, io, json
from pathlib import Path
import pytest
from PIL import Image
from foundry.compiler import Compiler, semantic, M15_SET_SYMBOL_VERTICAL_CENTER, fit_set_symbol_to_bounds, _standard_visible_type_bar, SET_SYMBOL_RECIPE_Y_OFFSET_PX, normalize_scryfall_inline_italics
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


def test_scryfall_inline_flavor_italics_render_without_literal_asterisks(env):
    w,_,a,s=env
    flavor='"Scouts of the Sakura Tribe spent two years wandering the forest."\n—*The History of Kamigawa*'
    assert normalize_scryfall_inline_italics(flavor).endswith('—{i}The History of Kamigawa{/i}')
    c=sf('Sakura-Tribe Scout',type_line='Creature — Snake Shaman Scout',colors=['G'],
         mana_cost='{G}',oracle_text='{T}: You may put a land card from your hand onto the battlefield.',
         flavor_text=flavor,power='1',toughness='1')
    data=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    rendered=data['text']['rules']['text']
    assert '—{i}The History of Kamigawa{/i}' in rendered
    assert '*The History of Kamigawa*' not in rendered


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
    accents=[f for f in r['data']['frames'] if {'Title','Type','Rules'} & {m['name'] for m in f.get('masks',[])}]
    assert len(accents)==3
    assert all(f['src'].endswith('m15FrameM.png') for f in accents)
    pinline=next(f for f in r['data']['frames'] if 'Pinline' in {m['name'] for m in f.get('masks',[])})
    assert pinline['src'].startswith('data:image/svg+xml;utf8,')
    body=[f for f in r['data']['frames'] if 'Frame' in {m['name'] for m in f.get('masks',[])}]
    assert body and all(f['src'].endswith('m15FrameA.png') for f in body)


@pytest.mark.parametrize('colors,expected',[([], 'A'),(['U'],'U'),(['W'],'W'),(['U','R'],'M'),(['W','U','B'],'M')])
def test_artifact_muted_title_type_and_rules_follow_card_color_but_body_stays_metallic(env,colors,expected):
    w,_,a,s=env
    c=sf('Colored Artifact',type_line='Artifact — Equipment',colors=colors,mana_cost='',power=None,toughness=None)
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    for piece in ('Title','Type','Rules'):
        matches=[f for f in d['frames'] if piece in {m['name'] for m in f.get('masks',[])}]
        assert len(matches)==1
        assert matches[0]['src'].endswith(f'm15Frame{expected}.png')
    body=[f for f in d['frames'] if 'Frame' in {m['name'] for m in f.get('masks',[])}]
    assert body and all(f['src'].endswith('m15FrameA.png') for f in body)


def test_two_color_legendary_crown_and_pinline_share_universal_gradient(env):
    w,_,a,s=env
    c=sf('Dual Legend',type_line='Legendary Creature — Human Wizard',colors=['U','R'],mana_cost='{1}{U}{R}',power='3',toughness='3')
    data=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    pinline=next(f for f in data['frames'] if any(
        'pinline' in str(m.get('name','')).lower() for m in f.get('masks',[]) if isinstance(m,dict)
    ))
    crown=next(f for f in data['frames'] if 'Gradient Legend Crown' in f.get('name',''))
    assert pinline['src'].startswith('data:image/svg+xml;utf8,')
    assert crown['src']==pinline['src']
    for effect in ('Title','Type','Rules'):
        layers=[f for f in data['frames'] if effect in {m.get('name') for m in f.get('masks',[]) if isinstance(m,dict)}]
        assert layers and all(f['src'].endswith('m15FrameM.png') for f in layers)


def test_colored_artifact_creature_keeps_metallic_pt_box(env):
    w,_,a,s=env
    c=sf('Colored Artifact Creature',type_line='Artifact Creature — Construct',colors=['R'],mana_cost='{2}{R}',power='3',toughness='3')
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    accents=[f for f in d['frames'] if {'Title','Type','Rules'} & {m['name'] for m in f.get('masks',[])}]
    assert len(accents)==3 and all(f['src'].endswith('m15FrameR.png') for f in accents)
    pinline=next(f for f in d['frames'] if 'Pinline' in {m['name'] for m in f.get('masks',[])})
    assert pinline['src'].endswith('m15FrameR.png')
    pt=[f for f in d['frames'] if 'power/toughness' in f.get('name','').lower()]
    assert len(pt)==1 and pt[0]['src'].endswith('m15PTA.png')


@pytest.mark.parametrize('legendary',[False,True])
def test_multicolor_vehicle_bars_are_gold_body_stays_vehicle(env,legendary):
    w,_,a,s=env;c=sf('Vehicle',type_line=('Legendary ' if legendary else '')+'Artifact — Vehicle',colors=['U','R'])
    d=w.compiler.compile_face(c,c,0,{},s,a['id'])['data']
    for f in d['frames']:
        masks={m['name'] for m in f.get('masks',[])}
        if {'Title','Type'} & masks:
            assert f['src'].endswith('m15FrameM.png')
        if 'Rules' in masks:
            assert f['src'].endswith('m15FrameM.png')
    pinline=next(f for f in d['frames'] if 'Pinline' in {m['name'] for m in f.get('masks',[])})
    assert pinline['src'].startswith('data:image/svg+xml;utf8,')
    assert any('Vehicle' in f.get('name','') for f in d['frames'])


def test_miracle_keyword_uses_cardconjurer_miracle_overlay(env):
    w,_,a,s=env
    c=sf('Temporal Mastery',type_line='Sorcery',colors=['U'],mana_cost='{5}{U}{U}',
         oracle_text='Take an extra turn after this one. Exile Temporal Mastery.\\nMiracle {1}{U}',
         keywords=['Miracle'],power=None,toughness=None)
    r=w.compiler.compile_face(c,c,0,{},s,a['id'])
    d=r['data'];miracle=[f for f in d['frames'] if 'Miracle Frame' in f.get('name','')]
    assert len(miracle)==1
    assert miracle[0]['name']=='Blue Miracle Frame'
    assert miracle[0]['src']=='/img/frames/m15/miracle/u.png'
    assert miracle[0]['bounds']=={'x':0.04,'y':0.0286,'width':0.92,'height':0.5324}
    assert d['frames'][0] is miracle[0]


def test_miracle_oracle_fallback_is_strict_and_classic_override_can_skip_it(env):
    w,_,a,s=env
    miracle=sf('Fallback Miracle',type_line='Instant',colors=['W'],mana_cost='{2}{W}',
               oracle_text='Miracle {W}',keywords=[],power=None,toughness=None)
    auto=w.compiler.compile_face(miracle,miracle,0,{},s,a['id'])['data']
    assert any(f.get('src')=='/img/frames/m15/miracle/w.png' for f in auto['frames'])
    classic=w.compiler.compile_face(miracle,miracle,0,{'templateOverride':'normal'},s,a['id'])['data']
    assert not any('Miracle Frame' in f.get('name','') for f in classic['frames'])
    prose=sf('Not A Miracle',type_line='Instant',colors=['W'],mana_cost='{W}',
             oracle_text='Create a Miracle Worker token.',keywords=[],power=None,toughness=None)
    ordinary=w.compiler.compile_face(prose,prose,0,{},s,a['id'])['data']
    assert not any('Miracle Frame' in f.get('name','') for f in ordinary['frames'])


@pytest.mark.parametrize('name,type_line,layout',[
    ('Creature','Creature — Elf','normal'),('Artifact','Artifact','normal'),
    ('Land','Land','normal'),('Legendary Land','Legendary Land','normal')])
def test_symbol_fit_uses_each_frame_bounds(env,name,type_line,layout):
    w,_,a,s=env;c=sf(name,type_line=type_line,layout=layout)
    comp=w.compiler.compile_face(c,c,0,{},s,a['id']);d=comp['data'];sym=w.store.asset(s['symbols']['rare'])
    cw=d['width'];ch=d['height'];bounds=d['setSymbolBounds'];box=d['text']['type']
    rendered_w=sym['width']*d['setSymbolZoom'];rendered_h=sym['height']*d['setSymbolZoom']
    bounds_w=round(bounds['width']*cw);bounds_h=round(bounds['height']*ch)
    assert rendered_w<=bounds_w+.6 and rendered_h<=bounds_h+.6
    assert min(abs(rendered_w-bounds_w),abs(rendered_h-bounds_h))<=1.5
    anchor_x=round(bounds['x']*cw);anchor_y=round(bounds['y']*ch)
    horizontal=bounds.get('horizontal','center');vertical=bounds.get('vertical','center')
    expected_x=anchor_x-rendered_w if horizontal=='right' else anchor_x-rendered_w/2 if horizontal=='center' else anchor_x
    expected_y=anchor_y-rendered_h if vertical=='bottom' else anchor_y-rendered_h/2 if vertical=='center' else anchor_y
    expected_y+=SET_SYMBOL_RECIPE_Y_OFFSET_PX.get(comp['recipe'],0)
    assert d['setSymbolX']*cw==pytest.approx(round(expected_x),abs=.6)
    assert d['setSymbolY']*ch==pytest.approx(round(expected_y),abs=.6)
    if _standard_visible_type_bar(d,bounds):assert bounds['y']==pytest.approx(M15_SET_SYMBOL_VERTICAL_CENTER)
    if horizontal=='right' and float(box.get('rotation') or 0)%360==0:
        assert (d['setSymbolX']-(box['x']+box['width']))*cw==pytest.approx(.01*cw,abs=.6)


@pytest.mark.parametrize('version',['m15Regular','modalRegular','genericShowcase','stationRegular','futureFrame'])
def test_set_symbol_fit_is_version_independent(version):
    data={'version':version,'width':2010,'height':2814,'setSymbolZoom':.101,
          'setSymbolX':.85,'setSymbolY':.57,
          'setSymbolBounds':{'x':.9213,'y':.59355,'width':.12,'height':.041,'vertical':'center','horizontal':'right'},
          'text':{'type':{'x':.0854,'y':.5664,'width':.78,'height':.0543,'rotation':0}}}
    fit_set_symbol_to_bounds(data,{'width':869,'height':1057})
    assert data['setSymbolZoom']==pytest.approx(.109)
    assert data['setSymbolX']*2010==pytest.approx(1757)
    assert data['setSymbolY']*2814==pytest.approx(1606)
    assert data['setSymbolBounds']['y']==pytest.approx(M15_SET_SYMBOL_VERTICAL_CENTER)


def test_set_symbol_fit_respects_nonstandard_frame_anchor():
    data={'version':'anything','width':1000,'height':1000,
          'setSymbolBounds':{'x':.5,'y':.4,'width':.2,'height':.1,'vertical':'bottom','horizontal':'center'},
          'text':{'type':{'x':.1,'y':.3,'height':.08,'width':.5,'rotation':0}}}
    fit_set_symbol_to_bounds(data,{'width':100,'height':200})
    assert data['setSymbolZoom']==pytest.approx(.5)
    assert data['setSymbolX']*1000==pytest.approx(475)
    assert data['setSymbolY']*1000==pytest.approx(300)
    assert data['setSymbolBounds']['y']==pytest.approx(.4)


def test_academy_ruins_uses_neutral_legendary_land_treatment(env):
    w,_,a,s=env
    c=sf(
        'Academy Ruins',
        type_line='Legendary Land',
        colors=[],
        mana_cost='',
        oracle_text='{T}: Add {C}.\n{1}{U}, {T}: Put target artifact card from your graveyard on top of your library.',
        produced_mana=['C'],
        power=None,
        toughness=None,
    )
    comp=w.compiler.compile_face(c,c,0,{},s,a['id'])
    assert comp['recipe']=='land_full_legendary'
    assert semantic(c,c).get('land_colors',[])==[]
    sources=[str(frame.get('src','')) for frame in comp['data']['frames']]
    # No blue template default may survive on a colorless land.
    assert not any(
        'FrameU.png' in src or '/ul.png' in src or 'CrownU' in src
        for src in sources
    )
    for effect in ('Pinline','Title','Type','Rules'):
        layers=[f for f in comp['data']['frames'] if effect in {
            m.get('name') for m in f.get('masks',[]) if isinstance(m,dict)
        }]
        assert layers and all(
            'FrameL.png' in str(f.get('src','')) or '/l.png' in str(f.get('src',''))
            for f in layers
        )
    assert any('m15CrownL' in src for src in sources)


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


def test_missing_generation_metadata_forces_once_then_reuses(env):
    w,c,a,s=env
    d=w.create({'source':[{'id':c['id']}],'settings':s})
    before=w.deck(d['id'])
    assert before['upgradeRequired']
    force=bool(before['upgradeRequired'])
    prepared=w.prepare(d['id'])
    comp=prepared['cards'][0]['faces'][0]['compiled']
    assert comp['generationVersion']==GENERATION_VERSION
    w.store.render_put(comp['renderKey'],a)
    first=w.render_targets([d['id']],force=force)
    assert first['cached']==0 and len(first['targets'])==1
    dims=(comp['data']['width'],comp['data']['height'])
    w.save_render(comp['renderKey'],png(dims),dims)
    reloaded=w.deck(d['id'])
    assert not reloaded.get('upgradeRequired')
    assert reloaded['cards'][0]['faces'][0]['compiled']['generationVersion']==GENERATION_VERSION
    second=w.render_targets([d['id']])
    assert second['cached']==1 and second['targets']==[]
