"""GitHub art is live; Scryfall keeps its separate year/week cache policy."""
import io
from PIL import Image
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.sources import Sources

def make_workspace(tmp_path):
    out=io.BytesIO();Image.new('RGB',(600,840),'#7566aa').save(out,'PNG')
    calls=[]
    class Network:
        def fetch(self,url,**kwargs):calls.append((url,kwargs));return out.getvalue(),'image/png',{}
    ws=Workspace(Store(tmp_path),Network())
    sf={'name':'One Card','type_line':'Land','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/test.jpg'}}
    return ws,sf,calls

def test_github_art_is_refetched_every_generation(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art'}})
    index={'one_card':'https://raw.githubusercontent.com/owner/repo/main/art/one_card.png'}
    ws._art(sf,sf,{},settings,index,{})
    assert calls[-1][1]=={'refresh':True,'ttl':0}

def test_hosted_land_art_is_refetched_every_generation(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'scryfall'},'useLandLibrary':True})
    land_index={'one_card':'https://raw.githubusercontent.com/andro951/cards/main/ProxyFoundry/full_art_lands/one_card.png'}
    ws._art(sf,sf,{},settings,{},land_index)
    assert calls[-1][1]=={'refresh':True,'ttl':0}

def test_old_refresh_art_setting_is_discarded(tmp_path):
    ws,_,_=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art','refreshArt':True}})
    assert 'refreshArt' not in settings['source']

def test_github_folder_index_bypasses_cache_when_refreshing():
    class Network:
        def __init__(self):self.calls=[]
        def json(self,url,**kwargs):
            self.calls.append((url,kwargs))
            if url=='https://api.github.com/repos/owner/repo':return {'default_branch':'main'}
            return [{'type':'file','name':'one_card.png','path':'art/one_card.png'}]
    net=Network();index=Sources(net).github_index('owner/repo/art',refresh=True)
    assert index['one_card'].endswith('/owner/repo/main/art/one_card.png')
    assert len(net.calls)==2 and all(kwargs.get('ttl')==0 for _,kwargs in net.calls)

def test_scryfall_cache_policy_is_unchanged(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'scryfall'}})
    ws._art(sf,sf,{},settings,{},{});assert calls[-1][1]=={'refresh':False,'ttl':None}
    settings['refreshData']=True
    ws._art(sf,sf,{},settings,{},{});assert calls[-1][1]=={'refresh':True,'ttl':None}

def test_global_scryfall_refresh_applies_to_art(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    ws.set_global_settings({'refreshData':True})
    settings=ws.validate_settings({})
    ws._art(sf,sf,{},settings,{},{})
    assert calls[-1][1]=={'refresh':True,'ttl':None}
