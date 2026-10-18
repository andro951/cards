"""Generation observes linked data.json changes before reusing prepared faces."""
import io
import json

import pytest
from PIL import Image

from foundry import github_data
from foundry.domain import ValidationError
from foundry.images import ingest_image
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace


class Remote:
    def __init__(self):
        self.commit='a'*40;self.calls=[];self.document={'version':1,'cards':[]};self.failure=None
    def transport(self,url):
        self.calls.append(url)
        if '/commits/' in url:value={'sha':self.commit}
        elif url=='https://api.github.com/repos/owner/repo':value={'default_branch':'main'}
        elif url.startswith('https://raw.githubusercontent.com/'):
            if self.failure:raise ValidationError(self.failure)
            value=self.document
        else:pytest.fail('Unexpected network request: '+url)
        return json.dumps(value).encode(),'application/json',{}


@pytest.fixture
def env(tmp_path):
    remote=Remote();store=Store(tmp_path);ws=Workspace(store,Network(store,transport=remote.transport))
    out=io.BytesIO();Image.new('RGB',(300,420),'gray').save(out,'PNG');art=ingest_image(store,out.getvalue())['id']
    settings=ws.validate_settings({'artist':'Test Artist','templateRules':{'token':'godzilla-card'},
        'dataJsonSource':{'kind':'github','value':'deck/data.json'},
        'githubSetupFolder':'https://github.com/owner/repo/tree/main/deck'})
    cards=[]
    for name,color,pt in [('Angel','W','4'),('Germ','B','0'),('Soldier','W','1')]:
        sf={'name':name,'layout':'token','type_line':'Token Creature — '+name,'colors':[color],
            'mana_cost':'','oracle_text':'Flying' if name=='Angel' else '',
            'power':pt,'toughness':pt,'rarity':'common'}
        card=ws.sources.entry(sf);card['faces'][0]['artOverride']=art;cards.append(card)
    deck=ws.new_deck('GitHub refresh');deck=store.put('decks',{**deck,'cards':cards,'settings':settings},deck['revision'])
    return ws,deck,remote


def set_names(remote):
    remote.commit='b'*40
    remote.document={'version':1,'cards':[{'name':'Angel','nickname':'Fallen Seraph'},
        {'name':'Germ','nickname':'Shadow of Death'}]}


def test_generate_refreshes_angel_germ_and_only_recompiles_changed_cards(env,monkeypatch):
    ws,deck,remote=env;first=ws.prepare(deck['id']);control=first['cards'][2]['faces'][0]['compiled']['renderKey']
    set_names(remote);calls=[];compile_face=ws.compiler.compile_face
    def tracked(sf,*a,**k):calls.append(sf['name']);return compile_face(sf,*a,**k)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    result=ws.prepare(deck['id'])
    assert calls==['Angel','Germ']
    for card,nick in zip(result['cards'],['Fallen Seraph','Shadow of Death']):
        text=card['faces'][0]['compiled']['data']['text']
        assert text['nickname']['text']==nick and text['title']['text']==card['name']
    assert result['cards'][2]['faces'][0]['compiled']['renderKey']==control


def test_same_commit_after_restart_only_checks_commit_and_keeps_revision(env,monkeypatch):
    ws,deck,remote=env;set_names(remote);first=ws.prepare(deck['id']);remote.calls.clear()
    ws=Workspace(Store(ws.store.home),Network(Store(ws.store.home),transport=remote.transport))
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Unchanged card compiled'))
    result=ws.prepare(deck['id'])
    assert result['revision']==first['revision']
    assert remote.calls==['https://api.github.com/repos/owner/repo/commits/main']


def test_unrelated_commit_keeps_cards_cached(env,monkeypatch):
    ws,deck,remote=env;set_names(remote);ws.prepare(deck['id']);remote.commit='c'*40
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Unchanged data recompiled'))
    result=ws.prepare(deck['id'])
    assert result['githubCardDataState']['commit']=='c'*40


@pytest.mark.parametrize('replacement',[None,''])
def test_removed_or_empty_nickname_clears_previously_imported_value(env,replacement):
    ws,deck,remote=env;set_names(remote);ws.prepare(deck['id']);remote.commit='c'*40
    entry=remote.document['cards'][0]
    if replacement is None:entry.pop('nickname')
    else:entry['nickname']=replacement
    result=ws.prepare(deck['id'])
    assert 'nickname' not in result['cards'][0]['faces'][0]['compiled']['data']['text']
    assert result['cards'][1]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Shadow of Death'


def test_manual_override_survives_unchanged_remote_field_and_remote_removal(env):
    ws,deck,remote=env;set_names(remote);ws.prepare(deck['id'])
    saved=ws.store.get('decks',deck['id']);face=saved['cards'][0]['faces'][0]
    face['semanticOverrides']['nickname']='My Seraph';ws.invalidate_face(face)
    ws.store.put('decks',saved,saved['revision'])
    remote.commit='c'*40;result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='My Seraph'
    remote.document['cards'][0].pop('nickname');remote.commit='d'*40
    result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='My Seraph'


@pytest.mark.parametrize('bad',[{'version':2,'cards':[]},{'version':1,'cards':[{'name':'Angel','nickname':[]}]}])
def test_invalid_remote_document_does_not_advance_commit_or_mutate_deck(env,bad):
    ws,deck,remote=env;set_names(remote);ws.prepare(deck['id']);before=ws.store.get('decks',deck['id'])
    remote.commit='c'*40;remote.document=bad
    with pytest.raises(ValidationError):ws.prepare(deck['id'])
    assert ws.store.get('decks',deck['id'])==before


def test_missing_remote_file_does_not_use_stale_data_silently(env):
    ws,deck,remote=env;ws.prepare(deck['id']);before=ws.store.get('decks',deck['id'])
    remote.commit='c'*40;remote.failure='HTTP 404 data.json'
    with pytest.raises(ValidationError,match='404'):ws.prepare(deck['id'])
    assert ws.store.get('decks',deck['id'])==before


@pytest.mark.parametrize('url',['https://github.com/owner/repo/blob/main/deck/data.json',
    'https://raw.githubusercontent.com/owner/repo/main/deck/data.json'])
def test_direct_file_links_refresh(env,url):
    ws,deck,remote=env;set_names(remote);deck['settings']['dataJsonSource']['value']=url
    ws.store.put('decks',deck,deck['revision']);result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Fallen Seraph'
    assert 'https://raw.githubusercontent.com/owner/repo/'+'b'*40+'/deck/data.json' in remote.calls


@pytest.mark.parametrize('url',[
    'https://github.com/owner/repo/tree/main/deck',
    'https://github.com/owner/repo/tree/main/deck/',
])
def test_folder_link_retained_by_card_save_refreshes_its_data_file(env,url):
    ws,deck,remote=env;set_names(remote)
    deck['settings']['dataJsonSource']['value']=url
    ws.store.put('decks',deck,deck['revision'])
    result=ws.prepare_card(deck['id'],deck['cards'][0]['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Fallen Seraph'
    assert 'https://raw.githubusercontent.com/owner/repo/'+'b'*40+'/deck/data.json' in remote.calls


def test_repository_root_folder_link_uses_root_data_file():
    loc=github_data.location({'dataJsonSource':{'kind':'github','value':'https://github.com/owner/repo/tree/main'}})
    assert loc['folder']=='data.json'


def test_other_file_is_not_reinterpreted_as_a_data_folder(env):
    ws,deck,remote=env
    deck['settings']['dataJsonSource']['value']='https://github.com/owner/repo/blob/main/deck/other.json'
    with pytest.raises(ValidationError,match='file named data.json'):
        github_data.location(deck['settings'])
    assert remote.calls==[]


def test_single_card_generation_checks_and_refreshes_first(env):
    ws,deck,remote=env;ws.prepare(deck['id']);set_names(remote)
    result=ws.prepare_card(deck['id'],deck['cards'][0]['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Fallen Seraph'
    assert result['cards'][1]['faces'][0].get('compiled') is None


def test_local_source_is_not_polled(env):
    ws,deck,remote=env;deck['settings']['dataJsonSource']={'kind':'local','value':'data.json'}
    ws.store.put('decks',deck,deck['revision']);ws.prepare(deck['id'])
    assert remote.calls==[]


def test_preparation_handles_previously_saved_full_local_inventory(env):
    ws,deck,remote=env;deck['settings']['dataJsonSource']={'kind':'local','value':'data.json'}
    deck['cardData']=[{'name':'Angel','nickname':'Fallen Seraph'},{'name':'Marsh Flats','nickname':'Unused land'}]
    ws.store.put('decks',deck,deck['revision'])
    result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Fallen Seraph'
    assert remote.calls==[] and len(result['cards'])==3


def test_pinned_commit_needs_no_branch_request(env):
    ws,deck,remote=env;deck['settings']['dataJsonSource']['value']='https://github.com/owner/repo/blob/'+'a'*40+'/deck/data.json'
    ws.store.put('decks',deck,deck['revision']);ws.prepare(deck['id']);remote.calls.clear()
    ws.prepare(deck['id']);assert remote.calls==[]


def test_cancelled_refresh_does_not_mutate_deck(env):
    ws,deck,remote=env;set_names(remote);before=ws.store.get('decks',deck['id']);checks=iter([False,True])
    with pytest.raises(ValidationError,match='cancelled'):
        github_data.refresh(ws,deck,lambda:next(checks))
    assert ws.store.get('decks',deck['id'])==before


def test_removed_specific_selector_falls_back_to_general_nickname(env):
    ws,deck,remote=env
    card=deck['cards'][0];card['scryfall']['oracle_id']='11111111-1111-4111-8111-111111111111'
    ws.store.put('decks',deck,deck['revision'])
    remote.document['cards']=[{'name':'Angel','nickname':'General Seraph'},
        {'oracle_id':card['scryfall']['oracle_id'],'name':'Angel','nickname':'Specific Seraph'}]
    first=ws.prepare(deck['id'])
    assert first['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Specific Seraph'
    remote.commit='c'*40;remote.document['cards'].pop()
    result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']['text']['nickname']['text']=='General Seraph'


def test_top_level_artist_changes_and_removal_are_applied(env):
    ws,deck,remote=env;remote.document['artist']='New Deck Artist'
    result=ws.prepare(deck['id']);assert result['settings']['artist']=='New Deck Artist'
    remote.commit='c'*40;remote.document.pop('artist')
    result=ws.prepare(deck['id']);assert result['settings']['artist']==''


def test_entire_removed_entry_clears_imported_nickname(env):
    ws,deck,remote=env;set_names(remote);ws.prepare(deck['id'])
    remote.commit='c'*40;remote.document['cards'].pop(0)
    result=ws.prepare(deck['id'])
    assert 'nickname' not in result['cards'][0]['faces'][0]['compiled']['data']['text']


def test_unused_source_entries_apply_when_card_is_added_without_new_commit(env):
    ws,deck,remote=env;set_names(remote)
    remote.document['cards'].append({'name':'Treasure','nickname':'Hidden Treasure'})
    first=ws.prepare(deck['id'])
    assert not any(e.get('name')=='Treasure' for e in first['cardData'])
    saved=ws.store.get('decks',deck['id'])
    sf={'name':'Treasure','layout':'token','type_line':'Token Artifact — Treasure','colors':[],
        'mana_cost':'','oracle_text':'{T}, Sacrifice this token: Add one mana of any color.','rarity':'common'}
    card=ws.sources.entry(sf);card['faces'][0]['artOverride']=saved['cards'][0]['faces'][0]['artOverride']
    saved['cards'].append(card);ws.store.put('decks',saved,saved['revision']);remote.calls.clear()
    result=ws.prepare(deck['id'])
    assert result['cards'][-1]['faces'][0]['compiled']['data']['text']['nickname']['text']=='Hidden Treasure'
    assert remote.calls==['https://api.github.com/repos/owner/repo/commits/main']
