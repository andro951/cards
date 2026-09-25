import copy,io
import pytest
from PIL import Image
from foundry.domain import *
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.images import ingest_image

@pytest.mark.parametrize('age,refresh,expected',[(365*DAY-1,False,True),(365*DAY,False,False),(7*DAY-1,True,True),(7*DAY,True,False)])
def test_cache_boundaries(age,refresh,expected):assert cache_is_fresh(0,age,refresh)==expected
@pytest.mark.parametrize('value',['C:\\cards\\art','file:///C:/cards','http://github.com/a/b','https://evil.test/a/b','https://github.com/a/b/tree/main/../x'])
def test_invalid_github_source(value):
    with pytest.raises(ValidationError):github_location(value)
def test_folders():
    assert github_location('https://github.com/a/b/tree/main/art')['folder']=='art'
    assert github_location('a/b/art',branch='images/v2')['ref']=='images/v2'
def test_lists():
    d=parse_deck_text('Commander\n1 Esika, God of the Tree (KHM) 168\nDeck\n4x Forest\n1 Fire // Ice\nSideboard\n1 Bad')
    assert [x['quantity'] for x in d]==[1,4,1]
    assert d[0]['source']=='khm:168'
@pytest.mark.parametrize('types,layout,index,group',[
    ('Artifact Creature — Myr','normal',0,'standard'),('Legendary Artifact — Equipment','normal',0,'legendary'),
    ('Artifact Land','normal',0,'land'),('Legendary Land','normal',0,'legendary-land'),('Basic Snow Land — Forest','normal',0,'basic-land'),
    ('Enchantment Creature — Saga','saga',0,'saga-creature'),('Legendary Planeswalker — Jace','normal',0,'planeswalker'),
    ('Land','modal_dfc',1,'modal-back'),('Creature','transform',0,'transform-front'),('Enchantment — Room','split',0,'room'),('Artifact — Spacecraft','normal',0,'station')])
def test_type_groups(types,layout,index,group):assert type_group({'type_line':types},{'layout':layout},index)==group
def test_crop_boundaries():
    d={'width':1000,'height':1000,'artBounds':{'width':1,'height':1}}
    assert not crop_metrics(1250,1000,d)['warning']
    assert crop_metrics(1251,1000,d)['warning']
    assert crop_metrics(1000,2000,d)['cropY']==.5
    assert crop_metrics(2000,1000,d)['cropX']==.5
def test_crop_actual_placement():
    d={'width':1000,'height':1000,'artBounds':{'width':1,'height':1},'artX':.3,'artY':0,'artZoom':1}
    assert crop_metrics(1000,1000,d)['cropX']==.3
def test_hash():
    d={'artSource':'a','frames':[]}
    assert render_key(d)==render_key(copy.deepcopy(d))
    assert render_key(d)!=render_key(d,'changed')
def test_revisions(tmp_path):
    s=Store(tmp_path);d=s.put('decks',{'name':'one'});s.put('decks',{**d,'name':'two'},d['revision'])
    with pytest.raises(ConflictError):s.put('decks',{**d,'name':'three'},d['revision'])
    assert s.get('decks',d['id'])['name']=='two'
    s.trash('decks',d['id']);assert s.get('decks',d['id']) is None
    s.trash('decks',d['id'],restore=True);assert s.get('decks',d['id'])['name']=='two'
    s.trash('decks',d['id']);trashed=s.get('decks',d['id'],include_deleted=True);s.purge('decks',d['id'],trashed['revision']);assert s.get('decks',d['id'],include_deleted=True) is None
    a=s.put('decks',{'name':'a'});b=s.put('decks',{'name':'b'});s.trash('decks',a['id']);s.trash('decks',b['id']);assert s.purge_trash('decks')['deleted']==2;assert s.list('decks',deleted=True)==[]
def test_assets(tmp_path):
    s=Store(tmp_path);a=s.add_asset(b'abc','text/plain');assert a['id']==s.add_asset(b'abc','text/plain')['id']
    with pytest.raises(ValidationError):s.asset_path('../x')


def test_bundled_set_symbols_are_defaults_and_uploads_replace_them(tmp_path):
    ws=Workspace(Store(tmp_path))
    deck=ws.new_deck('Bundled symbols')
    defaults=dict(deck['settings']['symbols'])
    assert set(defaults)==set(RARITIES)
    assert all(ws.store.asset(defaults[r]) for r in RARITIES)

    # A legacy deck with no selections should present the bundled defaults too.
    legacy=ws.store.put('decks',{
        'name':'Legacy symbols','cards':[],'settings':{'symbols':{}},
        'status':'draft','notes':'','importedSource':'',
    })
    assert ws.deck(legacy['id'])['settings']['symbols']==defaults

    # Replacing one rarity keeps the bundled defaults for the other three.
    raw=io.BytesIO();Image.new('RGBA',(96,96),'#ba812b').save(raw,'PNG')
    custom=ingest_image(ws.store,raw.getvalue())['id']
    saved=ws.save(deck['id'],{
        'revision':deck['revision'],
        'settings':{'symbols':{'rare':custom}},
    })
    assert saved['settings']['symbols']['rare']==custom
    for rarity in ('common','uncommon','mythic'):
        assert saved['settings']['symbols'][rarity]==defaults[rarity]
