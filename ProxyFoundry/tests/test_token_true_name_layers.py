import copy
import pytest
from foundry.compiler import Compiler,semantic,TOKEN_TRUE_NAME_LAYER_VERSION
from foundry.workspace import Workspace
from foundry.artwork import ArtworkIndex
from test_pipeline import workspace


def source(native,legendary):
    return {'name':'Test Token','layout':'token' if native else 'normal',
        'type_line':('Legendary ' if legendary else '')+('Token ' if native else '')+'Artifact Creature — Construct',
        'colors':['R','W'],'mana_cost':'{2}{R}{W}','oracle_text':'Vigilance',
        'power':'2','toughness':'2','rarity':'rare'}


@pytest.mark.parametrize('style',['token-classic','token-full-art','token-full-art-short','token-borderless'])
@pytest.mark.parametrize('legendary',[False,True])
@pytest.mark.parametrize('native',[False,True])
def test_every_token_style_places_true_name_under_title_and_crown(workspace,style,legendary,native):
    store,art,settings=workspace;compiler=Compiler(store);sf=source(native,legendary)
    options={'semanticOverrides':{'nickname':'Alternate Name'}}
    if native:options['templateOverride']=style
    comp=compiler.compile_face(sf,sf,0,options,settings,art)
    if not native:
        sem=semantic(sf,sf);sem['nickname']='Alternate Name'
        comp=Workspace(store)._apply_token_spec(comp,{'token_frame_style':style},art,'Copy token',sem=sem)
    data=comp['data'];frames=data['frames']
    bars=[i for i,f in enumerate(frames) if f['name']=='Nickname Title']
    headers=[i for i,f in enumerate(frames) if f.get('tokenTrueNameHeader') or 'Crown' in f['name']]
    body=[i for i,f in enumerate(frames) if any(m.get('name')=='Token body below true name' for m in f.get('masks',[]))]
    assert bars and headers and body
    assert max(headers)<min(bars) and max(bars)<min(body)
    assert data['tokenTrueNameLayerVersion']==TOKEN_TRUE_NAME_LAYER_VERSION
    assert data['text']['title']['text']=='Test Token'
    assert data['text']['nickname']['text']=='Alternate Name'
    assert data['text']['rules']['text']=='Vigilance'
    assert data['text']['pt']['text']=='2/2'


@pytest.mark.parametrize('style',['token-classic','token-full-art','token-full-art-short','token-borderless'])
def test_copy_token_second_conversion_does_not_stack_title_slices(workspace,style):
    store,art,settings=workspace;ws=Workspace(store);sf=source(False,True)
    comp=ws.compiler.compile_face(sf,sf,0,{},settings,art)
    sem=semantic(sf,sf);sem['nickname']='Alternate Name';spec={'token_frame_style':style}
    once=ws._apply_token_spec(copy.deepcopy(comp),spec,art,'Copy token',sem=sem)
    staged=ws._apply_token_spec(comp,spec,art,'Copy token',sem=sem,finalize=False)
    twice=ws._apply_token_spec(staged,spec,art,'Copy token',sem=sem)
    assert twice['data']['frames']==once['data']['frames']
    assert twice['data']['text']['rules']['text']==once['data']['text']['rules']['text']


@pytest.mark.parametrize('style',['auto','token-classic','token-full-art','token-full-art-short','token-borderless','godzilla-card'])
def test_native_token_cache_refresh_only_applies_to_nicknames(workspace,style):
    store,_,_=workspace;compiler=Compiler(store)
    plain=compiler.template_identity('token',style,{'nickname':''})
    named=compiler.template_identity('token',style,{'nickname':'Alternate Name'})
    assert named[1:]==tuple(v+TOKEN_TRUE_NAME_LAYER_VERSION for v in plain[1:])


@pytest.mark.parametrize('native',[False,True])
@pytest.mark.parametrize('legendary',[False,True])
def test_joined_nickname_tokens_keep_the_native_title_join(workspace,native,legendary):
    store,art,settings=workspace;sf=source(native,legendary);ws=Workspace(store)
    comp=ws.compiler.compile_face(sf,sf,0,
        {'templateOverride':'godzilla-card','semanticOverrides':{'nickname':'Alternate Name'}},settings,art)
    if not native:
        sem=semantic(sf,sf);sem['nickname']='Alternate Name'
        comp=ws._apply_token_spec(comp,{},art,'Copy token',sem=sem)
    data=comp['data']
    assert data['tokenTrueNameLayerVersion']==TOKEN_TRUE_NAME_LAYER_VERSION
    assert any('/godzilla/' in f['src'] and 'Joined' in f['src'] for f in data['frames'])
    assert not any('/nickname/addons/' in f['src'] for f in data['frames'])


def test_copy_token_refresh_key_does_not_invalidate_unnamed_tokens_or_normal_cards(workspace,monkeypatch):
    import foundry.workspace as module
    store,art,settings=workspace;ws=Workspace(store);entry=ws.sources.entry(source(False,False))
    entry['faces'][0]['artOverride']=art
    named=copy.deepcopy(entry);named['faces'][0]['semanticOverrides']={'nickname':'Alternate Name'}
    regular=ws.validate_settings(settings);tokens=ws.validate_settings({**settings,'allCardsTokens':True});index=ArtworkIndex({})
    keys=[ws._preparation_key(c,s,index) for c,s in [(named,regular),(entry,tokens),(named,tokens)]]
    monkeypatch.setattr(module,'TOKEN_TRUE_NAME_LAYER_VERSION',TOKEN_TRUE_NAME_LAYER_VERSION+1)
    assert ws._preparation_key(named,regular,index)==keys[0]
    assert ws._preparation_key(entry,tokens,index)==keys[1]
    assert ws._preparation_key(named,tokens,index)!=keys[2]
