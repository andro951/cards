import copy,json
from pathlib import Path
import pytest
from foundry.compiler import Compiler,semantic,VERTICAL_TOKEN_LAYOUT_VERSION
from foundry.artwork import ArtworkIndex
from foundry.workspace import Workspace
from test_pipeline import workspace


def card(index):
    return json.loads((Path(__file__).parent/'fixtures/vertical_tokens.json').read_text(encoding='utf-8'))[index]


def compile_card(workspace,index,nickname=''):
    store,art,settings=workspace;sf=card(index)
    comp=Compiler(store).compile_face(sf,sf,0,{'semanticOverrides':{'nickname':nickname}},settings,art)
    sem=semantic(sf,sf);sem['nickname']=nickname
    return Workspace(store),comp,sem


@pytest.mark.parametrize('index',[0,1])
@pytest.mark.parametrize('nickname',['','Alternate Name'])
@pytest.mark.parametrize('style',['token-classic','token-full-art','token-borderless'])
def test_token_header_preserves_all_native_vertical_panels(workspace,index,nickname,style):
    ws,comp,sem=compile_card(workspace,index,nickname);source=copy.deepcopy(comp['data'])
    result=ws._apply_token_spec(comp,{'token_frame_style':style},workspace[1],'Copy token',sem=sem)
    data=result['data'];kind='class' if index==0 else 'saga'
    assert result['group']=='token' and result['renderKey']
    assert data['verticalToken']==kind
    assert data['verticalTokenLayoutVersion']==VERTICAL_TOKEN_LAYOUT_VERSION
    assert data['version']==source['version'] and data['onload']==source['onload']
    assert data[kind]==source[kind]
    assert data['artBounds']==source['artBounds']
    assert data['setSymbolBounds']==source['setSymbolBounds']
    assert 'rules' not in data['text']
    for key,field in source['text'].items():
        if key.startswith(('level','ability')) or key=='reminder':assert data['text'][key]==field
    assert 'Enchantment' in data['text']['type']['text']
    if index==1:assert 'Land' in data['text']['type']['text']
    headers=[f for f in data['frames'] if f.get('verticalTokenHeader')]
    assert headers and any('/token/m15/regular/' in f['src'] for f in headers)
    body=[f for f in data['frames'] if not f.get('verticalTokenHeader') and f['name']!='Nickname Title']
    assert body and all(sum(m['name']=='Native vertical panels' for m in f['masks'])==1 for f in body)
    if nickname:
        assert data['text']['nickname']['text']==nickname
        assert data['text']['title']['text']==sem['name']
        header_indices=[i for i,f in enumerate(data['frames']) if f.get('verticalTokenHeader')]
        bar_indices=[i for i,f in enumerate(data['frames']) if f['name']=='Nickname Title']
        body_indices=[i for i,f in enumerate(data['frames']) if f in body]
        assert max(header_indices)<min(bar_indices)
        assert max(bar_indices)<min(body_indices)


@pytest.mark.parametrize('index',[0,1])
@pytest.mark.parametrize('color',['A','R','M'])
def test_individual_and_deck_conversion_is_idempotent_and_preserves_types(workspace,index,color):
    ws,comp,sem=compile_card(workspace,index,'Alternate Name')
    spec={'force_legendary':True,'frame_color':color,'token_frame_style':'token-full-art'}
    once=ws._apply_token_spec(copy.deepcopy(comp),spec,workspace[1],'Token',sem=sem)
    staged=ws._apply_token_spec(comp,spec,workspace[1],'Token',sem=sem,finalize=False)
    twice=ws._apply_token_spec(staged,spec,workspace[1],'Token',sem=sem)
    assert twice['data']==once['data']
    assert twice['data']['text']['type']['text'].startswith('Legendary Enchantment')
    crowns=[f for f in twice['data']['frames'] if '/crowns/m15Crown' in f.get('src','')]
    outlines=[f for f in twice['data']['frames'] if f['name']=='Token crown outside outline']
    assert crowns and all(f.get('opacity')==100 for f in crowns)
    assert len(outlines)==1
    outline=outlines[0];bounds=outline['bounds']
    assert outline.get('opacity')==100
    assert outline['src'].endswith('/CrownHeaderOutline.png')
    assert not outline['masks']  # The new bottom stroke extends beyond the header crop.
    assert twice['data']['frames'].index(outline)<min(twice['data']['frames'].index(f) for f in crowns)
    for crown in crowns:
        inner=crown['bounds']
        assert bounds['x']<inner['x'] and bounds['y']<inner['y']
        assert bounds['x']+bounds['width']>inner['x']+inner['width']
        assert bounds['y']+bounds['height']>inner['y']+inner['height']


def test_crown_contour_closes_the_visible_bottom_without_outlining_the_title_opening():
    import io
    from PIL import Image,ImageDraw
    from scripts.build_vertical_token_crown_outline import header_outline
    crown=Image.new('RGBA',(1408,215),'white')
    ImageDraw.Draw(crown).rectangle((100,50,1307,150),fill=(0,0,0,0))
    raw=io.BytesIO();crown.save(raw,'PNG')
    outline=header_outline(raw.getvalue());alpha=outline.getchannel('A')
    assert outline.size==(1412,219)
    for x in (100,706,1300):assert alpha.getpixel((x,198))==255
    assert alpha.getpixel((706,205))==0
    assert alpha.getpixel((706,52))==0


@pytest.mark.parametrize('scope',['card','deck','both'])
def test_deck_generation_handles_class_and_saga_and_reuses_preparation(workspace,scope,monkeypatch):
    store,art,settings=workspace;ws=Workspace(store);deck=ws.new_deck('Vertical token regression')
    deck['settings']=ws.validate_settings({**settings,'allCardsTokens':scope in {'deck','both'},
        'tokenOptions':{'legendaryMode':'legendary'},'templateRules':{'token':'token-full-art'}})
    deck['cards']=[]
    monkeypatch.setattr(ws.sources,'resolve_card',lambda ident,*a,**k:next(card(i) for i in [0,1] if card(i)['id']==ident))
    for index in [0,1]:
        entry=ws.sources.entry(card(index));entry['faces'][0]['artOverride']=art
        entry['faces'][0]['semanticOverrides']={'nickname':'Alternate Name'}
        if scope in {'card','both'}:entry['tokenSpec']={'nonlegendary':True}
        deck['cards'].append(entry)
    store.put('decks',deck,deck['revision']);prepared=ws.prepare(deck['id'])
    for entry in prepared['cards']:
        face=entry['faces'][0]
        assert not face.get('error') and face['compiled']['data'].get('verticalToken')
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Unchanged token recompiled'))
    assert ws.prepare(deck['id'])['cards']==prepared['cards']
    for entry in prepared['cards']:
        face=entry['faces'][0];key=face['compiled']['renderKey']
        store.render_put(key,store.asset(art),deck_id=deck['id'],card_id=entry['id'],face_id=face['id'])
        face['acceptedWarningKey']=key
    store.put('decks',prepared,prepared['revision'])
    assert ws.deck(deck['id'])['status']=='ready'
    saved=store.get('decks',deck['id'])
    saved['cards'][0]['faces'][0]['compiled']['data']['verticalTokenLayoutVersion']='old'
    store.put('decks',saved,saved['revision'])
    assert ws.deck(deck['id'])['status']=='draft'


def test_layout_refresh_key_only_changes_converted_vertical_cards(workspace,monkeypatch):
    import foundry.workspace as module
    store,art,settings=workspace;ws=Workspace(store)
    sf=card(0);entry=ws.sources.entry(sf)
    entry['faces'][0]['artOverride']=art
    index=ArtworkIndex({})
    normal=ws.validate_settings(settings);token=ws.validate_settings({**settings,'allCardsTokens':True})
    normal_key=ws._preparation_key(entry,normal,index);token_key=ws._preparation_key(entry,token,index)
    monkeypatch.setattr(module,'VERTICAL_TOKEN_LAYOUT_VERSION','next-version')
    assert ws._preparation_key(entry,normal,index)==normal_key
    assert ws._preparation_key(entry,token,index)!=token_key
