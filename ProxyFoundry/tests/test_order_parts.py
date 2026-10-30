"""Saved orders are maximally packed whole front/back pairs in classic ZIP files."""
import io,json,zipfile
from types import SimpleNamespace
from PIL import Image
from foundry.storage import Store
from foundry.orders import Orders
from foundry.domain import uid
from foundry.images import ingest_image

def test_order_folder_packs_to_limit_preserves_pairs_and_serves_native_parts(tmp_path,monkeypatch):
    import foundry.orders as orders
    from foundry.server import App
    from foundry.browser import request
    store=Store(tmp_path);raw=io.BytesIO();Image.new('RGB',(30,42),'purple').save(raw,'PNG')
    front=ingest_image(store,raw.getvalue());store.render_put('front',front)
    face={'id':uid(),'name':'Front','compiled':{'renderKey':'front'}}
    card={'id':uid(),'name':'Card','quantity':5,'scryfall':{'layout':'normal','type_line':'Creature'},'faces':[face]}
    deck=store.put('decks',{'name':'Order','status':'ready','settings':{'backAsset':front['id'],'createDfcSubstitutes':False},'cards':[card]})
    ws=SimpleNamespace(store=store,deck=lambda ident:deck)
    pair=front['size']*2+152+2*(len('FRONT/000001.png')+len('BACK/000001.png'))
    limit=22+2*pair;monkeypatch.setattr(orders,'MAX_BATCH_BYTES',limit)
    saved=Orders(ws).build([deck['id']]);assert [p['count'] for p in saved['parts']]==[2,2,1]
    assert [p['zipBytes'] for p in saved['parts']][:2]==[limit,limit]
    names=[]
    for part in saved['parts']:
        path=store.home/'orders'/saved['id']/part['filename']
        assert path.stat().st_size<=limit
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            for info in z.infolist():
                assert info.extract_version<45 and not info.extra and z.read(info)==raw.getvalue()
            names.extend(z.namelist())
    assert names==[f'{side}/{i:06d}.png' for i in range(1,6) for side in ['FRONT','BACK']]
    app=App(store)
    try:
        transfer=app.transfer(saved['id'],whole_file=True);headers={'X-Proxy-Transfer-Token':transfer['secret']}
        metadata=json.loads(request(app,'GET','/api/transfer/'+transfer['id']+'/metadata',headers=headers)['body'])
        assert metadata['protocolVersion']==3 and [b['count'] for b in metadata['batches']]==[2,2,1]
        files=json.loads(request(app,'GET','/api/transfer/'+transfer['id']+'/native-file',headers=headers)['body'])['files']
        assert len(files)==3 and all(row['path'].startswith('orders/'+saved['id']+'/') for row in files)
        store.begin_delete('orders',saved['id'])
        while store.cleanup_step().get('pending'):pass
        assert not list((store.home/'orders'/saved['id']).glob('*.zip'))
    finally:app.close()
