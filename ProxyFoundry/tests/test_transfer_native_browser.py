"""Actual browser transfers bypass synchronous Wasm file reads and survive IO exceptions."""
import base64,os
import pytest
from test_browser_storage import static_browser
from test_transfer_batches import make_order,TransferBatches

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual browser native ZIP ranges')

@pytest.mark.parametrize('static_browser',['msedge'] if os.name=='nt' else [None],indirect=True)
def test_transfer_uses_native_spans_and_filesystem_network_errors_leave_engine_usable(static_browser,tmp_path):
    directory,context,origin=static_browser
    source_zip=tmp_path/'source.zip';make_order(source_zip,payload_size=1200)
    plan=TransferBatches(source_zip,5,limit=6000);expected=list(plan.read(1,0,2000))
    raw=base64.b64encode(source_zip.read_bytes()).decode()
    fs=directory/'web/workspace-fs.js'
    script=fs.read_text(encoding='utf-8').replace('            request.send(body);',
        "            if(globalThis.__failOrderReads&&operation===`read`&&path.startsWith(`orders/`)&&Number(values.length)>=1000)throw new DOMException('Injected read connection failure','NetworkError');\n            request.send(body);")
    fs.write_text(script,encoding='utf-8')
    worker=directory/'web/engine-worker.js'
    hook='''
from foundry.browser import BrowserHandler
original_transfer_test_get=BrowserHandler.get
def transfer_test_get(self,path,query):
    if path=='/api/__test__/broken-read':
        return self.send_bytes(next((self.app.store.home/'orders').glob('*.zip')).read_bytes(),'application/zip')
    return original_transfer_test_get(self,path,query)
BrowserHandler.get=transfer_test_get
original_transfer_test_request=request
def request(app,method,url,body,headers):
    if url=='/api/__test__/native-transfer':
        import base64
        import foundry.transfer_batches as batches
        batches.MAX_BATCH_BYTES=6000
        order=app.store.put('orders',{'count':5,'cards':[],'decks':[]})
        (app.store.home/'orders'/(order['id']+'.zip')).write_bytes(base64.b64decode('ZIP_DATA'))
        transfer=app.transfer(order['id'])
        import js
        js.globalThis.__failOrderReads=True
        return {'status':200,'mime':'application/json','body':json.dumps(transfer).encode(),'headers':{}}
    return original_transfer_test_request(app,method,url,body,headers)
'''.replace('ZIP_DATA',raw)
    worker.write_text(worker.read_text(encoding='utf-8').replace('def browser_request(method, url, body, headers):',hook+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate('''async()=>{
        const {api}=await import('/site/ui.js'),{workspaceFetch}=await import('/site/workspace-fetch.js');
        const transfer=await api('/api/__test__/native-transfer',{});
        const path='/api/transfer/'+transfer.id+'/zip?batch=1';
        const headers={'X-Proxy-Transfer-Token':transfer.secret,Range:'bytes=0-1999'};
        const response=await workspaceFetch(path,{headers});
        const bytes=[...new Uint8Array(await response.arrayBuffer())];
        const legacy=await workspaceFetch('/api/transfer/'+transfer.id+'/zip',{headers:{...headers,Range:'bytes=0-31'}});
        const legacyBytes=[...new Uint8Array(await legacy.arrayBuffer())];
        const broken=await workspaceFetch('/api/__test__/broken-read');
        const error=await broken.json();
        const bootstrap=await api('/api/bootstrap');
        const denied=await workspaceFetch(path,{headers:{Range:'bytes=0-99'}});
        return {status:response.status,bytes,legacyStatus:legacy.status,legacyBytes,brokenStatus:broken.status,error:error.error,ready:bootstrap.browser,denied:denied.status};
    }''')
    assert result['status']==206 and result['bytes']==expected
    assert result['legacyStatus']==206 and result['legacyBytes']==list(source_zip.read_bytes()[:32])
    assert result['brokenStatus']==500 and 'I/O error' in result['error']
    assert result['ready'] is True and result['denied']==403
