"""Compare repeated normalization with actual browser-engine asset reuse."""
import argparse,base64,functools,http.server,json,subprocess,sys,tempfile,threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_website import build_site,copy_site

INJECT='''
import time
from foundry.images import ingest_image
baseline_images={'__package__':'foundry','__name__':'foundry._ingest_baseline'}
baseline_source=base64.b64decode('BASELINE').decode()
if baseline_source:exec(baseline_source,baseline_images)
original_request=request

def request(app,method,url,body,headers):
    if str(url).startswith('/api/__test__/ingest/'):
        warm=ingest_image(app.store,body)
        baseline=not str(url).endswith('/cached')
        operation=baseline_images.get('ingest_image',ingest_image) if baseline else ingest_image
        retained=app.store._image_ingest_cache
        if baseline:app.store._image_ingest_cache=None
        started=time.perf_counter()
        try:
            for index in range(8):
                result=operation(app.store,body)
                if result['id']!=warm['id']:raise AssertionError('Normalized bytes changed')
        finally:app.store._image_ingest_cache=retained
        result={'seconds':time.perf_counter()-started,'baseline':baseline,'asset':result['id'],
            'width':result['width'],'height':result['height'],'bytes':result['size'],'repeats':8}
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--baseline',help='Optional historical revision; default compares with the cache disabled.')
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/image-ingest-profile.json')
    args=parser.parse_args()
    old=subprocess.check_output(['git','show',args.baseline+':ProxyFoundry/foundry/images.py'],cwd=ROOT) if args.baseline else b''
    injected=INJECT.replace('BASELINE',base64.b64encode(old).decode())
    raw=args.image.read_bytes();trials=[]
    with tempfile.TemporaryDirectory(prefix='pf-ingest-') as temporary,sync_playwright() as playwright:
        tmp=Path(temporary);build_site(tmp);site=copy_site(tmp)
        worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8');anchor='def browser_request(method, url, body, headers):'
        assert source.count(anchor)==1;worker.write_text(source.replace(anchor,injected+'\n'+anchor),encoding='utf-8')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        browser=playwright.chromium.launch(headless=False)
        try:
            page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=120000)
            for baseline in [True,False,False,True]:
                row=page.evaluate('''async({encoded,baseline})=>{
                    const ui=await import('/site/ui.js'),bytes=Uint8Array.from(atob(encoded),value=>value.charCodeAt(0));
                    return ui.blobRequest('/api/__test__/ingest/'+(baseline?'baseline':'cached'),new Blob([bytes]),'image/png');
                }''',{'encoded':base64.b64encode(raw).decode(),'baseline':baseline})
                trials.append(row);print(json.dumps(row),flush=True)
            assert not errors,errors
            assert len({row['asset'] for row in trials})==1
        finally:browser.close();server.shutdown();server.server_close();thread.join(timeout=5)
    report={'baseline':args.baseline or 'normalization with cache disabled','revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'note':'Warm same-byte inputs through actual static browser engine. Python operation timers exclude startup and request body transfer. Bounded cache retains IDs only; all returned normalized PNG hashes match. No deck throughput claim.','sourceBytes':len(raw),'trials':trials}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()