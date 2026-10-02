"""Measure foreground requests during work in the real static browser engine.

The slow fixture is injected only into a temporary build. It isolates queue
blocking from network, artwork and native rendering; it is not a deck benchmark.
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

ROOT=Path(__file__).resolve().parents[1]
INJECT='''
original_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/responsiveness-job':
        import time
        def operation(update,cancel):
            for index in range(20):
                if cancel():raise ValueError('Cancelled at checkpoint')
                time.sleep(.1)
                update(index+1,20,'Completed chunk '+str(index+1))
            return {'chunks':20}
        result=app.jobs.start('Responsiveness fixture',operation)
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
'''
DRIVE='''async()=>{
    const ui=await import(`/site/ui.js`);
    const started=performance.now();
    const job=await ui.api(`/api/__test__/responsiveness-job`,{});
    const startSeconds=(performance.now()-started)/1000;
    let state;
    do{
        await new Promise(resolve=>setTimeout(resolve,20));
        state=await ui.api(`/api/jobs/${job.id}`);
    }while(state.state===`queued`);
    const ticks=[];
    let previous=performance.now();
    const timer=setInterval(()=>{const now=performance.now();ticks.push(now-previous);previous=now;},20);
    const foreground=performance.now();
    await ui.api(`/api/decks`);
    const foregroundSeconds=(performance.now()-foreground)/1000;
    clearInterval(timer);
    let complete=await ui.api(`/api/jobs/${job.id}`);
    while(![`done`,`failed`,`cancelled`].includes(complete.state)){
        await new Promise(resolve=>setTimeout(resolve,20));
        complete=await ui.api(`/api/jobs/${job.id}`);
    }
    const second=await ui.api(`/api/__test__/responsiveness-job`,{});
    do{
        await new Promise(resolve=>setTimeout(resolve,20));
        state=await ui.api(`/api/jobs/${second.id}`);
    }while(state.state===`queued`);
    const cancel=performance.now();
    await ui.api(`/api/jobs/${second.id}/cancel`,{});
    const cancelAcknowledgeSeconds=(performance.now()-cancel)/1000;
    do{
        await new Promise(resolve=>setTimeout(resolve,20));
        state=await ui.api(`/api/jobs/${second.id}`);
    }while(![`done`,`failed`,`cancelled`].includes(state.state));
    return {startSeconds,foregroundSeconds,maxMainThreadTimerGapMilliseconds:Math.max(0,...ticks),
        mainThreadTicks:ticks.length,cancelAcknowledgeSeconds,cancelFinishSeconds:(performance.now()-cancel)/1000,
        cancelledState:state.state,completedChunksBeforeCancel:state.done,fixtureSeconds:2};
}'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/responsiveness-profile.json')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--cooperative',action='store_true',help='Yield after each safe job chunk')
    parser.add_argument('--verify',action='store_true',help='Require foreground replies before the job finishes')
    options=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pf-responsiveness-') as temporary:
        site=Path(temporary)/'site'
        subprocess.run([sys.executable,str(ROOT/'scripts/build_web.py'),'--output',str(site)],cwd=ROOT,check=True,capture_output=True)
        worker=site/'web/engine-worker.js'
        source=worker.read_text(encoding='utf-8')
        anchor='def browser_request(method, url, body, headers):'
        assert source.count(anchor)==1,'Engine fixture injection point changed'
        injected=INJECT.replace("update(index+1,20,'Completed chunk '+str(index+1))", "update(index+1,20,'Completed chunk '+str(index+1))\n                yield") if options.cooperative else INJECT
        worker.write_text(source.replace(anchor,injected+'\n'+anchor),encoding='utf-8')
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(site)))
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
                    assert all(row['cancelledState']=='cancelled' for row in rows),rows
                    if options.verify:
                        assert options.cooperative,'Verification requires the resumable job fixture'
                        assert all(row['foregroundSeconds']<.75 for row in rows),rows
                        assert all(row['cancelAcknowledgeSeconds']<.5 for row in rows),rows
                    report={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                        'at':time.time(),'storageType':'browser','headless':options.headless,'cooperative':options.cooperative,'startupSeconds':startup,
                        'note':'Synthetic two-second job in 100 ms chunks; no card artwork or native rendering.', 'trials':rows}
                    options.output.parent.mkdir(parents=True,exist_ok=True)
                    options.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(json.dumps(report,indent=2),flush=True)
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
