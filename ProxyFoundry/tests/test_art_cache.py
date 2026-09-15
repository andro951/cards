"""Custom-art freshness never changes the requested Scryfall year/week policy."""
import io
from PIL import Image
from foundry.storage import Store
from foundry.workspace import Workspace

def make_workspace(tmp_path):
    out=io.BytesIO();Image.new('RGB',(600,840),'#7566aa').save(out,'PNG')
    calls=[]
    class Network:
        def fetch(self,url,**kwargs):calls.append((url,kwargs));return out.getvalue(),'image/png',{}
    ws=Workspace(Store(tmp_path),Network())
    sf={'name':'One Card','type_line':'Land','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/test.jpg'}}
    return ws,sf,calls

def test_custom_art_short_cache_and_explicit_refresh(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art'}})
    index={'one_card':'https://raw.githubusercontent.com/owner/repo/main/art/one_card.png'}
    ws._art(sf,sf,{},settings,index,{})
    assert calls[-1][1]=={'refresh':False,'ttl':600}
    settings['source']['refreshArt']=True
    ws._art(sf,sf,{},settings,index,{})
    assert calls[-1][1]['ttl']==0

def test_scryfall_cache_not_bypassed_by_custom_art_refresh(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    settings=ws.validate_settings({'source':{'mode':'scryfall','refreshArt':True}})
    ws._art(sf,sf,{},settings,{},{});assert calls[-1][1]=={'refresh':False,'ttl':None}
    settings['refreshData']=True
    ws._art(sf,sf,{},settings,{},{});assert calls[-1][1]=={'refresh':True,'ttl':None}

def test_global_scryfall_refresh_applies_to_art(tmp_path):
    ws,sf,calls=make_workspace(tmp_path)
    ws.set_global_settings({'refreshData':True})
    settings=ws.validate_settings({})
    ws._art(sf,sf,{},settings,{},{})
    assert calls[-1][1]=={'refresh':True,'ttl':None}
