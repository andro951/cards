"""Identity-based artwork review never downloads or renders artwork."""
import copy,json,time
import pytest
from foundry.artwork import ArtworkIndex,build_review
from foundry.card_data import parse_document,validate_targets
from foundry.domain import ValidationError
from foundry.workspace import Workspace,DEFAULT_SETTINGS
from foundry.storage import Store
from foundry.network import Network

ONE='dc4e2134-f0c2-49aa-9ea3-ebf83af1445c'
TWO='6a7a9dff-ff9e-4005-a17f-6ea0c11c1d5a'
def card(oracle=ONE,name='Spirit'):
    return {'id':oracle,'name':name,'quantity':1,'scryfall':{'id':oracle,'oracle_id':oracle,'name':name,'image_uris':{'normal':'https://cards.scryfall.io/'+oracle+'.jpg'}},'faces':[{'id':oracle,'index':0,'name':name}]}
def settings():
    s=copy.deepcopy(DEFAULT_SETTINGS);s['source'].update(mode='local',localFiles={});return s

def test_explicit_file_then_uuid_then_name():
    index=ArtworkIndex({'spirit':'a','uuid':'b','choice':'c'},{'spirit':'spirit.png','uuid':'my_'+ONE+'_drawing.png','choice':'arbitrary.png'})
    assert index.resolve('Spirit',ONE)=='uuid'
    assert index.resolve('Spirit',ONE,'arbitrary.png')=='choice'
    assert index.resolve('Spirit',TWO)=='spirit'
    assert index.resolve('Other') is None
    with pytest.raises(ValidationError,match='missing'):index.resolve('Spirit',ONE,'missing.png')
    assert index.resolve('Unknown',printing_id=ONE)=='uuid'

def test_token_variants_do_not_share_name_match():
    review=build_review({'cards':[card(),card(TWO)]},settings(),ArtworkIndex({'spirit':'a'}))
    assert review['missing']==2 and all(row['status']=='conflict' for row in review['items'])
    assert review['unused'][0]['filename']=='spirit.png'
    for row in [card(),card(TWO)]:row['faces'][0]['artFilename']='spirit.png'
    rows=[card(),card(TWO)]
    for row in rows:row['faces'][0]['artFilename']='spirit.png'
    assert not build_review({'cards':rows},settings(),ArtworkIndex({'spirit':'a'}))['needsReview']

def test_duplicates_missing_mapping_and_unused_acknowledgement():
    index=ArtworkIndex({'first':'a','second':'b'},{'first':'112_spirit.png','second':'113_spirit.png'})
    with pytest.raises(ValidationError,match='Multiple'):index.resolve('Spirit')
    c=card();c['faces'][0]['artFilename']='112_spirit.png';s=settings()
    result=build_review({'cards':[c]},s,index);assert result['missing']==0 and result['needsReview']
    s['artReviewSignature']=result['signature'];assert not build_review({'cards':[c]},s,index)['needsReview']
    c['faces'][0]['artFilename']='nonexistent.png';s['source']['fallback']=True
    assert build_review({'cards':[c]},s,index)['items'][0]['status']=='conflict'
    index['third']='c';index=ArtworkIndex(index,{**index.names,'third':'extra.png'})
    assert build_review({'cards':[c]},s,index)['needsReview']

def test_double_face_uuid_needs_face_qualifier():
    index=ArtworkIndex({'day':'a','night':'b'},{'day':ONE+'_day.png','night':'night_'+ONE+'.png'})
    assert index.resolve('Day',ONE,multiface=True)=='day'
    assert index.resolve('Night',ONE,multiface=True)=='night'
    with pytest.raises(ValidationError):index.resolve('Day',ONE)

@pytest.mark.parametrize('art',['../x.png','C:/x.png','/x.png','a\\b.png','a//b.png','x.txt'])
def test_mapping_rejects_unsafe_filename(art):
    with pytest.raises(ValidationError):parse_document(json.dumps({'version':1,'cards':[{'oracle_id':ONE,'art':art}]}).encode())

def test_schema_ids_and_target_validation():
    entries=parse_document(json.dumps({'version':1,'cards':[{'oracle_id':ONE.upper(),'art':'my picture.png','artist':'Me'},{'name':'Spirit','nickname':''}]}).encode())
    assert entries==[{'oracle_id':ONE,'art':'my picture.png','artist':'Me'}]
    assert validate_targets({'cards':[card()]},entries)==entries
    with pytest.raises(ValidationError,match='not found'):validate_targets({'cards':[card(TWO)]},entries)
    with pytest.raises(ValidationError,match='multiple card variants'):validate_targets({'cards':[card(),card(TWO)]},[{'name':'Spirit','art':'spirit.png'}])
    with pytest.raises(ValidationError,match='Invalid'):parse_document(json.dumps({'version':1,'cards':[{'oracle_id':'wrong','art':'x.png'}]}).encode())

def test_workspace_review_and_save_are_atomic_and_metadata_only(tmp_path):
    def transport(url):raise AssertionError('Review fetched '+url)
    store=Store(tmp_path);ws=Workspace(store,Network(store,transport=transport));s=settings()
    asset=store.add_asset(b'artwork','image/png',1,1)
    s['source']['localFiles']={'custom':asset['id']};s['source']['localNames']={'custom':'whatever.png'}
    deck=store.put('decks',{'id':ONE,'name':'Review','settings':s,'cards':[card()]})
    payload={'deckId':ONE,'cardData':[{'oracle_id':ONE,'art':'whatever.png','nickname':'Ghost'}]}
    steps=ws.artwork_review_steps(payload)
    while True:
        try:next(steps)
        except StopIteration as end:review=end.value;break
    assert not review['needsReview']
    assert not ws.deck(ONE)['cards'][0]['faces'][0].get('artFilename')
    saved=ws.save(ONE,{'revision':deck['revision'],'cardData':payload['cardData']})
    face=saved['cards'][0]['faces'][0];assert face['artFilename']=='whatever.png' and face['semanticOverrides']['nickname']=='Ghost'
    with pytest.raises(ValidationError):ws.save(ONE,{'revision':saved['revision'],'cardData':[{'oracle_id':TWO,'art':'other.png'}]})
    assert ws.deck(ONE)['revision']==saved['revision']

def test_large_inventory_is_indexed_once():
    started=time.perf_counter()
    index=ArtworkIndex({f'card_{i}':'a' for i in range(5000)})
    for i in range(5000):assert index.resolve(f'Card {i}')==f'card_{i}'
    elapsed=time.perf_counter()-started
    assert elapsed<1,elapsed


def test_github_keeps_colliding_names_for_visual_review():
    from foundry.sources import Sources
    class Remote:
        def json(self,url,**kwargs):
            if '/commits/' in url:return {'sha':'c'*40}
            return [{'type':'file','name':name,'path':'art/'+name,'sha':'a'*40} for name in ['spirit.png','spirit.jpg']]
    values=Sources(Remote()).github_index('https://github.com/owner/repo/tree/main/art')
    assert len(values)==2
    index=ArtworkIndex(values)
    assert index.resolve('Spirit',filename='spirit.jpg')=='spirit__2'


def test_large_card_data_uses_indexed_selectors():
    rows=[card(name='Card '+str(i)) for i in range(2000)]
    entries=[{'name':row['name'],'art':str(i)+'.png'} for i,row in enumerate(rows)]
    deck={'cards':rows,'settings':settings()}
    ws=object.__new__(Workspace)
    started=time.perf_counter();ws._apply_card_data(deck,entries);elapsed=time.perf_counter()-started
    assert all(row['faces'][0]['artFilename']==str(i)+'.png' for i,row in enumerate(rows))
    assert elapsed<1,elapsed



def test_reference_entries_roundtrip_without_overrides():
    entry={'name':'Spirit','oracle_id':ONE,'scryfall_url':'https://scryfall.com/card/tst/1/spirit'}
    entries=parse_document(json.dumps({'version':1,'cards':[entry]}).encode())
    assert entries==[entry]
    assert validate_targets({'cards':[card()]},entries)==entries
    assert parse_document(json.dumps({'version':1,'cards':[{'oracle_id':ONE}]}).encode())==[{'oracle_id':ONE}]


@pytest.mark.parametrize('url',['http://scryfall.com/card/tst/1','https://evil.example/card/tst/1','https://scryfall.com.evil.example/card/tst/1','https://scryfall.com@evil.example/card/tst/1','javascript:alert(1)','https://scryfall.com/card/bad link'])
def test_reference_entries_reject_invalid_links(url):
    with pytest.raises(ValidationError,match='Scryfall link'):
        parse_document(json.dumps({'version':1,'cards':[{'name':'Spirit','scryfall_url':url}]}).encode())
