"""Compare paired ZIP construction through the real browser storage bridge."""
import argparse,functools,http.server,json,subprocess,sys,tempfile,threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
INJECT='''
original_order_profile_request=request

def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/order-zip/seed':
        from foundry.domain import GENERATION_VERSION,uid
        from foundry.workspace import DEFAULT_SETTINGS
        data=json.loads(body);cards=[]
        back=app.store.add_asset(b'B'*(4*1024*1024),'image/png',2010,2814)
        template_key,version,_=app.ws.compiler.template_identity('standard','auto')
        for index in range(data['cards']):
            front=app.store.add_asset(index.to_bytes(4,'little')+b'F'*(8*1024*1024-4),'image/png',2010,2814)
            render_key='profile-front-'+str(index);app.store.render_put(render_key,front)
            cards.append({'id':uid(),'name':'ZIP profile card '+str(index),'quantity':data['copies'],
                'scryfall':{'name':'ZIP profile card '+str(index),'layout':'normal','type_line':'Creature — Human'},
                'faces':[{'id':uid(),'name':'ZIP profile card '+str(index),'group':'standard','compiled':{'renderKey':render_key,'generationVersion':GENERATION_VERSION,'templateKey':template_key,'templateVersion':version}}]})
        deck=app.store.put('decks',{'name':'ZIP benchmark','settings':dict(DEFAULT_SETTINGS,backAsset=back['id']),'status':'prepared','cards':cards})
        app.ws.deck(deck['id'])
        return {'status':200,'mime':'application/json','body':json.dumps({'deckId':deck['id']}).encode(),'headers':{}}
    if str(url)=='/api/__test__/order-zip/build':
        import shutil,zipfile
        from js import resetOrderZipStats,readOrderZipStats
        data=json.loads(body);original=zipfile.ZipFile.write
        original_archive=app.orders.archive
        def larger_write(archive,filename,arcname=None,compress_type=None,compresslevel=None):
            info=zipfile.ZipInfo.from_file(filename,arcname);info.compress_type=archive.compression
            with Path(filename).open('rb') as source,archive.open(info,'w') as target:shutil.copyfileobj(source,target,1024*1024)
        def operation(update,cancel):
            import time
            resetOrderZipStats();started=time.perf_counter()
            if data['mode']!='native':app.orders.archive=None
            if data['mode']=='large':zipfile.ZipFile.write=larger_write
            try:
                result=yield from app.orders.build_steps([data['deckId']],False,update,cancel)
                return {'mode':data['mode'],'seconds':time.perf_counter()-started,'zipBytes':result['zipBytes'],'count':result['count'],'download':result['download'],**json.loads(str(readOrderZipStats()))}
            finally:
                zipfile.ZipFile.write=original
                app.orders.archive=original_archive
        result=app.jobs.start('ZIP profile',operation)
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_order_profile_request(app,method,url,body,headers)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--modes',default='baseline,native')
    parser.add_argument('--cards',type=int,default=10)
    parser.add_argument('--copies',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.cards<=10000 or not 1<=args.copies<=10000 or args.cards*args.copies>10000:parser.error('Choose between 1 and 10,000 physical cards.')
    with tempfile.TemporaryDirectory(prefix='bpf-order-zip-') as temp,sync_playwright() as p:
        site=Path(temp)/'site'
        subprocess.run([sys.executable,str(ROOT/'scripts/build_web.py'),'--output',str(site)],cwd=ROOT,check=True,capture_output=True)
        worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8');anchor='def browser_request(method, url, body, headers):'
        assert source.count(anchor)==1
        source=source.replace('let python;',"let python;self.resetOrderZipStats=()=>{self.__orderZipStats={};};self.readOrderZipStats=()=>JSON.stringify(self.__orderZipStats);")
        worker.write_text(source.replace(anchor,INJECT+'\n'+anchor),encoding='utf-8')
        fs=site/'web/workspace-fs.js';source=fs.read_text(encoding='utf-8')
        anchor='const call=(operation,path,values={},body=null)=>{'
        assert source.count(anchor)==1
        fs.write_text(source.replace(anchor,anchor+"\n        if(self.__orderZipStats&&/^(assets|renders|orders)\\//.test(path))self.__orderZipStats[operation]=(self.__orderZipStats[operation]||0)+1;"),encoding='utf-8')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
            page.locator('#import-deck').wait_for(timeout=90000)
            deck=page.evaluate("async data=>{const {api}=await import('/site/ui.js');return api('/api/__test__/order-zip/seed',data);}",{'cards':args.cards,'copies':args.copies})
            rows=[]
            for mode in args.modes.split(','):
                row=page.evaluate('''async({mode,deckId})=>{
                    const {job}=await import('/site/ui.js');const ticks=[];let previous=performance.now();
                    const timer=setInterval(()=>{const now=performance.now();ticks.push(now-previous);previous=now;},20);
                    try{const result=await job('/api/__test__/order-zip/build',{mode,deckId},{onStarted:id=>window.profileJob=id});return {...result,maxTimerGapMs:Math.max(...ticks)};}
                    catch(error){const {api}=await import('/site/ui.js');return {mode,error:error.message,job:await api('/api/jobs/'+window.profileJob),browser:localStorage.getItem('bulk-proxy-forge-browser-diagnostics')};}
                    finally{clearInterval(timer);}
                }''',{'mode':mode,'deckId':deck['deckId']})
                rows.append(row);print(json.dumps(row),flush=True)
                args.output.parent.mkdir(exist_ok=True,parents=True);args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
        finally:browser.close();server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()