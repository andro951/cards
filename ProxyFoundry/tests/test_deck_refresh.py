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
from test_token_assignments import token_deck,assignment

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


@pytest.mark.parametrize('staged',[False,True],ids=['existing-import','staged-import'])
@pytest.mark.parametrize('removed_indices',[(0,),(1,),(3,),(0,1,3)],ids=['paired-front','paired-back','double-sided','all-tokens'])
def test_refresh_removes_real_token_faces_and_pairings_without_losing_other_images(token_deck,staged,removed_indices,monkeypatch):
    from foundry import token_assignments
    from foundry.orders import Orders
    ws,deck,cards=token_deck
    deck['importedSource']=DECK_URL
    if staged:
        deck['stagedImport']=True
        for entry in deck['cards']:entry['metadataSource']=entry['scryfall']['id']
    shared={'front':{'name':'Token from another deck'},'back':{'kind':'card-back'},'quantity':2}
    pair=assignment(cards[0],cards[1],7)
    deck['settings']['tokenAssignments']=[pair,shared]
    deck['settings']['tokenTreatments']=[{'face':token_assignments.reference(cards[0]),'options':{'frame_color':'W'}}]
    deck=ws.store.put('decks',deck,deck['revision']);deck=ws.deck(deck['id'])
    before={entry['id']:copy.deepcopy(entry) for entry in deck['cards']}
    removed={cards[index]['id'] for index in removed_indices};calls=[]
    def remote(url):
        calls.append(url);assert url==EXPORT_URL
        entries={}
        for entry in cards:
            if entry['id'] in removed:continue
            section='mainboard' if entry['scryfall']['layout']=='normal' else 'outside'
            entries.setdefault(section,[]).append({'count':entry['quantity'],'card_digest':entry['scryfall']})
        return json.dumps({'name':'Source tokens','entries':entries}).encode(),'application/json',{}
    ws.net.transport=remote
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *args,**kwargs:pytest.fail('Refresh must not render or prepare retained token faces'))
    old_order=Orders(ws).build([deck['id']])
    result=ws.refresh_deck(deck['id'],{'revision':deck['revision']})
    updated=result['deck'];present={entry['id'] for entry in updated['cards']}
    assert present==set(before)-removed
    assert {row['name'] for row in result['changes']['removed']}=={cards[index]['scryfall']['name'] for index in removed_indices}
    assert not result['changes']['added'] and result['changes']['local']==0
    for entry in updated['cards']:
        assert entry['faces']==before[entry['id']]['faces']
    assert not updated['tokens']['invalid']
    assert all(row['frontCardId'] in present and (row['backCardId'] is None or row['backCardId'] in present) for row in updated['tokens']['assigned'])
    assert updated['settings']['tokenAssignments']==([pair] if not removed.intersection({cards[0]['id'],cards[1]['id']}) else [])+[shared]
    assert bool(updated['settings']['tokenTreatments'])==(cards[0]['id'] not in removed)
    assert set(updated['tokens']['cardIds'])=={entry['id'] for entry in updated['cards'] if entry['scryfall']['layout']!='normal'}
    assert ws.store.get('orders',old_order['id'])['cards']==old_order['cards']
    for index in removed_indices:
        for face in before[cards[index]['id']]['faces']:
            assert ws.store.render_get(face['compiled']['renderKey'])
    repeated=ws.refresh_deck(deck['id'],{'revision':updated['revision']})
    assert not repeated['changes']['removed'] and {entry['id'] for entry in repeated['deck']['cards']}==present
    assert calls==[EXPORT_URL,EXPORT_URL]
    reloaded=ws.deck(deck['id'])
    if reloaded['tokens']['unused']:
        by_id={entry['id']:entry for entry in reloaded['cards']}
        rows=reloaded['settings']['tokenAssignments']+[assignment(by_id[row['cardId']]) for row in reloaded['tokens']['unused']]
        ws.save(deck['id'],{'revision':reloaded['revision'],'tokenAssignments':rows})
    assert all(row['cardId'] not in removed for row in Orders(ws).plan([deck['id']])['cards'])


@pytest.mark.parametrize('legacy',[False,True],ids=['current-copy','legacy-copy'])
def test_refresh_preserves_local_copy_tokens_when_their_source_card_is_removed(env,legacy):
    ws,deck,remote=env
    copied=ws.copy_token(deck['id'],deck['cards'][0]['id'],{'nonlegendary':True},deck['revision'])
    assert copied['cards'][-1]['faces'][0]['semanticOverrides']['flavor_text']==''
    assert copied['cards'][0]['faces']==deck['cards'][0]['faces']
    if legacy:
        copied['cards'][-1].pop('deckLocal');copied=ws.store.put('decks',copied,copied['revision'])
    kept=copy.deepcopy(ws.deck(deck['id'])['cards'][-1]);remote['rows']=[(CARD_B,1,'mainboard')]
    result=refresh(env)
    assert [entry['name'] for entry in result['deck']['cards']]==['Beta',kept['name']]
    assert result['deck']['cards'][-1]==kept and result['changes']['local']==1


@pytest.mark.parametrize('treatment',['individual','deck-wide'])
@pytest.mark.parametrize('legacy',[False,True],ids=['source-markers','missing-source-markers'])
def test_refresh_removes_normal_cards_treated_as_tokens_even_without_old_metadata_markers(token_deck,treatment,legacy):
    from foundry import token_assignments
    ws,deck,cards=token_deck;removed=cards[0];partner=cards[1]
    removed['name']=removed['faces'][0]['name']=removed['scryfall']['name']='Badgermole Cub'
    removed['scryfall'].update(layout='normal',type_line='Creature — Badger Mole')
    if treatment=='individual':removed['tokenSpec']={'nonlegendary':True}
    else:deck['settings']['allCardsTokens']=True
    deck.update(cards=cards,stagedImport=True,importedSource=DECK_URL)
    for entry in cards:
        if not legacy:entry['metadataSource']=entry['scryfall']['id']
    rows=[assignment(removed,partner,2),assignment(cards[2]) if treatment=='deck-wide' else assignment(partner)]
    deck['settings']['tokenAssignments']=rows
    deck['settings']['tokenTreatments']=[{'face':token_assignments.reference(removed),'options':{'nonlegendary':True}}] if treatment=='individual' else []
    deck=ws.store.put('decks',deck,deck['revision']);before=ws.deck(deck['id'])
    expected={entry['id']:entry for entry in before['cards'] if entry['id']!=removed['id']}
    calls=[]
    def remote(url):
        calls.append(url)
        if url!=EXPORT_URL:
            value=next(entry['scryfall'] for entry in cards if url.endswith(entry['scryfall']['id']))
            return json.dumps(value).encode(),'application/json',{}
        return json.dumps({'name':'Derevi Illusion Tokens','entries':{'columna':[
            {'count':entry['quantity'],'card_digest':entry['scryfall']} for entry in cards if entry['id']!=removed['id']
        ],'columnb':[{'count':1,'found':False,'raw_text':''}]}}).encode(),'application/json',{}
    ws.net.transport=remote
    result=ws.refresh_deck(deck['id'],{'revision':deck['revision']});updated=result['deck']
    assert {entry['id'] for entry in updated['cards']}==set(expected)
    assert 'Badgermole Cub' not in [entry['name'] for entry in updated['cards']]
    assert result['changes']['removed']==[{'name':'Badgermole Cub','quantity':removed['quantity']}]
    assert not result['changes']['added'] and result['changes']['local']==0
    assert updated['settings']['tokenAssignments']==[rows[1]] and not updated['settings']['tokenTreatments']
    assert not updated['tokens']['invalid'] and removed['id'] not in updated['tokens']['cardIds']
    for entry in updated['cards']:assert entry['faces']==expected[entry['id']]['faces']
    assert calls==[EXPORT_URL]


def test_refresh_repairs_previous_duplicate_token_faces_and_keeps_the_rendered_original(env):
    ws,deck,remote=env;kept=deck['cards'][0]
    duplicate=ws.sources.entry(kept['scryfall'],kept['quantity'],kept['section'])
    duplicate['metadataSource']=kept['scryfall']['id']
    deck.update(cards=[duplicate,*deck['cards']],stagedImport=True)
    deck['settings']['allCardsTokens']=True
    ws.store.put('decks',deck,deck['revision']);expected=copy.deepcopy(ws.deck(deck['id'])['cards'][1])
    remote['rows']=[(CARD_A,2,'mainboard')]
    result=refresh(env)
    assert result['deck']['cards']==[expected]
    assert result['deck']['tokens']['cardIds']==[kept['id']]
    assert len(result['deck']['tokens']['faces'])==1
    assert remote['calls']==[EXPORT_URL]


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
