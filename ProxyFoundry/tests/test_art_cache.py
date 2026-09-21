"""GitHub art is pinned to exact Git content; Scryfall keeps its separate cache policy."""
import hashlib
import io

import pytest
from PIL import Image

from foundry.domain import ValidationError
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.sources import Sources


def png(color='#7566aa'):
    out=io.BytesIO();Image.new('RGB',(600,840),color).save(out,'PNG');return out.getvalue()


def blob_sha(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()


def make_workspace(tmp_path):
    raw=png();calls=[]
    class Network:
        def fetch(self,url,**kwargs):calls.append((url,kwargs));return raw,'image/png',{}
    ws=Workspace(Store(tmp_path),Network())
    sf={'name':'One Card','type_line':'Land','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/test.jpg'}}
    return ws,sf,calls,raw


def test_github_art_uses_pinned_immutable_url_and_verifies_blob(tmp_path):
    ws,sf,calls,raw=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art'}})
    commit='a'*40
    entry={'url':'https://raw.githubusercontent.com/owner/repo/'+commit+'/art/one_card.png','blobSha':blob_sha(raw)}
    art_id,origin,url=ws._art(sf,sf,{},settings,{'one_card':entry},{})
    assert origin=='GitHub folder' and url==entry['url']
    assert ws.store.asset(art_id)
    assert calls[-1]==(entry['url'],{'immutable':True})


def test_hosted_land_art_uses_same_pinned_verification(tmp_path):
    ws,sf,calls,raw=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'scryfall'},'useLandLibrary':True})
    commit='b'*40
    entry={'url':'https://raw.githubusercontent.com/andro951/cards/'+commit+'/ProxyFoundry/full_art_lands/one_card.png','blobSha':blob_sha(raw)}
    ws._art(sf,sf,{},settings,{}, {'one_card':entry})
    assert calls[-1]==(entry['url'],{'immutable':True})


def test_github_folder_index_resolves_current_commit_and_keeps_blob_sha():
    commit='c'*40;blob='d'*40
    class Network:
        def __init__(self):self.calls=[]
        def json(self,url,**kwargs):
            self.calls.append((url,kwargs))
            if url=='https://api.github.com/repos/owner/repo':return {'default_branch':'main'}
            if url=='https://api.github.com/repos/owner/repo/commits/main':return {'sha':commit}
            if url=='https://api.github.com/repos/owner/repo/contents/art?ref='+commit:
                return [{'type':'file','name':'one_card.png','path':'art/one_card.png','sha':blob}]
            raise AssertionError(url)
    net=Network();index=Sources(net).github_index('owner/repo/art',refresh=True)
    assert index['one_card']=={
        'url':'https://raw.githubusercontent.com/owner/repo/'+commit+'/art/one_card.png',
        'blobSha':blob,
    }
    assert [url for url,_ in net.calls]==[
        'https://api.github.com/repos/owner/repo',
        'https://api.github.com/repos/owner/repo/commits/main',
        'https://api.github.com/repos/owner/repo/contents/art?ref='+commit,
    ]
    assert all(kwargs=={'ttl':0} for _,kwargs in net.calls)


def test_changed_branch_head_cannot_reuse_stale_mutable_raw_bytes(tmp_path):
    raws=[png('#334455'),png('#aa5522')]
    commits=['1'*40,'2'*40]
    blobs=[blob_sha(raw) for raw in raws]
    state=[0]
    class Network:
        def __init__(self):self.fetch_calls=[]
        def json(self,url,**kwargs):
            if url=='https://api.github.com/repos/owner/repo':return {'default_branch':'main'}
            if url=='https://api.github.com/repos/owner/repo/commits/main':return {'sha':commits[state[0]]}
            expected='https://api.github.com/repos/owner/repo/contents/art?ref='+commits[state[0]]
            if url==expected:
                return [{'type':'file','name':'one_card.png','path':'art/one_card.png','sha':blobs[state[0]]}]
            raise AssertionError(url)
        def fetch(self,url,**kwargs):
            self.fetch_calls.append((url,kwargs))
            # This is the failure mode being guarded against: a mutable main URL
            # can still hand back the old bytes after the branch was updated.
            if '/main/art/one_card.png' in url:return raws[0],'image/png',{}
            for i,commit in enumerate(commits):
                if '/'+commit+'/art/one_card.png' in url:return raws[i],'image/png',{}
            raise AssertionError(url)
    net=Network();ws=Workspace(Store(tmp_path),net)
    sf={'name':'One Card','type_line':'Land','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/test.jpg'}}
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art'}})

    first_index=ws.sources.github_index('owner/repo/art',refresh=True)
    first_id,_,first_url=ws._art(sf,sf,{},settings,first_index,{})
    state[0]=1
    second_index=ws.sources.github_index('owner/repo/art',refresh=True)
    second_id,_,second_url=ws._art(sf,sf,{},settings,second_index,{})

    assert first_id!=second_id
    assert commits[0] in first_url and commits[1] in second_url
    assert all('/main/art/one_card.png' not in url for url,_ in net.fetch_calls)


def test_github_blob_sha_mismatch_is_rejected(tmp_path):
    ws,sf,_,raw=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art'}})
    commit='e'*40
    entry={'url':'https://raw.githubusercontent.com/owner/repo/'+commit+'/art/one_card.png','blobSha':'0'*40}
    assert blob_sha(raw)!='0'*40
    with pytest.raises(ValidationError,match='did not match the folder listing'):
        ws._art(sf,sf,{},settings,{'one_card':entry},{})


def test_old_refresh_art_setting_is_discarded(tmp_path):
    ws,_,_,_=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art','refreshArt':True}})
    assert 'refreshArt' not in settings['source']


def test_scryfall_cache_policy_is_unchanged(tmp_path):
    ws,sf,calls,_=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'scryfall'}})
    ws._art(sf,sf,{},settings,{},{});assert calls[-1][1]=={'refresh':False,'ttl':None}
    settings['refreshData']=True
    ws._art(sf,sf,{},settings,{},{});assert calls[-1][1]=={'refresh':True,'ttl':None}


def test_global_scryfall_refresh_applies_to_art(tmp_path):
    ws,sf,calls,_=make_workspace(tmp_path)
    ws.set_global_settings({'refreshData':True})
    settings=ws.validate_settings({})
    ws._art(sf,sf,{},settings,{},{})
    assert calls[-1][1]=={'refresh':True,'ttl':None}
