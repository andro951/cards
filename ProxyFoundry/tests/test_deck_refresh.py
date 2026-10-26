"""Live list reconciliation keeps generated faces and publishes only complete updates."""
import copy,io,json
import pytest
from PIL import Image
from foundry.domain import ConflictError,ValidationError,uid
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry import art_variants
from test_import_scheduling import drain
from test_scryfall_deck_refresh import DECK_URL,EXPORT_URL,CARD_A,CARD_B,card

CARD_C='cccccccc-cccc-4ccc-8ccc-cccccccccccc'


@pytest.fixture
def env(tmp_path):
    images=io.BytesIO();Image.new('RGB',(30,42),'navy').save(images,'PNG');raw=images.getvalue()
    records={ident:card(ident,name,str(index)) for index,(ident,name) in enumerate([(CARD_A,'Alpha'),(CARD_B,'Beta'),(CARD_C,'Gamma')])}
    for value in records.values():value['image_uris']={'art_crop':'https://cards.scryfall.io/'+value['id']+'.png'}
    remote={'rows':[(CARD_A,2,'mainboard'),(CARD_B,1,'mainboard')],'calls':[],'fail':False}
    def fetch(url):
        remote['calls'].append(url)
        if url==EXPORT_URL:
            if remote['fail']:raise ValidationError('Original deck unavailable')
            entries={}
            for ident,count,section in remote['rows']:entries.setdefault(section,[]).append({'count':count,'card_digest':records[ident]})
            return json.dumps({'name':'Remote deck','entries':entries}).encode(),'application/json',{}
        if url.startswith('https://api.scryfall.com/cards/'):
            ident=url.rsplit('/',1)[1];return json.dumps(records[ident]).encode(),'application/json',{}
        if url.startswith('https://cards.scryfall.io/'):return raw,'image/png',{}
        raise AssertionError(url)
    store=Store(tmp_path);ws=Workspace(store,Network(store,transport=fetch,sleeper=lambda _:None))
    deck=ws.create({'source':DECK_URL,'name':'Keep local name','settings':{'artist':'Keep artist'}})
    deck=ws.prepare(deck['id'])
    for entry in deck['cards']:
        face=entry['faces'][0];store.render_put(face['compiled']['renderKey'],store.asset(face['compiled']['artId']))
    remote['calls'].clear()
    yield ws,ws.deck(deck['id']),remote


def refresh(env,**options):
    ws,old,_=env;deck=ws.deck(old['id'])
    return ws.refresh_deck(deck['id'],{'revision':deck['revision'],**options})


def test_refresh_adds_removes_updates_quantities_and_only_generates_new_cards(env,monkeypatch):
    ws,deck,remote=env;kept=copy.deepcopy(deck['cards'][0]);old_render=kept['faces'][0]['compiled']['renderKey']
    remote['rows']=[(CARD_A,5,'mainboard'),(CARD_C,1,'mainboard')]
    result=refresh(env);updated=result['deck'];alpha,gamma=updated['cards']
    kept['quantity']=5
    assert alpha==kept and gamma['name']=='Gamma' and not gamma['faces'][0].get('compiled')
    assert updated['name']=='Keep local name' and updated['settings']==deck['settings']
    assert [row['name'] for row in result['changes']['added']]==['Gamma']
    assert result['changes']['removed']==[{'name':'Beta','quantity':1}]
    assert result['changes']['quantityChanged']==[{'name':'Alpha','before':2,'after':5}]
    assert remote['calls']==[EXPORT_URL,'https://api.scryfall.com/cards/'+CARD_C]
    assert ws.store.render_get(old_render)
    calls=[];compile_face=ws.compiler.compile_face
    def compile(sf,*args,**kwargs):calls.append(sf['name']);return compile_face(sf,*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',compile)
    ws.prepare(deck['id']);plan=ws.render_targets([deck['id']])
    assert calls==['Gamma'] and [target['name'] for target in plan['targets']]==['Gamma']
    assert plan['cached']==1


def test_quantity_only_and_section_moves_retain_images_and_overrides(env):
    ws,deck,remote=env;entry=deck['cards'][0];entry['backOverride']=entry['faces'][0]['compiled']['artId']
    entry['faces'][0]['acceptedWarningKey']=entry['faces'][0]['compiled']['renderKey']
    deck=ws.store.put('decks',deck,deck['revision']);old_face=copy.deepcopy(entry['faces'][0])
    remote['rows']=[(CARD_A,4,'commanders'),(CARD_B,1,'mainboard')]
    result=refresh(env);updated=result['deck']
    assert updated['cards'][0]['faces'][0]==old_face and updated['cards'][0]['backOverride']==entry['backOverride']
    assert result['changes']['moved']==[{'name':'Alpha','from':'mainboard','to':'commanders'}]
    assert not result['changes']['added'] and not result['changes']['removed']
    assert ws.render_targets([deck['id']])['targets']==[]
    assert remote['calls']==[EXPORT_URL]


def test_empty_source_removes_source_cards_but_keeps_local_additions(env):
    ws,deck,remote=env
    ws.add_cards(deck['id'],{'revision':deck['revision'],'source':CARD_C})
    local=ws.deck(deck['id'])['cards'][-1]
    remote['rows']=[];result=refresh(env)
    assert result['deck']['cards']==[local]
    assert len(result['changes']['removed'])==2 and result['changes']['local']==1


@pytest.mark.parametrize('boundary',['cancel','edit','delete','unavailable'])
def test_refresh_never_publishes_partial_or_stale_lists(env,boundary):
    ws,deck,remote=env;before=ws.store.get('decks',deck['id']);cancelled=False
    remote['rows']=[(CARD_C,1,'mainboard')];remote['fail']=boundary=='unavailable'
    steps=ws.refresh_deck_steps(deck['id'],{'revision':deck['revision']},cancel=lambda:cancelled)
    next(steps)
    if boundary=='cancel':cancelled=True
    elif boundary=='edit':
        ws.save(deck['id'],{'revision':deck['revision'],'notes':'Keep newer edit'})
        before=ws.store.get('decks',deck['id'])
    elif boundary=='delete':ws.store.trash('decks',deck['id'],deck['revision'])
    with pytest.raises((ValidationError,ConflictError)):drain(steps)
    current=ws.store.get('decks',deck['id'])
    if boundary=='delete':assert current is None
    else:
        assert current['cards']==before['cards']
        if boundary=='edit':assert current['notes']=='Keep newer edit'
        else:assert current==before


def test_refresh_clamps_art_variants_without_discarding_retained_variant_images(env):
    ws,deck,remote=env;alpha=deck['cards'][0];alpha['quantity']=5
    variant_id=uid();deck['settings']['artVariants']=[{'id':variant_id,'card':art_variants.reference(alpha),
        'quantity':3,'faces':[{'name':'Alpha','art':'alternate.png'}]}]
    art_variants.apply(deck,ws.invalidate_face)
    variant=next(entry for entry in deck['cards'] if entry.get('artVariantId'))
    variant['faces'][0]['compiled']=copy.deepcopy(env[1]['cards'][0]['faces'][0]['compiled'])
    ws.store.put('decks',deck,deck['revision']);key=variant['faces'][0]['compiled']['renderKey'];face_id=variant['faces'][0]['id']
    remote['rows']=[(CARD_A,2,'mainboard'),(CARD_B,1,'mainboard')]
    result=refresh(env);remaining=next(entry for entry in result['deck']['cards'] if entry['name']=='Alpha')
    assert remaining['quantity']==2 and remaining['artVariantId']==variant_id
    assert remaining['faces'][0]['id']==face_id and remaining['faces'][0]['compiled']['renderKey']==key
    assert result['deck']['settings']['artVariants'][0]['quantity']==2


def test_outside_is_always_included_despite_legacy_preference_and_sideboard_is_excluded(env):
    ws,deck,remote=env;remote['rows'].extend([(CARD_C,1,'outside'),(CARD_C,3,'sideboard')])
    deck['includeOutside']=False;ws.store.put('decks',deck,deck['revision'])
    first=refresh(env,includeOutside=False)['deck']
    assert len(first['cards'])==3 and 'includeOutside' not in first
    assert len(refresh(env)['deck']['cards'])==3


def test_helper_import_retains_original_url_for_later_refresh(env):
    ws,_,_=env;link='https://archidekt.com/decks/12345/example'
    listing=ws.sources.read_deck_manifest(json.dumps({'sourceUrl':link,'name':'Helper deck','rows':[{'source':CARD_A,'quantity':1}]}))
    deck=ws.create_staged({'manifest':listing,'includeOutside':False})
    assert deck['importedSource']==link and 'includeOutside' not in deck


def test_removed_token_cleans_its_pair_without_invalid_pair_warnings(env):
    from foundry import token_assignments
    ws,deck,remote=env
    for card in deck['cards']:card['tokenSpec']={}
    deck['settings']['tokenAssignments']=[{'front':token_assignments.reference(deck['cards'][0]),
        'back':token_assignments.reference(deck['cards'][1]),'quantity':1}]
    ws.store.put('decks',deck,deck['revision']);remote['rows']=[(CARD_A,2,'mainboard')]
    result=refresh(env)['deck']
    assert result['settings']['tokenAssignments']==[] and not result['tokens']['invalid']
    assert len(result['tokens']['unused'])==1


@pytest.mark.parametrize('cancel',[False,True])
def test_browser_refresh_route_is_cooperative_and_cancellable(env,cancel):
    from foundry.browser import create_app,request
    ws,deck,remote=env;remote['rows']=[(CARD_A,7,'mainboard')]
    app=create_app(ws.store.home,ws.net.transport,'http://127.0.0.1')
    try:
        revision=app.ws.deck(deck['id'])['revision']
        reply=request(app,'POST','/api/decks/'+deck['id']+'/refresh',json.dumps({'revision':revision}).encode())
        assert reply['status']==200,reply
        ident=json.loads(reply['body'])['id'];app.jobs.run_pending(limit=1)
        assert app.jobs.get(ident)['state']=='running'
        if cancel:app.jobs.cancel(ident)
        app.jobs.run_pending();job=app.jobs.get(ident)
        assert job['state']==('cancelled' if cancel else 'done'),job
        cards=app.ws.deck(deck['id'])['cards']
        assert cards[0]['quantity']==(2 if cancel else 7)
        assert len(cards)==(2 if cancel else 1)
    finally:app.close()