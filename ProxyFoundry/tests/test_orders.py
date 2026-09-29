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
    template_key,template_version,_=ws.compiler.template_identity('standard','auto')
    def deck(name,back,q,second=False):
        f=[{'id':uid(),'name':'Same name','compiled':{'renderKey':'front','generationVersion':GENERATION_VERSION,'templateKey':template_key,'templateVersion':template_version}}]
        if second:f.append({'id':uid(),'name':'DFC','compiled':{'renderKey':'dfc','generationVersion':GENERATION_VERSION,'templateKey':template_key,'templateVersion':template_version}})
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
    from foundry.server import App
    from foundry.browser import request as browser_request
    app=App(s,Network(s))
    try:
        transfer=app.transfer(order['id'])
        headers={'x-proxy-transfer-token':transfer['secret'],'range':'bytes=0-1023'}
        meta=browser_request(app,'GET','/api/transfer/'+transfer['id']+'/metadata',headers=headers)
        assert meta['status']==200 and b'"protocolVersion": 2' in meta['body']
        chunk=browser_request(app,'GET','/api/transfer/'+transfer['id']+'/zip?batch=0',headers=headers)
        assert chunk['status']==206
        assert chunk['headers']['Content-Range'].startswith('bytes 0-')
        download=browser_request(app,'GET','/api/orders/'+order['id']+'/download',
                                 headers={'range':'bytes=0-31'})
        assert download['status']==206 and download['body'].startswith(b'PK')
    finally:app.close()
def test_draft_never_ordered(tmp_path):
    s=Store(tmp_path);ws=Workspace(s,Network(s));d=ws.new_deck()
    with pytest.raises(ValidationError):Orders(ws).build([d['id']])

def test_crop_warning_acceptance_is_tied_to_render(tmp_path):
    s=Store(tmp_path);ws=Workspace(s,Network(s));front=make_asset(s,'red')
    key='render-one';s.render_put(key,front)
    template_key,template_version,_=ws.compiler.template_identity('standard','auto')
    face={'id':uid(),'name':'Test Card','compiled':{'renderKey':key,'generationVersion':GENERATION_VERSION,
          'templateKey':template_key,'templateVersion':template_version,'crop':{'warning':True}}}
    card={'id':uid(),'name':'Test Card','quantity':1,'scryfall':{},'faces':[face]}
    deck=s.put('decks',{'name':'Crop Test','settings':dict(DEFAULT_SETTINGS,backAsset=front['id']),
                         'status':'prepared','cards':[card]})
    plan=Orders(ws).plan([deck['id']])
    assert len(plan['issues'])==1 and ws.deck(deck['id'])['summary']['warnings']==1
    with pytest.raises(ValidationError):Orders(ws).build([deck['id']],acknowledge=True)
    with pytest.raises(ValidationError,match='render changed'):
        ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':face['id'],
                           'acceptWarning':True,'renderKey':'stale'})
    accepted=ws.mutate_card(deck['id'],card['id'],{'revision':deck['revision'],'faceId':face['id'],
                           'acceptWarning':True,'renderKey':key})
    assert not Orders(ws).plan([deck['id']])['issues']
    assert ws.deck(deck['id'])['summary']['warnings']==0
    assert Orders(ws).build([deck['id']])['count']==1
    second='render-two';s.render_put(second,front)
    accepted['cards'][0]['faces'][0]['compiled']['renderKey']=second
    s.put('decks',accepted,accepted['revision'])
    assert len(Orders(ws).plan([deck['id']])['issues'])==1
