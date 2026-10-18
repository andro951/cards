"""Benchmark bounded native-render/save overlap in a temporary static build.

The native renderer and production PNG save API are unchanged. --folder reuses
the already-approved CDP session and refuses to open a permission picker.
"""
import argparse,base64,functools,hashlib,http.server,io,json,subprocess,sys,tempfile,threading,time
from pathlib import Path

from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from profile_native_render import fixtures,SEED
from test_website import build_site,copy_site
from foundry.storage import Store


DRIVE='''async({deckId,mode,freshSaves})=>{
    const ui=await import(`/site/ui.js`);
    if(freshSaves)await ui.api(`/api/images/delete-all`,{});
    const plan=await ui.api(`/api/render-sessions`,{deckIds:[deckId],force:true});
    const targets=[];
    for(const target of plan.targets)targets.push({...target,...await ui.api(`/api/render-sessions/${plan.id}/${target.key}`)});
    if(plan.errors.length)throw new Error(plan.errors.join(`\n`));
    const frame=document.createElement(`iframe`);frame.className=`render-frame`;
    frame.setAttribute(`sandbox`,`allow-scripts allow-same-origin`);
    frame.src=`/runtime/host?parent=${encodeURIComponent(location.origin)}&owner=${encodeURIComponent(window.__pfOwner)}&experiment=${mode}`;
    document.body.append(frame);
    let readyResolve,readyReject,pending=null,prefetch=null;
    const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
    const stages=[],saved=[],outputs=[],longTasks=[],gaps=[];
    const observer=new PerformanceObserver(list=>longTasks.push(...list.getEntries().map(entry=>({
        milliseconds:entry.duration,startedAt:performance.timeOrigin+entry.startTime,
        attribution:[...entry.attribution].map(task=>({name:task.name,containerSrc:task.containerSrc,containerType:task.containerType}))}))));
    observer.observe({type:`longtask`,buffered:false});
    const listener=event=>{
        if(event.source!==frame.contentWindow||event.origin!==location.origin||event.data?.source!==`pf-native-runtime`)return;
        const m=event.data;
        if(m.type===`ready`)readyResolve();
        if(m.type===`diagnostic`&&m.stage===`timing`)stages.push({...m.diagnostic,key:m.key});
        if(m.type===`prefetched`&&prefetch&&m.key===prefetch.key)prefetch.resolve();
        if(m.type===`prefetch-failed`&&prefetch)prefetch.reject(new Error(m.error));
        if(m.type===`failed`){if(pending)pending.reject(new Error(m.error));else readyReject(new Error(m.error));}
        if(m.type===`rendered`&&pending&&m.key===pending.key)pending.resolve(m);
    };
    window.addEventListener(`message`,listener);
    const ping=setInterval(()=>frame.contentWindow.postMessage({source:`pf-app`,type:`ping`},location.origin),500);
    let tick,timer,last;
    const save=async(target,output)=>{
        const started=performance.now();
        const result=await ui.blobRequest(`/api/render-sessions/${plan.id}/${target.key}`,output.blob,`image/png`);
        saved.push({key:target.key,seconds:(performance.now()-started)/1000,bytes:output.blob.size});return result;
    };
    const settle=async promise=>{const result=await promise;if(result.error)throw result.error;};
    const bounded=(promise,ms,message)=>new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error(message)),ms);
        promise.then(result=>{clearTimeout(timer);resolve(result);},error=>{clearTimeout(timer);reject(error);});
    });
    let previous=null;
    try{
        await bounded(ready,65000,`Renderer startup timeout`);
        clearInterval(ping);last=performance.now();timer=setInterval(()=>{const now=performance.now();gaps.push(now-last);last=now;},16);
        window.__pipelineMeasuring=true;
        const started=performance.now();
        for(let index=0;index<targets.length;index++){
            const target=targets[index],nativeStart=performance.now();
            const render=new Promise((resolve,reject)=>{pending={key:target.key,resolve,reject};});
            frame.contentWindow.postMessage({source:`pf-app`,type:`render`,key:target.key,data:target.data},location.origin);
            let nextReady=null;
            if(mode===`overlap-prefetch`&&targets[index+1]){
                const next=targets[index+1];
                nextReady=new Promise((resolve,reject)=>{prefetch={key:next.key,resolve,reject};});
                frame.contentWindow.postMessage({source:`pf-app`,type:`__testPrefetch`,key:next.key,data:next.data},location.origin);
                nextReady=nextReady.then(()=>({}),error=>({error}));
            }
            const output=await bounded(render,150000,`Native render timeout`);
            pending=null;outputs.push({key:target.key,name:target.name,blob:output.blob,nativeSeconds:(performance.now()-nativeStart)/1000});
            //At most one older PNG can be saving while the next face renders.
            if(previous)await settle(previous);
            if(nextReady)await settle(nextReady);
            previous=save(target,output).then(()=>({}),error=>({error}));
            if(!mode.startsWith(`overlap`)){await settle(previous);previous=null;}
        }
        if(previous)await settle(previous);
        const seconds=(performance.now()-started)/1000;window.__pipelineMeasuring=false;clearInterval(timer);observer.disconnect();
        const images=[];
        for(const output of outputs){
            const raw=await output.blob.arrayBuffer();
            const hash=[...new Uint8Array(await crypto.subtle.digest(`SHA-256`,raw))].map(byte=>byte.toString(16).padStart(2,`0`)).join(``);
            const stored=await (await fetch(`/api/assets/${hash}`)).arrayBuffer();
            const storedHash=[...new Uint8Array(await crypto.subtle.digest(`SHA-256`,stored))].map(byte=>byte.toString(16).padStart(2,`0`)).join(``);
            if(hash!==storedHash)throw new Error(`Saved PNG bytes differ for ${output.name}`);
            const png=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(`,`)[1]);reader.readAsDataURL(output.blob);});
            images.push({key:output.key,name:output.name,hash,png,nativeSeconds:output.nativeSeconds});
        }
        return {mode,seconds,saved,images,stages,maxTimerGapMs:Math.max(0,...gaps),longTasks,visibility:document.visibilityState,schedulerYieldAvailable:!!window.scheduler?.yield,longTaskCount:longTasks.length,longTaskMs:longTasks.reduce((a,b)=>a+b.milliseconds,0),maxPendingSaves:mode.startsWith(`overlap`)?1:0};
    }finally{
        window.__pipelineMeasuring=false;if(previous)await previous;clearInterval(ping);clearInterval(timer);observer.disconnect();
        window.removeEventListener(`message`,listener);frame.contentWindow.postMessage({source:`pf-app`,type:`dispose`},location.origin);frame.remove();
    }
}'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',action='store_true')
    parser.add_argument('--input-latency',action='store_true',help='Measure actual keyboard command latency during native rendering/saves')
    parser.add_argument('--task-yields',action='store_true',help='Compare unchanged serial drawing with native stage/draw task yields')
    parser.add_argument('--fresh-saves',action='store_true',help='Delete prior generated assets before each trial, retaining warm frame/art caches')
    parser.add_argument('--cdp-url',default='http://127.0.0.1:9227')
    parser.add_argument('--output',type=Path)
    options=parser.parse_args()
    storage_type='selected-folder' if options.folder else 'browser'
    evidence=ROOT/'test-results'/('pipeline-'+storage_type+('-fresh' if options.fresh_saves else '')+('-task-yields' if options.task_yields else '')+('-input' if options.input_latency else ''));evidence.mkdir(parents=True,exist_ok=True)
    output=options.output or evidence/'results.json'
    with tempfile.TemporaryDirectory(prefix='pf-pipeline-') as temporary:
        tmp=Path(temporary);_,payload=fixtures(tmp)
        store=Store(tmp/'fixture-workspace');deck=store.list('decks')[0];deck.pop('revision',None);payload['deck']=deck
        back=deck['settings']['backAsset'];asset=store.asset(back)
        payload['assets'].append({'mime':asset['mime'],'bytes':base64.b64encode(store.asset_path(back).read_bytes()).decode()})
        build_site(tmp);site=copy_site(tmp)
        worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
        worker.write_text(source.replace('def browser_request(method, url, body, headers):',SEED+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
        bridge=site/'site/runtime-bridge.js';source=bridge.read_text(encoding='utf-8')
        source=source.replace('stage,seconds:Number(seconds.toFixed(4)),outcome','stage,seconds:Number(seconds.toFixed(4)),startedAt:performance.timeOrigin+started,outcome')
        anchor="    if(msg.type==='render'){"
        prefetch='''    if(msg.type==='__testPrefetch'){
          assetCacheReady.then(async cache=>{
            const paths=new Set([msg.data.artSource,msg.data.setSymbolSource,msg.data.watermarkSource]);
            for(const frame of msg.data.frames||[])for(const layer of [frame,...frame.masks||[]])paths.add(layer.src);
            await Promise.all([...paths].filter(cache.accepts).map(cache.get));post('prefetched',{key:msg.key});
          }).catch(error=>post('prefetch-failed',{key:msg.key,error:error.message}));return;
        }
'''
        assert source.count(anchor)==1
        bridge.write_text(source.replace(anchor,prefetch+anchor),encoding='utf-8')
        if options.task_yields:
            source=bridge.read_text(encoding='utf-8').replace('      await yieldToInput();','')
            source=source.replace("  async function measureNative(stage,key,operation){", "  const experiment=new URL(location.href).searchParams.get('experiment');\n  const taskTurn=()=>window.scheduler?.yield?window.scheduler.yield():sleep(0);\n  async function measureNative(stage,key,operation){")
            timing="      if(seconds>=.1)post('diagnostic',{key,stage:'timing',diagnostic:{stage,seconds:Number(seconds.toFixed(4)),startedAt:performance.timeOrigin+started,outcome}});"
            assert timing in source
            source=source.replace(timing,timing+"\n      if(experiment==='yield-stages'||experiment==='yield-draw')await taskTurn();\n      if(experiment==='yield-timer')await sleep(0);")
            source=source.replace("await window.drawText();await window.bottomInfoEdited();", "await window.drawText();if(experiment==='yield-draw')await taskTurn();await window.bottomInfoEdited();if(experiment==='yield-draw')await taskTurn();")
            source=source.replace("await window.watermarkEdited();window.drawFrames();window.drawCard();", "await window.watermarkEdited();if(experiment==='yield-draw')await taskTurn();window.drawFrames();if(experiment==='yield-draw')await taskTurn();window.drawCard();")
            source=source.replace("window.drawFrames();window.drawCard();", "window.drawFrames();if(experiment==='yield-draw')await taskTurn();window.drawCard();")
            bridge.write_text(source,encoding='utf-8')
        (site/'benchmark-connect.html').write_text('<!doctype html><title>Pipeline benchmark</title>')
        if options.folder:
            #The permission helper releases only its HTTP server, retaining its browser.
            (ROOT/'test-results/night-permission-release-server').write_text('release')
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        handler=functools.partial(QuietHandler,directory=str(site));deadline=time.monotonic()+15
        while True:
            try:server=http.server.ThreadingHTTPServer(('127.0.0.1',8769 if options.folder else 0),handler);break
            except OSError:
                if not options.folder or time.monotonic()>deadline:raise
                time.sleep(.25)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        report={'storageType':storage_type,'freshSaves':options.fresh_saves,'taskYields':options.task_yields,'inputLatency':options.input_latency,'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'note':'Prepared structural fixture using Supernatural artwork. Native drawing and production PNG persistence unchanged. Dependency/plan warmup excluded. One pending save maximum. Prefetch is experimental and runs only after explicit benchmark generation starts.','trials':[]}
        references={}
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.connect_over_cdp(options.cdp_url) if options.folder else playwright.chromium.launch(headless=False)
                context=browser.contexts[0] if options.folder else browser.new_context(viewport={'width':1440,'height':1000})
                page=context.new_page();page.set_default_timeout(240000)
                origin=f'http://127.0.0.1:{server.server_port}'
                try:
                    if options.folder:
                        page.goto(origin+'/benchmark-connect.html')
                        page.evaluate('''async()=>{
                            for(const registration of await navigator.serviceWorker.getRegistrations())await registration.unregister();
                            for(const key of await caches.keys())await caches.delete(key);
                            const storage=await import('/web/storage-choice.js');window.__originalFolder=await storage.savedFolder();
                            if(!window.__originalFolder||await window.__originalFolder.queryPermission({mode:'readwrite'})!=='granted')throw new Error('Existing benchmark folder permission is unavailable. No picker will be opened.');
                            await new Promise((resolve,reject)=>{const open=indexedDB.open('bulk-proxy-forge-browser',1);open.onsuccess=()=>{
                                const db=open.result,tx=db.transaction('preferences','readwrite');tx.objectStore('preferences').put(window.__originalFolder,'pipelineOriginalFolder');
                                tx.oncomplete=()=>{db.close();resolve();};tx.onerror=()=>reject(tx.error);
                            };open.onerror=()=>reject(open.error);});
                            window.__testFolder=await window.__originalFolder.getDirectoryHandle('Overnight-Pipeline-'+crypto.randomUUID().slice(0,8),{create:true});
                            await storage.useFolder(window.__testFolder);
                        }''')
                    page.goto(origin+'/');page.locator('#import-deck').wait_for(timeout=90000)
                    assert page.evaluate("async()=>(await(await fetch('/api/bootstrap')).json()).storageType")==storage_type
                    page.evaluate("async payload=>{const ui=await import('/site/ui.js');await ui.api('/api/__test__/seed-render-profile',payload);await ui.job('/api/runtime/prepare',{});}",payload)
                    #Balanced warm repetitions plus a separate cold/warmup trial.
                    modes=['serial','serial','yield-stages','yield-draw','yield-timer','yield-timer','yield-draw','yield-stages','serial'] if options.task_yields else ['serial','serial','overlap','overlap-prefetch','overlap-prefetch','overlap','serial']
                    for index,mode in enumerate(modes):
                        print(f'{storage_type}: trial {index} {mode}',flush=True)
                        arguments={'deckId':deck['id'],'mode':mode,'freshSaves':options.fresh_saves}
                        if options.input_latency:
                            page.locator('#deck-search').focus()
                            page.evaluate('arguments=>{window.__pipelineDone=false;window.__pipelineMeasuring=false;window.__pipelinePromise=('+DRIVE+')(arguments).finally(()=>{window.__pipelineDone=true;});window.__pipelinePromise.catch(()=>{});}',arguments)
                            latency=[];deadline=time.monotonic()+300
                            while not page.evaluate('window.__pipelineDone'):
                                if time.monotonic()>deadline:raise TimeoutError('Input-latency trial timed out')
                                if page.evaluate('window.__pipelineMeasuring'):
                                    started=time.perf_counter();page.keyboard.type('x');page.keyboard.press('Backspace');latency.append((time.perf_counter()-started)*1000)
                                time.sleep(.05)
                            row=page.evaluate('window.__pipelinePromise');row['keyboardLatencyMs']=latency
                        else:row=page.evaluate(DRIVE,arguments)
                        row['warmup']=index==0
                        for image in row['images']:
                            raw=base64.b64decode(image.pop('png'));path=evidence/f'{index}-{image["name"].replace("/","_")}.png';path.write_bytes(raw)
                            pixels=Image.open(io.BytesIO(raw)).convert('RGBA')
                            if image['key'] not in references:references[image['key']]=pixels
                            difference=ImageChops.difference(references[image['key']],pixels)
                            image['pixelsIdentical']=not any(channel.getbbox() for channel in difference.split())
                            assert image['pixelsIdentical'],image['name']
                            image['path']=str(path)
                        report['trials'].append(row);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                        print(f'{row["seconds"]:.3f}s, {len(row["images"])} byte-verified exact-pixel PNGs, timer max {row["maxTimerGapMs"]:.1f}ms',flush=True)
                    expected=[{'hash':image['hash']} for image in report['trials'][-1]['images']]
                    page.reload();page.locator('#import-deck').wait_for(timeout=90000)
                    hashes=page.evaluate('''async images=>{
                        const rows=[];for(const image of images){const raw=await(await fetch('/api/assets/'+image.hash)).arrayBuffer();
                        rows.push([...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(byte=>byte.toString(16).padStart(2,'0')).join(''));}return rows;
                    }''',expected)
                    assert hashes==[image['hash'] for image in expected]
                    report['reloadBytesVerified']=True;output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                finally:
                    if options.folder:
                        page.evaluate('''async()=>{
                            const original=await new Promise((resolve,reject)=>{const open=indexedDB.open('bulk-proxy-forge-browser',1);open.onsuccess=()=>{
                                const db=open.result,tx=db.transaction('preferences','readwrite'),request=tx.objectStore('preferences').get('pipelineOriginalFolder');
                                let folder;request.onsuccess=()=>{folder=request.result;tx.objectStore('preferences').delete('pipelineOriginalFolder');};
                                tx.oncomplete=()=>{db.close();resolve(folder);};tx.onerror=()=>reject(tx.error);
                            };open.onerror=()=>reject(open.error);});
                            if(original)await(await import('/web/storage-choice.js')).useFolder(original);
                        }''')
                    page.close()
                    if not options.folder:context.close();browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()