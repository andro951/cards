"""Measure UI request priority during a background asset burst in the static engine.

Each temporary asset request occupies the Python worker for 50 ms. This isolates
request scheduling, not live asset throughput or native drawing speed.
"""
import argparse
import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from static_server import StaticSiteServer

ROOT=Path(__file__).resolve().parents[1]
INJECT='''
original_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/foreground-job':
        job=app.jobs.start('Foreground priority fixture',lambda update,cancel:{'ok':True})
        return {'status':200,'mime':'application/json','body':json.dumps(job).encode(),'headers':{}}
    if str(url).startswith('/img/__test__/slow'):
        import time
        time.sleep(.05)
        return {'status':200,'mime':'application/json','body':b'{"ok":true}','headers':{}}
    return original_request(app,method,url,body,headers)
'''
DRIVE='''async()=>{
    const ui=await import('/site/ui.js');
    const requests=Array.from({length:20},(_,i)=>fetch('/img/__test__/slow?i='+i).then(response=>response.json()));
    await new Promise(resolve=>setTimeout(resolve,30));
    const start=performance.now();await ui.api('/api/templates');const foregroundSeconds=(performance.now()-start)/1000;
    const jobStart=performance.now();
    const job=await ui.api('/api/__test__/foreground-job',{});
    let state;
    do{
        await new Promise(resolve=>setTimeout(resolve,5));
        state=await ui.api('/api/jobs/'+job.id);
    }while(!['done','failed','cancelled'].includes(state.state));
    if(state.state!=='done')throw new Error(state.error||'Foreground fixture failed');
    const foregroundJobSeconds=(performance.now()-jobStart)/1000;
    const images=await Promise.all(requests);return {foregroundSeconds,foregroundJobSeconds,assets:images.length};
}'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/request-priority-profile.json')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--verify',action='store_true',help='Require UI replies ahead of the pending asset burst')
    options=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pf-responsiveness-') as temporary:
        site=Path(temporary)/'site'
        subprocess.run([sys.executable,str(ROOT/'scripts/build_web.py'),'--output',str(site)],cwd=ROOT,check=True,capture_output=True)
        worker=site/'web/engine-worker.js'
        source=worker.read_text(encoding='utf-8')
        anchor='def browser_request(method, url, body, headers):'
        assert source.count(anchor)==1,'Engine fixture injection point changed'
        worker.write_text(source.replace(anchor,INJECT+'\n'+anchor),encoding='utf-8')
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=StaticSiteServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=options.headless)
                try:
                    page=browser.new_page()
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    started=time.perf_counter()
                    page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                    page.locator('#import-deck').wait_for(timeout=120000)
                    startup=time.perf_counter()-started
                    rows=[page.evaluate(DRIVE) for _ in range(3)]
                    assert not errors,errors
                    assert all(row['assets']==20 for row in rows),rows
                    if options.verify:
                        assert all(row['foregroundSeconds']<.35 and row['foregroundJobSeconds']<.35 for row in rows),rows
                    report={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                        'at':time.time(),'storageType':'browser','headless':options.headless,'startupSeconds':startup,
                        'note':'Twenty serial 50 ms asset reads per trial; no artwork download or native rendering.', 'trials':rows}
                    options.output.parent.mkdir(parents=True,exist_ok=True)
                    options.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(json.dumps(report,indent=2),flush=True)
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()