"""Measure actual static browser startup without rendering or importing artwork."""
import argparse,functools,http.server,json,shutil,subprocess,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_website import build_site,copy_site

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/startup-profile.json')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args();assert 1<=args.repeats<=10;trials=[]
    with tempfile.TemporaryDirectory(prefix='pf-startup-') as temporary,sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=False)
        try:
            for base in ['/','/cards/']:
                tmp=Path(temporary)/('root' if base=='/' else 'subpath');tmp.mkdir()
                build_site(tmp,base);site=copy_site(tmp)
                bootstrap=site/'web/bootstrap.js';source=bootstrap.read_text(encoding='utf-8')
                source=source.replace('const data=event.data;','const data=event.data;\n    if(data.type==="startup-timing"){window.__startupStages??=[];window.__startupStages.push(data);}')
                bootstrap.write_text(source,encoding='utf-8')
                class Quiet(http.server.SimpleHTTPRequestHandler):
                    def log_message(self,*args):pass
                served=site if base=='/' else tmp/'served'
                if base!='/':
                    served.mkdir();shutil.move(str(site),str(served/'cards'))
                server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(served)))
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    for repeat in range(args.repeats):
                        context=browser.new_context();page=context.new_page();errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        try:
                            for warm in [False,True]:
                                started=time.perf_counter()
                                if warm:page.reload(wait_until='domcontentloaded')
                                else:page.goto('http://127.0.0.1:'+str(server.server_port)+base,wait_until='domcontentloaded')
                                try:
                                    page.wait_for_function('document.querySelector("#import-deck")&& !document.querySelector("#browser-startup")',timeout=120000)
                                    row={'base':base,'repeat':repeat,'warm':warm,'seconds':time.perf_counter()-started,'stages':page.evaluate('window.__startupStages||[]'),'errors':errors.copy()}
                                except Exception:
                                    args.output.with_suffix('.failure.json').write_text(json.dumps({'base':base,'warm':warm,'body':page.locator('body').inner_text(),'errors':errors,'diagnostics':page.evaluate('localStorage.getItem("bulk-proxy-forge-browser-diagnostics")')},indent=2),encoding='utf-8');raise
                                diagnostics=page.evaluate('JSON.parse(localStorage.getItem("bulk-proxy-forge-browser-diagnostics"))')
                                assert any(entry['kind']=='startup timing' and '"website-total"' in entry['detail'] for entry in diagnostics['entries'])
                                assert not errors,errors
                                assert any(stage['stage']=='engine-total' and stage['outcome']=='ok' for stage in row['stages'])
                                trials.append(row);print(json.dumps(row),flush=True)
                        finally:context.close()
                finally:server.shutdown();server.server_close();thread.join(timeout=5)
        finally:browser.close()
    report={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'note':'Fresh browser contexts and warm reloads; shared browser process may retain CDN HTTP cache. No import or generation. Local static bundle transport.','trials':trials}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()