"""Synthetic icon regressions. The four supplied example icons are not shipped."""
import io,zipfile
import pytest
from PIL import Image,ImageChops,ImageDraw
from foundry.backs import Backs,compose_icon,BLANK_SIZE,ICON_BOUNDS
from foundry.domain import ValidationError,uid,GENERATION_VERSION
from foundry.images import ingest_image
from foundry.storage import Store
from foundry.workspace import Workspace
from foundry.orders import Orders
from foundry.backup import Backups

def png(size=(120,80),color=(20,140,230,255)):
    out=io.BytesIO();Image.new('RGBA',size,color).save(out,'PNG');return out.getvalue()

@pytest.mark.parametrize('size',[(1000,1000),(1600,300),(300,1600),(1,1000),(1000,1),(120,80)])
def test_contain_exact_outside_pixels(size):
    blank=Image.new('RGBA',BLANK_SIZE,(55,31,10,255));icon=Image.new('RGBA',size,(30,190,220,220))
    output,info=compose_icon(blank,icon);x,y,w,h=info['placedBounds'];b=ICON_BOUNDS
    assert b['x']<=x and b['y']<=y and x+w<=847 and y+h<=1090
    scale=min(640/size[0],640/size[1]);assert (w,h)==tuple(max(1,min(640,round(n*scale))) for n in size)
    assert ImageChops.difference(blank.convert('RGB'),output.convert('RGB')).getbbox()==(x,y,x+w,y+h)
    for rect in [(0,0,1055,450),(0,1090,1055,1491),(0,450,207,1090),(847,450,1055,1090)]:
        assert output.crop(rect).tobytes()==blank.crop(rect).tobytes()

def test_only_transparent_padding_trimmed():
    blank=Image.new('RGBA',BLANK_SIZE,'orange');icon=Image.new('RGBA',(1000,1000))
    ImageDraw.Draw(icon).rectangle((200,350,799,649),fill=(40,240,10,128))
    _,info=compose_icon(blank,icon)
    assert info['sourceVisibleBounds']==[200,350,800,650] and info['placedBounds']==[207,610,640,320]

def test_transparency_preserved():
    blank=Image.new('RGBA',BLANK_SIZE,(200,80,30,255));icon=Image.new('RGBA',(640,640))
    ImageDraw.Draw(icon).rectangle((0,0,639,639),outline=(0,255,0,255),width=5)
    output,_=compose_icon(blank,icon)
    assert output.getpixel((527,770))==blank.getpixel((527,770))
    assert output.getpixel((207,450))==(0,255,0,255)

def test_invalid_and_opaque_warning():
    b=Image.new('RGBA',BLANK_SIZE)
    with pytest.raises(ValidationError,match='fully transparent'):compose_icon(b,Image.new('RGBA',(30,30)))
    with pytest.raises(ValidationError,match='1055'):compose_icon(Image.new('RGBA',(100,100)),Image.new('RGBA',(1,1),'red'))
    _,info=compose_icon(b,Image.new('RGB',(100,100),'black'));assert len(info['warnings'])==2

def test_default_and_composite_cache(tmp_path):
    store=Store(tmp_path);backs=Backs(store);default=backs.builtin('default')
    assert store.asset_path(default['id']).read_bytes()==(backs.root/'forge_default.png').read_bytes()
    assert (default['width'],default['height'])==(1061,1482)
    icon=ingest_image(store,png());a=backs.icon(icon['id']);b=backs.icon(icon['id'])
    assert a['id']==b['id'] and not a['cached'] and b['cached']
    assert a['width']==1055 and a['height']==1491 and a['design']['iconAsset']==icon['id']
    assert backs.settings({})['backAsset']==default['id']
    assert backs.settings({'backAsset':icon['id']})=={'backAsset':icon['id'],'backDesign':{'mode':'custom'}}
    assert backs.settings({'backAsset':None})['backDesign']['mode']=='none'
    assert backs.settings({'backAsset':default['id'],'backDesign':a['design']})['backAsset']==a['id']
    with pytest.raises(ValidationError):backs.settings({'backDesign':{'mode':'arbitrary'}})

def rendered_deck(w,name='Deck',dfc=False):
    d=w.new_deck(name);a=ingest_image(w.store,png());b=ingest_image(w.store,png(color='purple'))
    key=uid();w.store.render_put(key,a)
    faces=[{'id':uid(),'name':'Test','compiled':{'renderKey':key,'generationVersion':GENERATION_VERSION}}]
    if dfc:
        key=uid();w.store.render_put(key,b);faces.append({'id':uid(),'name':'Reverse','compiled':{'renderKey':key,'generationVersion':GENERATION_VERSION}})
    c={'id':uid(),'name':'Test','quantity':2,'scryfall':{},'faces':faces}
    return w.store.put('decks',{**d,'status':'prepared','cards':[c]},d['revision']),a,b

def test_multideck_dfc_and_no_front_regeneration(tmp_path):
    w=Workspace(Store(tmp_path));d,front,_=rendered_deck(w);dfc,_,real=rendered_deck(w,'DFC',True)
    icon=ingest_image(w.store,png((400,200)));result=w.backs.icon(icon['id'])
    d=w.save(d['id'],{'revision':d['revision'],'settings':{'backDesign':result['design']}})
    assert w.deck(d['id'])['status']=='ready' and not w.render_targets([d['id']])['targets']
    order=Orders(w).build([d['id'],dfc['id']],True);path=w.store.home/'orders'/(order['id']+'.zip');saved=path.read_bytes()
    with zipfile.ZipFile(path) as z:
        assert len(z.namelist())==8
        assert z.read('BACK/000001.png')==w.store.asset_path(result['id']).read_bytes()
        assert z.read('BACK/000003.png')==w.store.asset_path(real['id']).read_bytes()
    d=w.save(d['id'],{'revision':d['revision'],'settings':{'backAsset':front['id']}})
    assert d['settings']['backDesign']['mode']=='custom'
    assert path.read_bytes()==saved and not w.render_targets([d['id']])['targets']

def test_per_card_icon_override_and_real_reverse_restore(tmp_path):
    w=Workspace(Store(tmp_path));d,a,b=rendered_deck(w,dfc=True);c=d['cards'][0];icon=w.backs.icon(a['id'])
    d=w.mutate_card(d['id'],c['id'],{'revision':d['revision'],'backDesignOverride':icon['design']})
    assert Orders(w).plan([d['id']])['cards'][0]['backAsset']==icon['id']
    d=w.mutate_card(d['id'],c['id'],{'revision':d['revision'],'backOverride':None,'backDesignOverride':None})
    assert Orders(w).plan([d['id']])['cards'][0]['backAsset']==b['id'] and w.deck(d['id'])['status']=='ready'

def test_design_and_source_icon_survive_defaults_duplicate_backup(tmp_path):
    w=Workspace(Store(tmp_path));icon=ingest_image(w.store,png());design=w.backs.icon(icon['id'])['design']
    w.set_global_settings({'defaults':{'backDesign':design}});d=w.new_deck('Logo');copy=w.duplicate(d['id'])
    assert copy['settings']['backDesign']==d['settings']['backDesign']
    backup=Backups(w);out=backup.export();path=w.store.home/'backups'/out['filename']
    with zipfile.ZipFile(path) as z:assert 'assets/'+icon['id']+'.png' in z.namelist()
    for ident in backup.restore(path)['ids']:
        assert w.deck(ident)['settings']['backDesign']==design and w.store.asset(w.deck(ident)['settings']['backAsset'])
