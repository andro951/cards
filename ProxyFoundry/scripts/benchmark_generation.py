"""Measure production generation in a new isolated browser workspace.

Uses read-only deck metadata and repository artwork. No user workspace is edited.
"""
import argparse,base64,copy,functools,http.server,json,logging,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(ROOT))
from scripts.static_server import StaticSiteServer

HOOK='''
import base64,logging,time,copy
benchmark_timings=[]
benchmark_persists=[]
original_benchmark_persist=app.store.persist
def benchmark_persist(path):
    active=getattr(app.store,'generation',None)
    benchmark_persists.append({'bytes':Path(path).stat().st_size,'generation':active['id'] if active else None})
    return original_benchmark_persist(path)
app.store.persist=benchmark_persist
class BenchmarkTimingHandler(logging.Handler):
    def emit(self,record):
        message=record.getMessage()
        if message.startswith('TIMING '):
            try:benchmark_timings.append(json.loads(message[7:]))
            except ValueError:pass
app.log.addHandler(BenchmarkTimingHandler())
from foundry import timing as benchmark_timing
benchmark_timing.THRESHOLD_SECONDS=0
original_benchmark_request=request
def request(app,method,url,body,headers):
    if url=='/api/__benchmark/seed':
        from foundry.images import ingest_image
        from foundry.domain import uid
        payload=json.loads(body)
        deck=payload['deck'];deck['id']=uid();deck['revision']=1;deck['name']='Generation benchmark';deck['status']='draft'
        deck['settings']['symbols']={name:ingest_image(app.store,base64.b64decode(raw))['id'] for name,raw in payload['symbols'].items()}
        deck['settings']['backAsset']=None;deck['settings'].pop('backDesign',None)
        deck['settings']['dataJsonSource']=None;deck['settings']['artist']='ChatGPT'
        for card in deck['cards']:
            card['id']=uid()
            for face in card['faces']:
                face['id']=uid()
                for key in ['compiled','lastRender','preparationKey','preparedAt','error','artOverride']:
                    face.pop(key,None)
            sf=card['scryfall'];asset=app.store.add_asset(json.dumps(sf).encode(),'application/json')
            app.store.cache_put('https://api.scryfall.com/cards/'+sf['id'],asset,time.time())
        # Match the database footprint in the user's diagnostic run.
        if payload.get('padding'):
            app.store.put('benchmark-padding',{'id':'padding','value':'x'*payload['padding']})
        saved=app.store.put('decks',deck)
        benchmark_timings.clear();benchmark_persists.clear()
        return {'status':200,'mime':'application/json','body':json.dumps({'id':saved['id']}).encode(),'headers':{}}
    if url=='/api/__benchmark/timings':
        return {'status':200,'mime':'application/json','body':json.dumps(benchmark_timings).encode(),'headers':{}}
    if url=='/api/__benchmark/report':
        summaries=sorted((app.store.home/'logs').glob('generation-*.json'),key=lambda p:p.stat().st_mtime)
        report={'persistCount':len(benchmark_persists),'generationPersistCount':sum(bool(row['generation']) for row in benchmark_persists),'persistBytes':sum(row['bytes'] for row in benchmark_persists),'generation':json.loads(summaries[-1].read_text()) if summaries else None}
        return {'status':200,'mime':'application/json','body':json.dumps(report).encode(),'headers':{}}
    return original_benchmark_request(app,method,url,body,headers)
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--site',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=18)
    parser.add_argument('--workers',type=int)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--folder',action='store_true')
    parser.add_argument('--padding',type=int,default=6*1024*1024)
    parser.add_argument('--export-images',action='store_true')
    parser.add_argument('--click',action='store_true')
    options=parser.parse_args()
    options.output.mkdir(parents=True,exist_ok=True)
    deck=json.loads((ROOT/'test-results/generation-20261016/derevi2-source-deck.json').read_text(encoding='utf-8'))
    if options.limit:
        count=options.limit
        deck['cards']=deck['cards'][:max(1,count-4)]+deck['cards'][-min(4,count-1):]
    symbols={name:base64.b64encode((ROOT.parent/'derevi2/set_symbol'/(name+'.png')).read_bytes()).decode() for name in ['common','uncommon','rare','mythic']}
    worker=options.site/'web/engine-worker.js'
    text=worker.read_text(encoding='utf-8')
    if 'class BenchmarkTimingHandler' in text:
        start=text.index('\nimport base64,logging,time,copy\n');end=text.index('def browser_request(method, url, body, headers):',start)
        text=text[:start]+text[end:]
    worker.write_text(text.replace('def browser_request(method, url, body, headers):',HOOK+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=StaticSiteServer(('127.0.0.1',0),functools.partial(Handler,directory=str(options.site)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin='http://127.0.0.1:'+str(server.server_port)
    try:
        with sync_playwright() as pw:
            context=pw.chromium.launch_persistent_context(str(options.output/'browser-profile'),headless=True,viewport={'width':1280,'height':900})
            browser=context.browser
            if options.workers:
                context.add_init_script('Object.defineProperty(navigator,"deviceMemory",{get:()=>8});Object.defineProperty(navigator,"hardwareConcurrency",{get:()=>'+str(options.workers)+'});')
            page=context.new_page();page.set_default_timeout(180000)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(origin);page.locator('#import-deck').wait_for(timeout=180000)
            if options.folder:
                page.evaluate('''async()=>{const root=await navigator.storage.getDirectory();const folder=await root.getDirectoryHandle('isolated-selected-folder',{create:true});await(await import('/web/storage-choice.js')).useFolder(folder);}''')
                page.reload();page.locator('#import-deck').wait_for(timeout=180000)
            ident=page.evaluate('''async payload=>(await(await import('/site/ui.js')).api('/api/__benchmark/seed',payload)).id''',{'deck':deck,'symbols':symbols,'padding':options.padding})
            print('Seeded',len(deck['cards']),'cards; folder=',options.folder,flush=True)
            page.evaluate('id=>location.hash="deck/"+id+"/cards"',ident)
            page.locator('#generate-deck').wait_for(timeout=60000)
            started=time.perf_counter()
            if options.click:
                page.click('#generate-deck')
                page.locator('#generation-screen,#artwork-finish').first.wait_for(timeout=60000)
                if page.locator('#artwork-finish').count():
                    assert '0 cards need artwork' in page.locator('body').inner_text()
                    page.click('#artwork-finish')
                try:page.locator('#generation-screen').wait_for(timeout=30000)
                except Exception:
                    page.screenshot(path=str(options.output/'blocked.png'))
                    print(page.locator('body').inner_text()[-8000:],flush=True)
                    raise
                page.locator('#generation-screen').wait_for(state='detached',timeout=1200000)
            result=page.evaluate('''async({id,render,clicked})=>{
                const ui=await import('/site/ui.js');const started=performance.now();
                if(render&&!clicked)await(await import('/site/render.js')).renderDecks([id],{artChecked:true,notify:false});
                else if(!clicked)await ui.job('/api/decks/'+id+'/prepare',{}, {label:'Prepare benchmark'});
                return {seconds:(performance.now()-started)/1000,deck:await ui.api('/api/decks/'+id),report:await ui.api('/api/__benchmark/report'),timings:await ui.api('/api/__benchmark/timings'),device:{cores:navigator.hardwareConcurrency,memory:navigator.deviceMemory},storageType:ui.state.bootstrap.storageType};
            }''',{'id':ident,'render':options.render and not options.click,'clicked':options.click})
            if options.click:result['seconds']=time.perf_counter()-started
            result['errors']=errors;result['wallSeconds']=time.perf_counter()-started
            (options.output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print('Generation complete:',round(result['seconds'],3),'seconds',flush=True)
            if options.render:
                expected=result['deck']['summary']['rendered']
                print('Checking reload',flush=True)
                page.reload()
                try:page.locator('#generate-deck').wait_for(timeout=30000)
                except Exception:
                    page.screenshot(path=str(options.output/'reload-blocked.png'))
                    print(page.locator('body').inner_text()[-8000:],flush=True)
                    raise
                saved=page.evaluate('''async id=>{const ui=await import('/site/ui.js');return(await ui.api('/api/decks/'+id)).summary;}''',ident)
                assert saved['rendered']==expected and expected==sum(len(c['faces']) for c in deck['cards']),saved
                result['reloadVerified']=saved
                print('Reload verified:',saved,flush=True)
                if options.export_images:
                    image_folder=options.output/'images';image_folder.mkdir(exist_ok=True)
                    for n,face in enumerate(f for c in result['deck']['cards'] for f in c['faces']):
                        png=page.evaluate('''async hash=>{const root=window.__pfWorkspaceDirectory,assets=await root.getDirectoryHandle('assets'),folder=await assets.getDirectoryHandle(hash.slice(0,2)),blob=await(await folder.getFileHandle(hash)).getFile();return new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob);});}''',face['compiled']['render']['asset_id'])
                        (image_folder/(str(n)+'-'+face['name'].replace('/','_')+'.png')).write_bytes(base64.b64decode(png))
                        print('Exported',n+1,flush=True)
            (options.output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            totals={}
            for row in result['timings']:
                stage=row.get('stage','');value=row.get('seconds',0)
                summary=totals.setdefault(stage,{'seconds':0,'count':0,'max':0})
                summary['seconds']+=value;summary['count']+=1;summary['max']=max(summary['max'],value)
            report={key:result.get(key) for key in ['seconds','wallSeconds','device','storageType','errors','report','reloadVerified']}
            report['faces']=result['deck'].get('summary',{});report['timings']=totals
            (options.output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report),flush=True)
            page.screenshot(path=str(options.output/'finished.png'))
            context.close();browser.close()
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
