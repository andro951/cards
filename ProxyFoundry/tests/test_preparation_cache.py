"""Preparation reuses durable assets and invalidates changes without rendering."""
import copy
import io
import json
import time

import pytest
from PIL import Image

from foundry.compiler import Compiler
from foundry.domain import ValidationError
from foundry.images import ingest_image
from foundry.network import Network
from foundry.sources import Sources
from foundry.storage import Store
from foundry.workspace import Workspace


def image_bytes(format='PNG'):
    out=io.BytesIO();Image.new('RGB',(300,420),'#558877').save(out,format);return out.getvalue()


@pytest.mark.parametrize(('format','mime'),[('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_original_image_bytes_and_format_survive_ingestion(tmp_path,format,mime):
    store=Store(tmp_path);raw=image_bytes(format);asset=ingest_image(store,raw)
    assert asset['mime']==mime
    assert store.asset_path(asset['id']).read_bytes()==raw
    assert (asset['width'],asset['height'])==(300,420)


def test_orientation_and_padding_still_transform_pixels(tmp_path):
    store=Store(tmp_path);out=io.BytesIO();im=Image.new('RGB',(30,60),'red')
    exif=Image.Exif();exif[274]=6;im.save(out,'JPEG',exif=exif)
    asset=ingest_image(store,out.getvalue());assert asset['mime']=='image/png'
    assert (asset['width'],asset['height'])==(60,30)
    out=io.BytesIO();im=Image.new('RGBA',(40,40));im.paste('red',(10,10,30,30));im.save(out,'PNG')
    asset=ingest_image(store,out.getvalue(),trim_transparent_padding=True)
    assert (asset['width'],asset['height'])==(20,20)


class Remote:
    def __init__(self):
        self.commit='a'*40;self.calls=[];self.files=[];self.status='ahead'
        self.rows=[{'type':'file','name':name+'.jpg','path':'art/'+name+'.jpg'} for name in ('one_card','two_card')]
    def transport(self,url):
        self.calls.append(url)
        if '/commits/' in url:body={'sha':self.commit}
        elif '/compare/' in url:body={'status':self.status,'files':self.files}
        elif '/contents/' in url:body=self.rows
        else:return image_bytes('JPEG'),'image/jpeg',{}
        return json.dumps(body).encode(),'application/json',{}


def github_index(tmp_path,remote):
    return Sources(Network(Store(tmp_path),transport=remote.transport)).github_index('https://github.com/owner/repo/tree/main/art',refresh=True)


def test_same_commit_reuses_folder_listing_after_restart(tmp_path):
    remote=Remote();first=github_index(tmp_path,remote);remote.calls.clear()
    assert github_index(tmp_path,remote)==first
    assert len(remote.calls)==1 and '/commits/' in remote.calls[0]


def test_comparison_only_invalidates_changed_files(tmp_path):
    remote=Remote();first=github_index(tmp_path,remote)
    remote.commit='b'*40;remote.files=[{'filename':'art/one_card.jpg','status':'modified'}]
    second=github_index(tmp_path,remote)
    assert first['two_card']==second['two_card']
    assert first['one_card']['url']!=second['one_card']['url']


@pytest.mark.parametrize('scenario',['diverged','capped','unavailable'])
def test_unreliable_comparison_refreshes_all_urls(tmp_path,scenario):
    remote=Remote();first=github_index(tmp_path,remote);remote.commit='b'*40
    if scenario=='diverged':remote.status='diverged'
    elif scenario=='capped':remote.files=[{'filename':str(i),'status':'modified'} for i in range(300)]
    else:
        original=remote.transport
        def transport(url):
            if '/compare/' in url:raise ValidationError('Comparison unavailable')
            return original(url)
        remote.transport=transport
    second=github_index(tmp_path,remote)
    assert all(first[key]['url']!=second[key]['url'] for key in first)


def test_comparison_handles_add_remove_and_rename(tmp_path):
    remote=Remote();first=github_index(tmp_path,remote);remote.commit='b'*40
    remote.rows=[{'type':'file','name':'renamed.jpg','path':'art/renamed.jpg'},
                 {'type':'file','name':'new.jpg','path':'art/new.jpg'}]
    remote.files=[{'filename':'art/renamed.jpg','previous_filename':'art/one_card.jpg','status':'renamed'},
                  {'filename':'art/two_card.jpg','status':'removed'},
                  {'filename':'art/new.jpg','status':'added'}]
    second=github_index(tmp_path,remote)
    assert set(second)=={'renamed','new'}
    assert all('b'*40 in item['url'] for item in second.values())


def seeded(tmp_path,format='JPEG'):
    store=Store(tmp_path);raw=image_bytes(format)
    sf={'id':'00000000-0000-4000-8000-000000000001','name':'One Card','layout':'normal',
        'type_line':'Creature — Human','mana_cost':'{G}','oracle_text':'Vigilance',
        'colors':['G'],'rarity':'common','power':'2','toughness':'2','artist':'Tester',
        'image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/card.jpg'}}
    calls=[]
    def transport(url):
        calls.append(url)
        if 'api.scryfall' in url:return json.dumps(sf).encode(),'application/json',{}
        return raw,'image/jpeg',{}
    ws=Workspace(store,Network(store,transport=transport,sleeper=lambda _:None))
    deck=ws.new_deck('Preparation cache')
    card=ws.sources.entry(sf)
    deck=store.put('decks',{**deck,'cards':[card]},deck['revision'])
    return ws,deck,calls,transport


@pytest.mark.parametrize('format',['JPEG','WEBP'])
def test_cached_preparation_skips_network_decode_and_compile_after_restart(tmp_path,monkeypatch,format):
    ws,deck,calls,transport=seeded(tmp_path,format);prepared=ws.prepare(deck['id'])
    assert not prepared['cards'][0]['faces'][0].get('error')
    original=prepared['cards'][0]['faces'][0]['compiled']['data'];calls.clear()
    ws=Workspace(Store(tmp_path),Network(Store(tmp_path),transport=transport))
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Unchanged face recompiled'))
    monkeypatch.setattr(ws.sources,'resolve_card',lambda *a,**k:pytest.fail('Unchanged metadata resolved'))
    result=ws.prepare(deck['id'])
    assert result['cards'][0]['faces'][0]['compiled']['data']==original and not calls


def test_processed_artwork_is_durable_even_when_face_changes(tmp_path,monkeypatch):
    ws,deck,calls,transport=seeded(tmp_path);ws.prepare(deck['id']);calls.clear()
    ws=Workspace(Store(tmp_path),Network(Store(tmp_path),transport=transport))
    ws.default_symbols()
    monkeypatch.setattr('foundry.workspace.ingest_image',lambda *a,**k:pytest.fail('Artwork reprocessed'))
    deck=ws.deck(deck['id']);deck['cards'][0]['faces'][0]['semanticOverrides']={'nickname':'New Name'}
    ws.store.put('decks',deck,deck['revision']);result=ws.prepare(deck['id'])
    assert not result['cards'][0]['faces'][0].get('error') and not calls


@pytest.mark.parametrize('change',['artist','nickname','template','expired','missing-art'])
def test_changed_inputs_invalidate_preparation(tmp_path,monkeypatch,change):
    ws,deck,calls,transport=seeded(tmp_path);ws.prepare(deck['id']);deck=ws.deck(deck['id'])
    face=deck['cards'][0]['faces'][0]
    if change=='artist':deck['settings']['artist']='New Artist'
    elif change=='nickname':face['semanticOverrides']={'nickname':'New Name'}
    elif change=='template':deck['settings']['templateRules']={'standard':'normal'}
    elif change=='expired':face['preparedAt']=0
    else:ws.store.asset_path(face['compiled']['artId']).unlink()
    ws.store.put('decks',deck,deck['revision']);compiled=[];original=ws.compiler.compile_face
    def compile(*a,**k):compiled.append(True);return original(*a,**k)
    monkeypatch.setattr(ws.compiler,'compile_face',compile)
    ws.prepare(deck['id']);assert compiled


def test_new_metadata_artist_does_not_force_a_second_preparation(tmp_path,monkeypatch):
    ws,deck,_,_=seeded(tmp_path);deck=ws.deck(deck['id'])
    deck['cards'][0]['scryfall'].pop('artist')
    ws.store.put('decks',deck,deck['revision']);ws.prepare(deck['id'])
    monkeypatch.setattr(ws.compiler,'compile_face',lambda *a,**k:pytest.fail('Display artist invalidated cache'))
    ws.prepare(deck['id'])


def test_github_changes_recompile_only_affected_cards(tmp_path,monkeypatch):
    ws,deck,_,metadata_transport=seeded(tmp_path)
    remote=Remote();original=remote.transport
    sf=deck['cards'][0]['scryfall'];second=copy.deepcopy(sf)
    second.update(name='Two Card',id='00000000-0000-4000-8000-000000000002')
    def transport(url):
        if 'api.scryfall' in url:
            return json.dumps(second if url.endswith(second['id']) else sf).encode(),'application/json',{}
        return original(url)
    ws.net=Network(ws.store,transport=transport);ws.sources=Sources(ws.net)
    deck=ws.deck(deck['id']);deck['cards'].append(ws.sources.entry(second))
    deck['settings']['source']={'mode':'github','githubFolder':'https://github.com/owner/repo/tree/main/art','fallback':False}
    ws.store.put('decks',deck,deck['revision']);ws.prepare(deck['id'])
    remote.commit='b'*40;remote.files=[{'filename':'art/one_card.jpg','status':'modified'}]
    compiled=[];compile=ws.compiler.compile_face
    def tracked(sf,*args,**kwargs):compiled.append(sf['name']);return compile(sf,*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    ws.prepare(deck['id']);assert compiled==['One Card']


def test_cancel_flushes_completed_cards_without_per_card_saves(tmp_path,monkeypatch):
    ws,deck,_,_=seeded(tmp_path);deck=ws.deck(deck['id'])
    deck['cards']=[{**copy.deepcopy(deck['cards'][0]),'id':str(i)} for i in range(4)]
    ws.store.put('decks',deck,deck['revision']);saves=[];original=ws.store.put
    def put(kind,*a,**k):
        if kind=='decks':saves.append(True)
        return original(kind,*a,**k)
    monkeypatch.setattr(ws.store,'put',put)
    cancel=[False];steps=ws.prepare_steps(deck['id'],cancel=lambda:cancel[0])
    next(steps);next(steps);next(steps);assert not saves
    cancel[0]=True
    with pytest.raises(ValidationError,match='cancelled'):next(steps)
    saved=ws.deck(deck['id'])
    assert len(saves)==1
    assert all(c['faces'][0].get('compiled') for c in saved['cards'][:2])
    assert not saved['cards'][2]['faces'][0].get('compiled')


def test_unchanged_deck_plans_once_without_processing_or_saving(tmp_path,monkeypatch):
    ws,deck,_,_=seeded(tmp_path);ws.prepare(deck['id'])
    deck=ws.deck(deck['id']);deck['cards']=[{**copy.deepcopy(deck['cards'][0]),'id':str(i)} for i in range(25)]
    ws.store.put('decks',deck,deck['revision']);revision=ws.store.get('decks',deck['id'])['revision']
    monkeypatch.setattr(ws,'_prepare_card_faces',lambda *a,**k:pytest.fail('Unchanged card processed'))
    original=ws.store.put
    def put(kind,*a,**k):
        if kind=='decks':pytest.fail('Unchanged deck saved')
        return original(kind,*a,**k)
    monkeypatch.setattr(ws.store,'put',put);events=[]
    result=ws.prepare(deck['id'],progress=lambda *a:events.append(a))
    assert result['revision']==revision and result['summary']['faces']==25
    assert len(events)==1 and '25 faces unchanged' in events[0][2]


def test_plan_processes_only_the_card_with_changed_options(tmp_path,monkeypatch):
    ws,deck,_,_=seeded(tmp_path);ws.prepare(deck['id']);deck=ws.deck(deck['id'])
    deck['cards']=[{**copy.deepcopy(deck['cards'][0]),'id':str(i)} for i in range(3)]
    deck['cards'][1]['faces'][0]['semanticOverrides']={'nickname':'Changed'}
    ws.store.put('decks',deck,deck['revision']);processed=[];prepare=ws._prepare_card_faces
    def tracked(d,c,*a,**k):processed.append(c['id']);return prepare(d,c,*a,**k)
    monkeypatch.setattr(ws,'_prepare_card_faces',tracked)
    result=ws.prepare(deck['id'])
    assert processed==['1']
    assert result['cards'][1]['faces'][0]['semanticOverrides']['nickname']=='Changed'
