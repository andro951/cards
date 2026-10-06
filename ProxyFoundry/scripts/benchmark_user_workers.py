"""Serial versus worker render/save timings on the recovered Supernatural deck."""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from foundry.server import App,LocalServer,Handler
from foundry.storage import Store

DRIVE='''async ({plan,origin,count,worker})=>{
    const {NativeRenderer,NativeRenderPool}=await import('/site/native-render-pool.js');
    const {api,blobRequest}=await import('/site/ui.js');
    const timings=[],started=performance.now();
    const pool=new NativeRenderPool({count,createRenderer:()=>new NativeRenderer({origin,worker,
        diagnostic:message=>{if(message.stage==='timing')timings.push({...message.diagnostic,key:message.key});}
    })});
    await pool.run(plan.targets,{
        load:async target=>(await api('/api/render-sessions/'+plan.id+'/'+target.key)).data,
        save:async(target,output)=>{
            const start=performance.now();
            await blobRequest('/api/render-sessions/'+plan.id+'/'+target.key,output.blob,'image/png');
            timings.push({stage:'save',key:target.key,seconds:(performance.now()-start)/1000});
        },
        saved:async(target,output,done)=>{await window.benchmarkProgress({done,total:plan.targets.length,name:target.name,seconds:(performance.now()-started)/1000});}
    });
    return {seconds:(performance.now()-started)/1000,timings,saved:pool.saved};
}'''

def main():
    output=ROOT/'test-results/user-deck-workers'
    recovered=json.loads((output/'prepared.json').read_text(encoding='utf-8'))
    store=Store(output/'workspace');app=App(store)
    original=Handler.runtime_get
    old_bridge=subprocess.check_output(['git','show','a043a76:ProxyFoundry/site/runtime-bridge.js'],cwd=ROOT)
    mode=['serial']
    def runtime_get(handler,path,query):
        if path=='/site/runtime-bridge.js' and mode[0]=='serial':
            return handler.send_bytes(old_bridge,'application/javascript')
        return original(handler,path,query)
    Handler.runtime_get=runtime_get
    server=LocalServer(app,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'source':recovered['source'],'cards':recovered['cards'],'faces':recovered['faces'],'storage':'Isolated local filesystem workspace; production render/save API. Not the browser selected-folder storage backend.','trials':[]}
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=False,args=['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows'])
            page=browser.new_page();page.set_default_timeout(180000)
            page.expose_function('benchmarkProgress',lambda row:print(mode[0],json.dumps(row),flush=True) if row['done']%10==0 or row['done']==1 else None)
            page.on('pageerror',lambda error:print('PAGE ERROR',error,flush=True))
            page.goto(server.origin);page.locator('#import-deck').wait_for(timeout=120000)
            modes=['serial','workers']
            if '--workers-only' in sys.argv:modes=['workers']
            for variant in modes:
                mode[0]=variant
                #Both trials must perform fresh writes, including content-addressed assets.
                #This store is the recovered, isolated benchmark workspace only.
                store.clear_deck_renders(recovered['deck']['id'])
                plan=app.start_render_session([recovered['deck']['id']],force=True)
                if '--small' in sys.argv:plan['targets']=plan['targets'][:7]
                print('BEGIN',variant,len(plan['targets']),flush=True)
                trial=page.evaluate(DRIVE,{'plan':plan,'origin':app.runtime_origin,'count':1 if variant=='serial' else 2,'worker':variant!='serial'})
                trial['mode']=variant;report['trials'].append(trial)
                pictures=output/variant;pictures.mkdir(exist_ok=True)
                for target in plan['targets']:
                    saved=store.render_get(target['key']);assert saved
                    raw=store.asset_path(saved['asset_id']).read_bytes()
                    with Image.open(store.asset_path(saved['asset_id'])) as image:assert image.size==(2010,2814)
                    (pictures/(target['key']+'.png')).write_bytes(raw)
                (output/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                print('DONE',variant,trial['seconds'],flush=True)
            browser.close()
        comparisons=[]
        for target in plan['targets']:
            left=output/'serial'/(target['key']+'.png');right=output/'workers'/(target['key']+'.png')
            if not left.is_file() or not right.is_file():continue
            with Image.open(left) as a,Image.open(right) as b:
                difference=ImageChops.difference(a.convert('RGBA'),b.convert('RGBA'))
                extrema=difference.getextrema();comparisons.append({'name':target['name'],'maxChannelDifference':max(hi for lo,hi in extrema),'bounds':difference.convert('RGB').getbbox()})
        report['comparisons']=comparisons
        started=time.perf_counter();cached=app.start_render_session([recovered['deck']['id']]);report['cachedPlanSeconds']=time.perf_counter()-started
        report['cachedFaces']=cached['cached'];report['cachedQueued']=len(cached['targets'])
        (output/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('REPORT',output/'benchmark.json',flush=True)
    finally:
        Handler.runtime_get=original;server.shutdown();server.server_close();thread.join(timeout=5);app.close()

if __name__=='__main__':main()
