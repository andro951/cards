import io
import pytest
from PIL import Image
from foundry.compiler import Compiler,semantic,FULL_ART_NONLAND_BOUNDS,SHORT_TOKEN_ART_VERSION,fit_token_art
from foundry.workspace import Workspace
from foundry.images import ingest_image
from foundry.artwork import ArtworkIndex
from test_pipeline import workspace


def card(native=False):
    return {'name':'Aerith Gainsborough','layout':'token' if native else 'normal',
        'type_line':('Token ' if native else 'Legendary ')+'Creature — Human Cleric',
        'colors':['W'],'mana_cost':'{2}{W}','rarity':'rare','power':'2','toughness':'2',
        'oracle_text':'Lifelink\nWhenever you gain life, put a +1/+1 counter on Aerith Gainsborough.'}


def assert_covers_canvas(data,size):
    left=data['artX']*data['width'];top=data['artY']*data['height'];zoom=data['artZoom']
    assert left<=1e-6 and top<=1e-6
    assert left+size[0]*zoom>=data['width']-1e-6
    assert top+size[1]*zoom>=data['height']-1e-6


@pytest.mark.parametrize('size',[(1060,1484),(1600,900),(900,900),(700,2100)])
@pytest.mark.parametrize('native',[False,True])
def test_short_token_art_covers_all_four_card_edges(workspace,size,native):
    store,_,settings=workspace;raw=io.BytesIO();Image.new('RGB',size,'#684b32').save(raw,'PNG')
    art=ingest_image(store,raw.getvalue())['id'];sf=card(native);ws=Workspace(store)
    options={'semanticOverrides':{'nickname':'Jo Harvelle, Defiant Hunter'}}
    if native:options['templateOverride']='token-full-art-short'
    comp=ws.compiler.compile_face(sf,sf,0,options,settings,art)
    if not native:
        sem=semantic(sf,sf);sem['nickname']='Jo Harvelle, Defiant Hunter'
        comp=ws._apply_token_spec(comp,{'token_frame_style':'token-full-art-short'},art,'Copy token',sem=sem)
    data=comp['data']
    assert data['version']=='tokenShort'
    assert data['artBounds']==FULL_ART_NONLAND_BOUNDS
    assert data['shortTokenArtVersion']==SHORT_TOKEN_ART_VERSION
    assert_covers_canvas(data,size)


def test_disabled_autofit_preserves_the_art_placement(workspace):
    store,art,_=workspace
    data={'version':'tokenShort','width':2010,'height':2814,'artX':.12,'artY':-.2,'artZoom':2.3,'artRotate':15}
    fit_token_art(data,str(store.asset_path(art)),False)
    assert {k:data[k] for k in ['artX','artY','artZoom','artRotate']}=={'artX':.12,'artY':-.2,'artZoom':2.3,'artRotate':15}


def test_native_cache_refresh_is_scoped_to_short_tokens(workspace,monkeypatch):
    import foundry.compiler as module
    compiler=Compiler(workspace[0]);sf=card(True)
    selections=[('token','auto',sf),('token','token-full-art-short',sf),('token','token-classic',sf),
        ('token','token-full-art',sf),('legendary','auto',card()),('token','auto',None)]
    previous=[compiler.template_identity(*args) for args in selections]
    monkeypatch.setattr(module,'SHORT_TOKEN_ART_VERSION',SHORT_TOKEN_ART_VERSION+1)
    current=[compiler.template_identity(*args) for args in selections]
    assert current[0]!=previous[0] and current[1]!=previous[1]
    assert current[2:]==previous[2:]


def test_converted_token_refresh_is_scoped_to_the_selected_style(workspace,monkeypatch):
    import foundry.workspace as module
    store,art,settings=workspace;ws=Workspace(store);entry=ws.sources.entry(card())
    entry['faces'][0]['artOverride']=art;index=ArtworkIndex({})
    short=ws.validate_settings({**settings,'allCardsTokens':True})
    classic=ws.validate_settings({**short,'templateRules':{'token':'token-classic'}})
    plain=ws.validate_settings(settings)
    keys=[ws._preparation_key(entry,s,index) for s in [short,classic,plain]]
    monkeypatch.setattr(module,'SHORT_TOKEN_ART_VERSION',SHORT_TOKEN_ART_VERSION+1)
    assert ws._preparation_key(entry,short,index)!=keys[0]
    assert ws._preparation_key(entry,classic,index)==keys[1]
    assert ws._preparation_key(entry,plain,index)==keys[2]


@pytest.mark.parametrize('scope',['card','deck','both'])
def test_existing_converted_decks_refresh_the_art_fit_and_then_reuse_it(workspace,monkeypatch,scope):
    import foundry.workspace as workspace_module
    import foundry.compiler as compiler_module
    store,art,settings=workspace;ws=Workspace(store);deck=ws.new_deck('Short token fill')
    entry=ws.sources.entry(card());entry['faces'][0]['artOverride']=art
    if scope in {'card','both'}:entry['tokenSpec']={'nonlegendary':True}
    deck['settings']=ws.validate_settings({**settings,'allCardsTokens':scope in {'deck','both'}})
    deck['cards']=[entry];store.put('decks',deck,deck['revision'])
    prepared=ws.prepare(deck['id']);face=prepared['cards'][0]['faces'][0]
    assert not face.get('error')
    assert_covers_canvas(face['compiled']['data'],(900,900))
    version=SHORT_TOKEN_ART_VERSION+1
    monkeypatch.setattr(workspace_module,'SHORT_TOKEN_ART_VERSION',version)
    monkeypatch.setattr(compiler_module,'SHORT_TOKEN_ART_VERSION',version)
    compile=ws.compiler.compile_face;calls=[]
    def tracked(*args,**kwargs):calls.append(1);return compile(*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    refreshed=ws.prepare(deck['id']);data=refreshed['cards'][0]['faces'][0]['compiled']['data']
    assert calls==[1] and data['shortTokenArtVersion']==version
    assert_covers_canvas(data,(900,900));calls.clear()
    assert ws.prepare(deck['id'])['cards']==refreshed['cards']
    assert not calls
