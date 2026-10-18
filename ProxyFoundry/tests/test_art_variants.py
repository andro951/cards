import copy,io,json
import pytest
from PIL import Image
from foundry import art_variants,token_assignments
from foundry.domain import uid,ValidationError
from foundry.card_data import parse_document,document_settings
from foundry.workspace import Workspace
from test_pipeline import workspace,sf


@pytest.fixture
def variant_deck(workspace):
    store,art,settings=workspace;ws=Workspace(store)
    image=io.BytesIO();Image.new('RGB',(900,900),'red').save(image,'PNG')
    alternate=store.add_asset(image.getvalue(),'image/png',900,900)['id']
    card=sf('Creature — Bird',['U']);card.update(name='Test Card',oracle_text='Flying')
    ws.net.transport=lambda url:(json.dumps(card).encode(),'application/json',{})
    entry=ws.sources.entry(card,4)
    settings={**settings,'source':{'mode':'local','localFiles':{'base':art,'alt':alternate},'localNames':{'base':'test_card.png','alt':'other_art.png'},'fallback':False}}
    deck=ws.new_deck('Alternate art')
    store.put('decks',{**deck,'cards':[entry],'settings':settings},deck['revision'])
    deck=ws.prepare(deck['id'])
    return ws,deck,alternate


def row(card,count=1,filename='other_art.png'):
    return {'id':uid(),'card':art_variants.reference(card),'quantity':count,'faces':[{'name':card['faces'][0]['name'],'art':filename}]}


def test_split_preserves_count_identity_and_cached_original(variant_deck,monkeypatch):
    ws,deck,alternate=variant_deck;original=deck['cards'][0];before=copy.deepcopy(original)
    variant=row(original)
    ws.save(deck['id'],{'revision':deck['revision'],'artVariants':[variant]})
    split=ws.deck(deck['id'])
    assert [card['quantity'] for card in split['cards']]==[3,1]
    assert split['cards'][0]['faces']==before['faces']
    assert split['cards'][1]['scryfall']==before['scryfall']
    assert split['cards'][1]['id']!=before['id'] and split['cards'][1]['artVariantId']==variant['id']
    calls=[];compile_face=ws.compiler.compile_face
    def tracked(*args,**kwargs):calls.append(True);return compile_face(*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    ready=ws.prepare(deck['id'])
    assert len(calls)==1
    assert ready['cards'][1]['faces'][0]['compiled']['artId']==alternate
    assert ready['cards'][0]['faces'][0]['compiled']['renderKey']==before['faces'][0]['compiled']['renderKey']
    current=ws.deck(deck['id']);variant['quantity']=2
    ws.save(deck['id'],{'revision':current['revision'],'artVariants':[variant]})
    calls.clear();ws.prepare(deck['id']);assert not calls


def test_move_all_restore_original_and_reimport(variant_deck):
    ws,deck,_=variant_deck;original=deck['cards'][0];variant=row(original,4)
    ws.save(deck['id'],{'revision':deck['revision'],'artVariants':[variant]})
    moved=ws.deck(deck['id']);assert len(moved['cards'])==1 and moved['cards'][0]['quantity']==4
    variant['quantity']=1
    ws.save(deck['id'],{'revision':moved['revision'],'artVariants':[variant]})
    split=ws.deck(deck['id']);assert [c['quantity'] for c in split['cards']]==[3,1]
    assert split['cards'][0]['id']==original['id']
    assert not split['cards'][0]['faces'][0].get('variantArtFilename')
    raw=json.dumps({'version':1,'cards':[],'artVariants':[variant]}).encode()
    assert parse_document(raw)==[]
    fresh=ws.new_deck('Reimported')
    ws.store.put('decks',{**fresh,'cards':[ws.sources.entry(original['scryfall'],4)]},fresh['revision'])
    fresh=ws.deck(fresh['id'])
    ws.save(fresh['id'],{'revision':fresh['revision'],'settings':document_settings(raw)})
    recreated=ws.deck(fresh['id'])
    assert [c['quantity'] for c in recreated['cards']]==[3,1]
    assert recreated['cards'][1]['artVariantId']==variant['id']


def test_split_cannot_increase_quantity_or_erase_unrelated_project_entries(variant_deck):
    ws,deck,_=variant_deck
    with pytest.raises(ValidationError,match='deck contains 4'):
        ws.save(deck['id'],{'revision':deck['revision'],'artVariants':[row(deck['cards'][0],5)]})
    assert ws.deck(deck['id'])['revision']==deck['revision']
    unrelated=row(deck['cards'][0]);unrelated['card']['scryfall_id']=uid()
    ws.save(deck['id'],{'revision':deck['revision'],'artVariants':[unrelated]})
    result=ws.deck(deck['id']);assert len(result['cards'])==1 and result['cards'][0]['quantity']==4
    assert result['settings']['artVariants']==[unrelated]


def test_variant_token_references_are_distinct_and_survive_pairing(variant_deck):
    ws,deck,_=variant_deck;variant=row(deck['cards'][0],2)
    ws.save(deck['id'],{'revision':deck['revision'],'artVariants':[variant],'settings':{'allCardsTokens':True}})
    split=ws.deck(deck['id']);base,alternate=split['cards']
    assert len(split['tokens']['faces'])==2
    front,back=token_assignments.reference(base),token_assignments.reference(alternate)
    assert token_assignments.key(front)!=token_assignments.key(back)
    assert back['art_variant']==variant['id']
    ws.save(deck['id'],{'revision':split['revision'],'tokenAssignments':[{'front':front,'back':back,'quantity':3}]})
    result=ws.deck(deck['id']);assert result['tokens']['ready']
    assert [f['used'] for f in result['tokens']['faces']]==[3,3]


def test_double_faced_variant_changes_only_selected_artwork(variant_deck):
    ws,deck,_=variant_deck
    card=ws.sources.entry({'id':uid(),'name':'Front // Back','layout':'transform','card_faces':[{'name':'Front','type_line':'Creature'},{'name':'Back','type_line':'Creature'}]},3)
    card['faces'][1]['artFilename']='back.png'
    card['faces'][0]['fit']={'artX':0.2}
    document={'cards':[card],'settings':{'artVariants':[row(card,1)]}}
    original_ids=[f['id'] for f in card['faces']]
    assert art_variants.apply(document,ws.invalidate_face)
    base,variant=document['cards']
    assert [c['quantity'] for c in document['cards']]==[2,1]
    assert [f['id'] for f in base['faces']]==original_ids
    assert variant['faces'][0]['variantArtFilename']=='other_art.png'
    assert base['faces'][0]['fit']=={'artX':0.2} and 'fit' not in variant['faces'][0]
    assert not variant['faces'][1].get('variantArtFilename')
    assert variant['faces'][1]['artFilename']=='back.png'


@pytest.mark.parametrize('change',[{'quantity':True},{'quantity':0},{'quantity':10000},{'faces':[{'name':'Test Card','art':'../bad.png'}]},{'faces':[{'name':'Test Card','art':'https://example.com/art.png'}]}])
def test_invalid_variant_data_is_rejected(variant_deck,change):
    _,deck,_=variant_deck
    with pytest.raises(ValidationError):art_variants.validate([{**row(deck['cards'][0]),**change}])