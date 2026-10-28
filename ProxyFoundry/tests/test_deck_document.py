import copy
import hashlib
import json
from pathlib import Path
import pytest
from foundry.deck_document import export_document,import_document,reusable_recipe,validate,source_for_image
from foundry.card_data import parse_document
from foundry.domain import ValidationError,uid,stable_hash
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace
from test_preparation_cache import seeded


def source_deck(tmp_path):
    ws,deck,_,_=seeded(tmp_path/'source')
    deck=ws.prepare(deck['id'])
    deck['notes']='Keep all quantities, sections and edits.'
    deck['settings']['showFlavorText']=False
    deck['cards'][0]['quantity']=3
    face=deck['cards'][0]['faces'][0]
    face['fit']={'zoom':1.25,'x':.1,'y':-.1}
    face['acceptedArt']=[face['compiled']['contentRenderKey']]
    face['acceptedWarningKey']=face['compiled']['renderKey']
    deck=ws.store.put('decks',deck,deck['revision'])
    return ws,deck


def destination(tmp_path,source,document):
    urls={}
    for ident,entry in document['images'].items():
        cached=source.store.cache_get(entry['url'])
        if cached:
            raw=source.store.asset_path(cached['asset_id']).read_bytes()
        elif entry.get('transform')=='trim-transparent':
            filename=entry['url'].split('/ProxyFoundry/')[-1]
            raw=(Path(__file__).parents[1]/filename).read_bytes()
        else:raw=source.store.asset_path(ident).read_bytes()
        urls[entry['url']]=(raw,entry['mime'],{})
    store=Store(tmp_path/'destination')
    return Workspace(store,Network(store,transport=lambda url:urls[url],sleeper=lambda _:None))


def test_finished_recipe_round_trip_preserves_inputs_without_embedding_images(tmp_path,monkeypatch):
    ws,deck=source_deck(tmp_path)
    document=export_document(ws,deck['id'])
    assert document['version']==2
    assert all('url' in image for image in document['images'].values())
    assert 'base64' not in json.dumps(document)
    assert not document['includesRenders']
    restored_ws=destination(tmp_path,ws,document)
    restored=import_document(restored_ws,document)
    assert restored['id']!=deck['id']
    assert restored['name']==deck['name']
    assert restored['notes']==deck['notes']
    assert restored['settings']==document['deck']['settings']
    card=restored['cards'][0];face=card['faces'][0]
    assert card['quantity']==3
    assert card['section']==deck['cards'][0]['section']
    assert card['scryfall']==deck['cards'][0]['scryfall']
    assert face['fit']==deck['cards'][0]['faces'][0]['fit']
    assert face['compiled']['data']==deck['cards'][0]['faces'][0]['compiled']['data']
    assert face['acceptedArt']==deck['cards'][0]['faces'][0]['acceptedArt']
    assert face['acceptedWarningKey']==face['compiled']['renderKey']
    assert reusable_recipe(restored)
    monkeypatch.setattr(restored_ws.sources,'resolve_card',lambda *a,**k:pytest.fail('Frozen metadata changed'))
    monkeypatch.setattr(restored_ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Frozen layout changed'))
    assert restored_ws.prepare(restored['id'])['cards'][0]['faces'][0]['compiled']['data']==face['compiled']['data']
    restored['settings']['artist']='A deliberate edit'
    assert not reusable_recipe(restored)
    assert parse_document(json.dumps(document).encode())==document['cards']


def test_missing_permanent_source_is_reported_instead_of_embedded(tmp_path):
    ws,deck=source_deck(tmp_path)
    ident=ws.store.add_asset(b'unreferenced image','image/png',1,1)['id']
    deck['cards'][0]['faces'][0]['artOverride']=ident
    ws.store.put('decks',deck,deck['revision'])
    plan=export_document(ws,deck['id'],allow_missing=True)
    assert ident in plan['missing']
    assert 'base64' not in plan['document']['images'][ident]
    with pytest.raises(ValidationError,match='permanent URLs'):export_document(ws,deck['id'])


def test_changed_remote_image_never_publishes_a_deck(tmp_path):
    ws,deck=source_deck(tmp_path);document=export_document(ws,deck['id'])
    store=Store(tmp_path/'other')
    other=Workspace(store,Network(store,transport=lambda url:(b'changed','image/png',{}),sleeper=lambda _:None))
    with pytest.raises(ValidationError,match='SHA-256|decode|different pixels'):import_document(other,document)
    assert not store.list('decks')


def test_import_is_a_copy_and_does_not_overwrite_the_source(tmp_path):
    ws,deck=source_deck(tmp_path);document=export_document(ws,deck['id'])
    original=copy.deepcopy(ws.store.get('decks',deck['id']))
    imported=import_document(ws,document)
    assert imported['id']!=deck['id']
    assert ws.store.get('decks',deck['id'])==original
    assert imported['cards'][0]['id']!=original['cards'][0]['id']
    assert imported['cards'][0]['faces'][0]['id']!=original['cards'][0]['faces'][0]['id']
    assert imported['cards'][0]['faces'][0]['compiled']['renderKey']!=original['cards'][0]['faces'][0]['compiled']['renderKey']


def test_embedded_images_are_rejected(tmp_path):
    ws,deck=source_deck(tmp_path);document=export_document(ws,deck['id'])
    entry=next(iter(document['images'].values()));entry['base64']='AA=='
    with pytest.raises(ValidationError,match='embedded'):validate(document)


@pytest.mark.parametrize('base64_encoded',[False,True])
def test_generated_gradient_layers_export_as_drawing_inputs_and_rebuild(tmp_path,base64_encoded):
    import base64,xml.etree.ElementTree as ET
    from urllib.parse import quote,unquote
    ws,deck=source_deck(tmp_path)
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><defs><linearGradient id="fade"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs><rect width="20" height="20" fill="url(#fade)"/></svg>'
    uri=('data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()) if base64_encoded else 'data:image/svg+xml;utf8,'+quote(svg)
    frames=deck['cards'][0]['faces'][0]['compiled']['data']['frames']
    frames.append({'name':'Generated land title gradient','src':uri,'masks':[]})
    ws.store.put('decks',deck,deck['revision'])
    document=export_document(ws,deck['id'])
    assert len(document['vectors'])==1
    assert 'data:image/' not in json.dumps(document) and 'base64' not in json.dumps(document)
    other=destination(tmp_path,ws,document);restored=import_document(other,document)
    restored_uri=restored['cards'][0]['faces'][0]['compiled']['data']['frames'][-1]['src']
    def tree(node):return (node.tag,dict(node.attrib),node.text,[tree(c) for c in node])
    assert tree(ET.fromstring(unquote(restored_uri.split(',',1)[1])))==tree(ET.fromstring(svg))
    assert reusable_recipe(restored)
    missing=copy.deepcopy(document);missing['vectors']={}
    with pytest.raises(ValidationError,match='vector'):validate(missing)
    tampered=copy.deepcopy(document);next(iter(tampered['vectors'].values()))['root']['attributes']['width']='99'
    with pytest.raises(ValidationError,match='identity'):validate(tampered)


def test_vector_drawing_recipes_reject_active_or_external_content():
    from foundry.deck_document import map_images,vector_source
    from urllib.parse import quote
    for svg in ['<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.com/a.svg"/></svg>']:
        with pytest.raises(ValidationError):map_images('data:image/svg+xml,'+quote(svg),vectors={})
    with pytest.raises(ValidationError):vector_source({'kind':'svg','root':{'tag':'svg'}})


@pytest.mark.parametrize('legacy',[False,True])
def test_cropped_github_symbols_keep_original_sources_and_rebuild(tmp_path,legacy):
    import io
    from PIL import Image
    from foundry.images import ingest_image
    ws,deck=source_deck(tmp_path);urls={};expected={}
    for n,rarity in enumerate(['common','uncommon','rare','mythic']):
        image=Image.new('RGBA',(40,40));image.paste((40*n,60,90,255),(10,10,30,30))
        buffer=io.BytesIO();image.save(buffer,'PNG');raw=buffer.getvalue()
        url='https://raw.githubusercontent.com/owner/cards/'+'a'*40+'/symbols/'+rarity+'.png'
        urls[url]=(raw,'image/png',{})
        original=ws.store.add_asset(raw,'image/png',40,40);ws.store.cache_put(url,original,ws.net.clock())
        trimmed=ingest_image(ws.store,raw,trim_transparent_padding=True)
        assert trimmed['id']!=original['id']
        key=stable_hash({'url':url,'trim':True,'version':1})
        record={'id':key,'assetId':trimmed['id']}
        if not legacy:record['source']={'url':url,'transform':'trim-transparent'}
        ws.store.put('github-setup-images',record)
        if not legacy:
            #New provenance survives eviction of the original HTTP cache entry.
            with ws.store.connect() as db:db.execute('DELETE FROM http_cache WHERE url=?',(url,))
        deck['settings']['symbols'][rarity]=trimmed['id'];expected[trimmed['id']]=url
    ws.store.put('decks',deck,deck['revision'])
    before=ws.store.get('decks',deck['id'])['revision']
    document=export_document(ws,deck['id'])
    assert ws.store.get('decks',deck['id'])['revision']==before
    for ident,url in expected.items():assert {k:document['images'][ident][k] for k in ['url','transform']}=={'url':url,'transform':'trim-transparent'}
    other=destination(tmp_path,ws,{**document,'images':{key:entry for key,entry in document['images'].items() if key not in expected}})
    transport=other.net.transport;other.net.transport=lambda url:urls[url] if url in urls else transport(url)
    restored=import_document(other,document)
    assert restored['settings']['symbols']==deck['settings']['symbols']


def test_v1_overlays_stay_compatible():
    assert parse_document(b'{"version":1,"cards":[{"name":"One Card","nickname":"Two"}]}')[0]['nickname']=='Two'


def test_custom_templates_token_pairings_and_all_overrides_round_trip(tmp_path):
    ws,deck=source_deck(tmp_path)
    original=deck['cards'][0]
    art=original['faces'][0]['compiled']['artId']
    template=ws.save_template({'name':'Custom creature frame','data':original['faces'][0]['compiled']['data'],
                               'groups':['standard'],'mapping':{},'legendary':False})
    deck['settings']['templateRules']={'standard':template['id']}
    original['faces'][0]['templateOverride']=template['id']
    original['faces'][0]['semanticOverrides']={'nickname':'A complete recipe','oracle_text':'Vigilance'}
    tokens=[]
    for name in ('Cat','Bird'):
        sf={**original['scryfall'],'id':uid(),'oracle_id':uid(),'name':name,'layout':'token',
            'type_line':'Token Creature — '+name,'oracle_text':'','mana_cost':'','colors':['W'],'power':'1','toughness':'1'}
        card=ws.sources.entry(sf,2,'tokens')
        face=card['faces'][0]
        face['compiled']=ws.compiler.compile_face(sf,sf,0,{},deck['settings'],art)
        face['compiled']['contentRenderKey']=face['compiled']['renderKey']
        tokens.append(card)
    deck['cards'].extend(tokens)
    from foundry.token_assignments import reference
    deck['settings']['tokenAssignments']=[{'front':reference(tokens[0]),
        'back':reference(tokens[1]),'quantity':4}]
    deck['settings']['backDesign']={'mode':'icon','iconAsset':art}
    deck['settings']['backAsset']=ws.backs.icon(art)['id']
    ws.store.put('decks',deck,deck['revision'])
    document=export_document(ws,deck['id'])
    assert document['templates'][0]['id']==template['id']
    assert any(image.get('recipe',{}).get('kind')=='back-icon' for image in document['images'].values())
    #All source bytes are already available in this workspace. Importing still
    #allocates separate deck/card/template identities and retains the recipe.
    restored=import_document(ws,document)
    assert restored['settings']['tokenAssignments']==document['deck']['settings']['tokenAssignments']
    assert restored['tokens']['physicalCount']==4
    selected=restored['settings']['templateRules']['standard']
    assert selected!=template['id']
    assert ws.store.get('templates',selected)['data']==template['data']
    assert restored['cards'][0]['faces'][0]['templateOverride']==selected
    assert restored['cards'][0]['faces'][0]['semanticOverrides']==original['faces'][0]['semanticOverrides']
    assert restored['settings']['backAsset']==deck['settings']['backAsset']


def test_missing_dependency_and_renderer_mismatch_do_not_import(tmp_path):
    ws,deck=source_deck(tmp_path);document=export_document(ws,deck['id'])
    document['images'].pop(deck['settings']['backAsset'])
    before=len(ws.store.list('decks'))
    with pytest.raises(ValidationError,match='missing a required image'):import_document(ws,document)
    assert len(ws.store.list('decks'))==before
    document=export_document(ws,deck['id']);document['renderer']['pipeline']='another-version'
    with pytest.raises(ValidationError,match='different renderer version'):import_document(ws,document)
    assert len(ws.store.list('decks'))==before


def test_permanent_github_source_pins_commit_and_records_normalization(tmp_path):
    import io
    from PIL import Image
    from foundry.images import ingest_image
    image=Image.new('RGBA',(20,20));image.paste('red',(5,5,15,15));output=io.BytesIO();image.save(output,'PNG');raw=output.getvalue()
    store=Store(tmp_path)
    asset=ingest_image(store,raw,trim_transparent_padding=True)
    def transport(url):
        return (json.dumps({'sha':'b'*40}).encode(),'application/json',{}) if '/commits/' in url else (raw,'image/png',{})
    ws=Workspace(store,Network(store,transport=transport,sleeper=lambda _:None))
    result=source_for_image(ws,asset['id'],'https://github.com/owner/cards/blob/main/art.png')
    assert result=={'url':'https://raw.githubusercontent.com/owner/cards/'+'b'*40+'/art.png','transform':'trim-transparent'}


def test_deck_wide_token_conversion_keeps_exact_compiled_recipe(tmp_path):
    ws,deck=source_deck(tmp_path)
    ws.save(deck['id'],{'revision':deck['revision'],'settings':{'allCardsTokens':True,
        'tokenOptions':{'power':'3','toughness':'3','subtypes':'Cat','nonlegendary':True}}})
    deck=ws.prepare(deck['id'])
    assert not deck['cards'][0]['faces'][0].get('error')
    document=export_document(ws,deck['id'])
    other=destination(tmp_path,ws,document)
    restored=import_document(other,document)
    assert restored['settings']['allCardsTokens']
    assert restored['settings']['tokenOptions']==deck['settings']['tokenOptions']
    assert restored['cards'][0]['faces'][0]['compiled']['data']==deck['cards'][0]['faces'][0]['compiled']['data']
    assert reusable_recipe(restored)


def test_cancelled_import_never_publishes_a_deck(tmp_path):
    from foundry.deck_document import import_document_steps
    ws,deck=source_deck(tmp_path);document=export_document(ws,deck['id'])
    other=destination(tmp_path,ws,document)
    cancelled=False
    steps=import_document_steps(other,document,cancel=lambda:cancelled)
    next(steps)
    cancelled=True
    with pytest.raises(ValidationError,match='cancelled'):next(steps)
    assert not other.store.list('decks')


def test_browser_import_yields_between_image_sources(tmp_path):
    from foundry.browser import BrowserJobs
    from foundry.deck_document import import_document_steps
    ws,deck=source_deck(tmp_path);document=export_document(ws,deck['id'])
    other=destination(tmp_path,ws,document)
    jobs=BrowserJobs(other.store)
    job=jobs.start('Import complete deck',lambda update,cancel:import_document_steps(other,document,update,cancel))
    jobs.run_pending(limit=1)
    assert jobs.get(job['id'])['state']=='running'
    assert not other.store.list('decks')
    while jobs.run_pending(limit=1):pass
    result=jobs.get(job['id'])
    assert result['state']=='done'
    assert result['result']['name']==deck['name']
