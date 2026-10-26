import copy,io,json,zipfile
import pytest
from PIL import Image
from foundry.storage import Store
from foundry.network import Network
from foundry.workspace import Workspace
from foundry.domain import uid,ValidationError,PIPELINE_VERSION,type_group
from foundry.orders import Orders
from foundry.card_data import parse_document,document_settings
from foundry import token_assignments as tokens
from test_github_data_refresh import env


@pytest.fixture
def token_deck(tmp_path):
    store=Store(tmp_path);ws=Workspace(store,Network(store));deck=ws.new_deck('Tokens')
    images=[]
    for color in ('red','green','blue','yellow'):
        buffer=io.BytesIO();Image.new('RGB',(40,56),color).save(buffer,'PNG')
        images.append(store.add_asset(buffer.getvalue(),'image/png',40,56))
    cards=[]
    for number,(name,layout,kind) in enumerate([('Angel','token','Token Creature — Angel'),('Germ','token','Token Creature — Germ'),('Ordinary','normal','Creature — Human'),('Day // Night','double_faced_token','Card')]):
        sf={'id':uid(),'oracle_id':uid(),'name':name,'layout':layout,'type_line':kind,'oracle_text':'Flying' if number==0 else ''}
        if number==3:sf['card_faces']=[{'name':'Day','type_line':'Card'},{'name':'Night','type_line':'Card'}]
        card=ws.sources.entry(sf,number+2)
        for face in card['faces']:
            raw=(sf.get('card_faces') or [sf])[face['index']];group=type_group(raw,sf,face['index'])
            key,version,_=ws.compiler.template_identity(group,'auto')
            render=uid();store.render_put(render,images[(number+face['index'])%len(images)])
            face['compiled']={'renderKey':render,'generationVersion':PIPELINE_VERSION,'templateKey':key,'templateVersion':version,'data':{'width':40,'height':56},'render':store.render_get(render)}
        cards.append(card)
    deck.update(cards=cards,status='prepared');deck=store.put('decks',deck,deck['revision'])
    return ws,ws.deck(deck['id']),cards


def assignment(front,back=None,count=1):
    return {'front':tokens.reference(front),'back':tokens.reference(back) if back else {'kind':'card-back'},'quantity':count}


def test_initial_tokens_unassigned_and_natural_reverse_is_already_physical(token_deck):
    ws,deck,cards=token_deck
    assert deck['status']=='ready' and deck['printStatus']=='tokens-not-ready'
    assert {r['name'] for r in deck['tokens']['unused']}=={'Angel','Germ'}
    assert [r['used'] for r in deck['tokens']['faces']]==[0,0]
    assert len(deck['tokens']['assigned'])==1 and deck['tokens']['assigned'][0]['backKind']=='reverse'
    assert len(deck['tokens']['faces'])==2
    with pytest.raises(ValidationError,match='Angel, Germ.*Token Review'):Orders(ws).plan([deck['id']])


def test_pair_quantities_back_usage_and_print_images_are_independent_of_source(token_deck):
    ws,deck,cards=token_deck
    row=assignment(cards[0],cards[1],7)
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[row]})
    saved=ws.deck(deck['id']);assert saved['tokens']['ready'] and saved['printStatus']=='ready'
    assert [f['used'] for f in saved['tokens']['faces']]==[7,7]
    assert [c['quantity'] for c in saved['cards']]==[2,3,4,5]
    plan=Orders(ws).plan([deck['id']]);assert plan['count']==4+5+7
    pair=[c for c in plan['cards'] if c['name']=='Angel / Germ'];assert len(pair)==7
    assert pair[0]['frontAsset']==cards[0]['faces'][0]['compiled']['render']['asset_id']
    assert pair[0]['backAsset']==cards[1]['faces'][0]['compiled']['render']['asset_id']
    assert saved['summary']['physicalCards']==plan['count']
    order=Orders(ws).build([deck['id']])
    with zipfile.ZipFile(ws.store.home/'orders'/(order['id']+'.zip')) as archive:
        index=next(c['index'] for c in order['cards'] if c['name']=='Angel / Germ')
        assert archive.read(f'BACK/{index:06d}.png')==ws.store.asset_path(pair[0]['backAsset']).read_bytes()


def test_pairing_changes_never_invalidate_face_renders_or_preparation_keys(token_deck):
    ws,deck,cards=token_deck;before=copy.deepcopy([c['faces'] for c in deck['cards']])
    keys=[ws._preparation_key(card,deck['settings'],{}) for card in deck['cards']]
    for count in (1,8):
        current=ws.deck(deck['id'])
        ws.save(deck['id'],{'revision':current['revision'],'tokenAssignments':[assignment(cards[0],cards[1],count)]})
        result=ws.deck(deck['id']);assert result['status']=='ready'
        assert [c['faces'] for c in result['cards']]==before
        assert [ws._preparation_key(card,result['settings'],{}) for card in result['cards']]==keys


def test_assigned_faces_remain_available_for_multiple_distinct_tokens(token_deck):
    ws,deck,cards=token_deck
    rows=[assignment(cards[0],cards[1],7),assignment(cards[0],None,2),assignment(cards[1],None,3)]
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':rows})
    result=ws.deck(deck['id'])
    assert len(result['tokens']['faces'])==2
    assert [face['used'] for face in result['tokens']['faces']]==[9,10]
    assert len(result['tokens']['assigned'])==4
    assert result['tokens']['ready']


@pytest.mark.parametrize('count',[0,-1,10000,True,1.5,'2'])
def test_invalid_quantities_rejected(token_deck,count):
    _,_,cards=token_deck
    with pytest.raises(ValidationError):tokens.validate_assignments([assignment(cards[0],cards[1],count)])


def test_reverse_duplicate_and_self_pair_rejected(token_deck):
    _,_,cards=token_deck
    with pytest.raises(ValidationError,match='already exists'):
        tokens.validate_assignments([assignment(cards[0],cards[1]),assignment(cards[1],cards[0])])
    with pytest.raises(ValidationError,match='same face'):
        tokens.validate_assignments([assignment(cards[0],cards[0])])


def test_non_tokens_and_natural_tokens_cannot_be_used_as_back_candidates(token_deck):
    ws,deck,cards=token_deck
    for back in (cards[2],cards[3]):
        with pytest.raises(ValidationError,match='single-sided token'):
            ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[assignment(cards[0],back)]})


def test_normal_backs_explicit_and_multiple_pairs_count_both_sides(token_deck):
    ws,deck,cards=token_deck
    rows=[assignment(cards[0],cards[1],2),assignment(cards[0],None,4)]
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':rows})
    result=ws.deck(deck['id']);assert [f['used'] for f in result['tokens']['faces']]==[6,2]
    plan=Orders(ws).plan([deck['id']]);normal=[c for c in plan['cards'] if c['name']=='Angel']
    assert len(normal)==4 and normal[0]['backAsset']==deck['settings']['backAsset']


def test_natural_quantity_can_be_overridden_without_exposing_its_faces(token_deck):
    ws,deck,cards=token_deck
    rows=[assignment(cards[0],cards[1]),{'front':tokens.reference(cards[3]),'back':{'kind':'reverse'},'quantity':9}]
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':rows})
    report=ws.deck(deck['id'])['tokens']
    assert len(report['faces'])==2 and len(report['assigned'])==2 and report['physicalCount']==10


def test_convert_existing_card_and_roundtrip_data_file(token_deck):
    ws,deck,cards=token_deck;original=cards[2]
    ws.mutate_card(deck['id'],original['id'],{'revision':deck['revision'],'tokenSpec':{'nonlegendary':True,'power_toughness':'1/1'}})
    result=ws.deck(deck['id']);assert len(result['cards'])==4
    assert original['id'] in result['tokens']['cardIds'] and len(result['tokens']['unused'])==3
    assert not result['cards'][2]['faces'][0].get('compiled')
    document={'version':1,'cards':[],'tokenAssignments':[assignment(cards[0],cards[1],6)],'tokenTreatments':result['settings']['tokenTreatments']}
    raw=json.dumps(document).encode();assert parse_document(raw)==[]
    settings=document_settings(raw);fresh=copy.deepcopy(deck);fresh['id']=uid();fresh['settings'].update(settings)
    for card in fresh['cards']:
        card['id']=uid()
        for face in card['faces']:face['id']=uid()
    fresh=ws.store.put('decks',fresh);reloaded=ws.deck(fresh['id'])
    assert reloaded['cards'][2]['tokenSpec']['power_toughness']=='1/1'
    assert [f['used'] for f in reloaded['tokens']['faces']]==[6,6,0]


def test_deck_wide_treatment_is_classified_without_rendering(token_deck):
    _,deck,_=token_deck;deck['settings']['allCardsTokens']=True
    assert len(tokens.overview(deck)['cardIds'])==4


def test_individual_token_conversion_turns_off_flavor_only_for_that_card(token_deck):
    ws,deck,cards=token_deck;original=cards[2]
    before=copy.deepcopy(ws.deck(deck['id']));flavor='Keep the original printing flavor.'
    original['scryfall']['flavor_text']=flavor
    deck=ws.store.put('decks',{**deck,'cards':cards},deck['revision'])
    saved=ws.mutate_card(deck['id'],original['id'],{'revision':deck['revision'],'tokenSpec':{'nonlegendary':True}})
    face=saved['cards'][2]['faces'][0]
    assert face['semanticOverrides']['flavor_text']=='' and saved['settings']['showFlavorText'] is True
    assert saved['cards'][2]['scryfall']['flavor_text']==flavor
    assert saved['cards'][0]['faces']==before['cards'][0]['faces']
    restored=ws.mutate_card(deck['id'],original['id'],{'revision':saved['revision'],'faceId':face['id'],
        'semanticOverrides':{'flavor_text':'Explicitly restored flavor'}})
    tweaked=ws.mutate_card(deck['id'],original['id'],{'revision':restored['revision'],'tokenSpec':{'nonlegendary':False}})
    assert tweaked['cards'][2]['faces'][0]['semanticOverrides']['flavor_text']=='Explicitly restored flavor'


def test_deck_wide_token_conversion_turns_off_flavor_but_allows_a_later_explicit_choice(token_deck):
    ws,deck,_=token_deck
    first=ws.save(deck['id'],{'revision':deck['revision'],'settings':{'allCardsTokens':True}})
    assert first['settings']['allCardsTokens'] and first['settings']['showFlavorText'] is False
    restored=ws.save(deck['id'],{'revision':first['revision'],'settings':{'showFlavorText':True}})
    assert restored['settings']['allCardsTokens'] and restored['settings']['showFlavorText']
    off=ws.save(deck['id'],{'revision':restored['revision'],'settings':{'allCardsTokens':False}})
    enabled=ws.save(deck['id'],{'revision':off['revision'],'settings':{'allCardsTokens':True,'showFlavorText':True}})
    assert enabled['settings']['showFlavorText'] is False


def test_missing_partner_is_ignored_but_present_token_still_needs_a_back(token_deck):
    ws,deck,cards=token_deck
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[assignment(cards[0],cards[1])]})
    current=ws.deck(deck['id']);ws.mutate_card(deck['id'],cards[1]['id'],{'revision':current['revision'],'remove':True})
    report=ws.deck(deck['id'])['tokens'];assert not report['invalid'] and report['unused']
    with pytest.raises(ValidationError,match='Tokens not ready'):Orders(ws).plan([deck['id']])
    current=ws.deck(deck['id']);ws.save(deck['id'],{'revision':current['revision'],'tokenAssignments':[]})
    assert not ws.deck(deck['id'])['tokens']['invalid']


def test_shared_token_assignments_do_not_block_normal_deck_or_change_print_counts(token_deck):
    ws,deck,cards=token_deck
    rows=[assignment(cards[0],cards[1],7),assignment(cards[2],None,8)]
    deck['cards']=[cards[2]]
    deck=ws.store.put('decks',deck,deck['revision'])
    ws.save(deck['id'],{'revision':deck['revision'],'settings':{'tokenAssignments':rows}})
    result=ws.deck(deck['id'])
    assert result['tokens']['ready'] and result['printStatus']=='ready'
    assert not result['tokens']['invalid'] and not result['tokens']['cardIds'] and not result['tokens']['assigned']
    assert result['settings']['tokenAssignments']==rows
    plan=Orders(ws).plan([deck['id']])
    assert plan['count']==cards[2]['quantity']
    assert {row['name'] for row in plan['cards']}=={cards[2]['name']}


def test_shared_pairs_preserved_when_saving_subset_and_apply_when_partner_returns(token_deck):
    ws,deck,cards=token_deck
    original=assignment(cards[0],cards[1],2)
    deck['settings']['tokenAssignments']=[original]
    deck['cards']=[cards[0],cards[2]]
    deck=ws.store.put('decks',deck,deck['revision'])
    report=ws.deck(deck['id'])['tokens']
    assert not report['invalid'] and report['unused']==[{'cardId':cards[0]['id'],'name':'Angel'}]
    rows=[original,assignment(cards[0],None,3)]
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':rows})
    saved=ws.deck(deck['id'])
    assert saved['tokens']['ready'] and saved['settings']['tokenAssignments']==rows
    assert Orders(ws).plan([deck['id']])['count']==3+cards[2]['quantity']
    saved['cards'].append(cards[1]);ws.store.put('decks',saved,saved['revision'])
    report=ws.deck(deck['id'])['tokens']
    assert report['ready'] and len(report['assigned'])==2
    assert {face['cardId']:face['used'] for face in report['faces']}=={cards[0]['id']:5,cards[1]['id']:2}
    assert report['physicalCount']==5


def test_reimported_printing_resolves_by_oracle_and_name(token_deck):
    _,deck,cards=token_deck;ref=tokens.reference(cards[0]);card=copy.deepcopy(cards[0]);card['scryfall']['id']=uid()
    assert tokens.resolve([card],ref)==card


def test_saved_file_assignments_import_in_setup_and_refresh_from_github(token_deck):
    from foundry import github_data
    ws,deck,cards=token_deck
    document={'version':1,'cards':[],'tokenAssignments':[assignment(cards[0],cards[1],3)],'tokenTreatments':[]}
    settings=document_settings(json.dumps(document).encode())
    ws.save(deck['id'],{'revision':deck['revision'],'settings':settings})
    current=ws.deck(deck['id']);assert current['tokens']['ready']
    assert current['tokens']['faces'][0]['used']==3
    current['settings']['dataJsonSource']={'kind':'github','value':'https://github.com/owner/repo/blob/main/data.json'}
    ws.store.put('decks',current,current['revision'])
    class Remote:
        def json(self,*args,**kwargs):return {'sha':'a'*40}
        def fresh_json(self,url):return self.json(url,ttl=0)
        def fetch(self,*args,**kwargs):return json.dumps({**document,'tokenAssignments':[assignment(cards[0],cards[1],8)]}).encode(),'application/json',None
    ws.net=Remote();refreshed=github_data.refresh(ws,ws.deck(deck['id']))
    assert refreshed['tokens']['faces'][0]['used']==8 and refreshed['status']=='ready'
    assert [card['faces'] for card in refreshed['cards']]==[card['faces'] for card in current['cards']]


def test_existing_invalid_assignments_can_be_removed_one_at_a_time(token_deck):
    ws,deck,cards=token_deck
    rows=[assignment(cards[3],None),{'front':tokens.reference(cards[0]),'back':{'kind':'reverse'},'quantity':1}]
    deck['settings']['tokenAssignments']=rows;ws.store.put('decks',deck,deck['revision'])
    current=ws.deck(deck['id']);assert len(current['tokens']['invalid'])==2
    ws.save(deck['id'],{'revision':current['revision'],'tokenAssignments':rows[1:]})
    assert len(ws.deck(deck['id'])['tokens']['invalid'])==1


def test_stale_revision_does_not_overwrite_another_assignment(token_deck):
    from foundry.domain import ConflictError
    ws,deck,cards=token_deck
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[assignment(cards[0],cards[1],4)]})
    with pytest.raises(ConflictError):
        ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[assignment(cards[0],cards[1],9)]})
    assert ws.deck(deck['id'])['tokens']['faces'][0]['used']==4


def test_back_face_warnings_reference_the_correct_card_once(token_deck):
    ws,deck,cards=token_deck;face=cards[1]['faces'][0];face['compiled']['flags']=['Review']
    deck['cards']=cards;deck=ws.store.put('decks',deck,deck['revision'])
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[assignment(cards[0],cards[1]),assignment(cards[1],None)]})
    plan=Orders(ws).plan([deck['id']]);assert len(plan['issues'])==1
    issue=plan['issues'][0];assert issue['cardId']==cards[1]['id'] and issue['faceId']==face['id']
    current=ws.deck(deck['id']);ws.mutate_card(deck['id'],issue['cardId'],{'revision':current['revision'],'faceId':issue['faceId'],'acceptWarning':True,'renderKey':issue['renderKey']})
    assert not Orders(ws).plan([deck['id']])['issues']


def test_token_pairings_do_not_leak_into_reusable_style_defaults(token_deck):
    ws,deck,cards=token_deck
    ws.save(deck['id'],{'revision':deck['revision'],'tokenAssignments':[assignment(cards[0],cards[1])]})
    preset=ws.save_style_preset(deck['id'],'Style')
    assert 'tokenAssignments' not in preset['settings'] and 'tokenTreatments' not in preset['settings']
    ws.set_global_settings({'defaultStylePresetId':preset['id']})
    assert ws.new_deck()['settings']['tokenAssignments']==[]


def test_duplicate_import_rows_share_a_face_and_default_quantity(token_deck):
    ws,deck,cards=token_deck
    duplicate=copy.deepcopy(cards[0]);duplicate['id']=uid();duplicate['quantity']=4;duplicate['section']='tokens'
    deck['cards'].append(duplicate);report=tokens.overview(deck)
    assert len(report['faces'])==2 and report['faces'][0]['suggestedQuantity']==6
    assert duplicate['id'] in report['cardIds']
    deck['settings']['tokenAssignments']=[assignment(cards[0],cards[1],3)]
    assert tokens.overview(deck)['ready']


def test_distinct_printings_remain_distinct_token_faces(token_deck):
    _,deck,cards=token_deck
    variant=copy.deepcopy(cards[0]);variant['id']=uid();variant['scryfall']['id']=uid();deck['cards'].append(variant)
    assert len(tokens.overview(deck)['faces'])==3
    rows=tokens.validate_assignments([assignment(cards[0],variant)])
    deck['settings']['tokenAssignments']=rows
    assert len(tokens.overview(deck)['unused'])==1


def test_converted_card_prepares_with_existing_native_token_renderer(env):
    ws,deck,_=env;card=deck['cards'][0]
    card['scryfall'].update(layout='normal',type_line='Creature — Angel')
    deck['settings']['dataJsonSource']={'kind':'local','value':'data.json'}
    deck['settings']['templateRules']['token']='token-classic'
    deck=ws.store.put('decks',deck,deck['revision']);prepared=ws.prepare(deck['id'])
    changed=ws.mutate_card(deck['id'],card['id'],{'revision':prepared['revision'],
        'tokenSpec':{'nonlegendary':True,'power_toughness':'1/1','replace_creature_subtypes':['Spirit']}})
    result=ws.prepare(deck['id']);converted=result['cards'][0]['faces'][0]['compiled']
    assert converted['recipe']=='Card Tools copy token'
    assert converted['data']['text']['pt']['text']=='1/1'
    assert converted['data']['version'].startswith('token') and 'Spirit' in converted['data']['text']['type']['text']
    assert len(result['cards'])==3 and changed['settings']['tokenTreatments']


@pytest.mark.parametrize('back',[{'kind':[]},{'kind':'unknown'},None,{'name':False}])
def test_malformed_back_references_are_validation_errors(back):
    with pytest.raises(ValidationError):
        parse_document(json.dumps({'version':1,'cards':[],'tokenAssignments':[{'front':{'name':'Angel'},'back':back,'quantity':1}]}).encode())
