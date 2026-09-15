import io,zipfile,pytest
from PIL import Image
from foundry.storage import Store
from foundry.domain import uid,ValidationError,GENERATION_VERSION
from foundry.network import Network
from foundry.workspace import Workspace,DEFAULT_SETTINGS
from foundry.orders import Orders
from foundry.images import ingest_image

def make_asset(s,color):
    b=io.BytesIO();Image.new('RGB',(30,42),color).save(b,'PNG');return ingest_image(s,b.getvalue())
def test_multideck_pairs_and_quantities(tmp_path):
    s=Store(tmp_path);ws=Workspace(s,Network(s));front=make_asset(s,'red');dfc=make_asset(s,'green');back1=make_asset(s,'blue');back2=make_asset(s,'yellow')
    s.render_put('front',front);s.render_put('dfc',dfc)
    def deck(name,back,q,second=False):
        f=[{'id':uid(),'name':'Same name','compiled':{'renderKey':'front','generationVersion':GENERATION_VERSION}}]
        if second:f.append({'id':uid(),'name':'DFC','compiled':{'renderKey':'dfc','generationVersion':GENERATION_VERSION}})
        return s.put('decks',{'name':name,'settings':dict(DEFAULT_SETTINGS,backAsset=back['id']),'status':'prepared','cards':[{'id':uid(),'name':'Same name','quantity':q,'faces':f}]})
    a=deck('One',back1,2);b=deck('Two',back2,1);c=deck('Three',back1,1,True)
    order=Orders(ws).build([a['id'],b['id'],c['id']])
    assert order['count']==4
    with zipfile.ZipFile(s.home/'orders'/(order['id']+'.zip')) as z:
        assert len(z.namelist())==8
        assert z.read('BACK/000001.png')==s.asset_path(back1['id']).read_bytes()
        assert z.read('BACK/000002.png')==s.asset_path(back1['id']).read_bytes()
        assert z.read('BACK/000003.png')==s.asset_path(back2['id']).read_bytes()
        assert z.read('BACK/000004.png')==s.asset_path(dfc['id']).read_bytes()
def test_draft_never_ordered(tmp_path):
    s=Store(tmp_path);ws=Workspace(s,Network(s));d=ws.new_deck()
    with pytest.raises(ValidationError):Orders(ws).build([d['id']])
