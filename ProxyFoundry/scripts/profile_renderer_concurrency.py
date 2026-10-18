"""Measure one/two/three pinned native iframes without changing production.

Each iframe is primed with every structural face before measurement. PNG saves,
bootstrap, priming and result encoding are excluded from native throughput.
"""
import argparse,base64,functools,http.server,io,json,subprocess,sys,tempfile,threading,time
from pathlib import Path
from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from profile_native_render import fixtures,SEED
from foundry.storage import Store
from test_website import build_site,copy_site

DRIVE='''async({deckId,count})=>{
    const ui=await import(`/site/ui.js`),plan=await ui.api(`/api/render-sessions`,{deckIds:[deckId],force:true});
    if(plan.errors.length)throw new Error(plan.errors.join(`\n`));
    const targets=[],workers=[];
    for(const target of plan.targets)targets.push({...target,...await ui.api(`/api/render-sessions/${plan.id}/${target.key}`)});
    const wait=(promise,ms)=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(`Native benchmark timeout`)),ms);promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});
    const create=async()=>{
        const frame=document.createElement(`iframe`);frame.className=`render-frame`;frame.setAttribute(`sandbox`,`allow-scripts allow-same-origin`);
        frame.src=`/runtime/host?parent=${encodeURIComponent(location.origin)}&owner=${encodeURIComponent(window.__pfOwner)}`;document.body.append(frame);
        let ready,pending=null;const readyPromise=new Promise(resolve=>{ready=resolve;});
        const listener=event=>{
            if(event.source!==frame.contentWindow||event.origin!==location.origin||event.data?.source!==`pf-native-runtime`)return;
            const data=event.data;
            if(data.type===`ready`)ready();
            if(data.type===`rendered`&&pending){const next=pending;pending=null;next.resolve(data);}
            if(data.type===`failed`&&pending){const next=pending;pending=null;next.reject(new Error(data.error));}
        };
        window.addEventListener(`message`,listener);
        const worker={frame,listener,render:target=>wait(new Promise((resolve,reject)=>{pending={resolve,reject};frame.contentWindow.postMessage({source:`pf-app`,type:`render`,data:target.data,key:target.key},location.origin);}),90000)};
        workers.push(worker);
        const ping=setInterval(()=>frame.contentWindow.postMessage({source:`pf-app`,type:`ping`},location.origin),200);
        try{await wait(readyPromise,90000);}finally{clearInterval(ping);}
        return worker;
    };
    let timer=null,observer=null;
    try{
        for(let index=0;index<count;index++)await create();
        //Warm every face in every iframe so distribution does not bias asset caches.
        for(const worker of workers)for(const target of targets)await worker.render(target);
        const tasks=[],gaps=[];let last=performance.now();
        observer=new PerformanceObserver(list=>{for(const entry of list.getEntries())tasks.push({milliseconds:entry.duration,attribution:entry.attribution.map(a=>({containerType:a.containerType,containerSrc:a.containerSrc}))});});
        observer.observe({type:`longtask`});timer=setInterval(()=>{const now=performance.now();gaps.push(now-last);last=now;},16);
        const started=performance.now(),outputs=new Array(targets.length);let next=0;
        await Promise.all(workers.map(async worker=>{while(next<targets.length){const index=next++;outputs[index]=await worker.render(targets[index]);}}));
        const seconds=(performance.now()-started)/1000;
        clearInterval(timer);observer.disconnect();
        const canvases=workers.map(worker=>{
            const win=worker.frame.contentWindow,found=new Set(win.document.querySelectorAll(`canvas`));
            //The native core also owns detached canvas surfaces in globals.
            for(const key of Object.getOwnPropertyNames(win))try{if(win[key] instanceof win.HTMLCanvasElement)found.add(win[key]);}catch{}
            return [...found].map(c=>({width:c.width,height:c.height}));
        });
        const images=[];
        for(let index=0;index<outputs.length;index++){
            const output=outputs[index],blob=output.blob||new Blob([output.buffer],{type:`image/png`});
            const png=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(`,`)[1]);reader.readAsDataURL(blob);});
            images.push({name:targets[index].name||String(index),key:targets[index].key,png});
        }
        return {count,seconds,faces:targets.length,maxTimerGapMs:Math.max(0,...gaps),maxLongTaskMs:Math.max(0,...tasks.map(t=>t.milliseconds)),longTaskMs:tasks.reduce((sum,t)=>sum+t.milliseconds,0),tasks,canvases,
            canvasPixelBytes:canvases.flat().reduce((sum,c)=>sum+c.width*c.height*4,0),usedJsHeapBytes:performance.memory?.usedJSHeapSize||null,images};
    }finally{
        clearInterval(timer);observer?.disconnect();
        for(const worker of workers){window.removeEventListener(`message`,worker.listener);worker.frame.contentWindow.postMessage({source:`pf-app`,type:`dispose`},location.origin);worker.frame.remove();}
    }
}'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/renderer-concurrency/results.json')
    parser.add_argument('--headless',action='store_true')
    args=parser.parse_args();evidence=args.output.parent;evidence.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pf-renderer-concurrency-') as temporary:
        tmp=Path(temporary);_,payload=fixtures(tmp)
        store=Store(tmp/'fixture-workspace');deck=store.list('decks')[0];deck.pop('revision',None);payload['deck']=deck
        back=deck['settings']['backAsset'];asset=store.asset(back)
        payload['assets'].append({'mime':asset['mime'],'bytes':base64.b64encode(store.asset_path(back).read_bytes()).decode()})
        build_site(tmp);site=copy_site(tmp)
        worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8');anchor='def browser_request(method, url, body, headers):'
        assert source.count(anchor)==1;worker.write_text(source.replace(anchor,SEED+'\n'+anchor),encoding='utf-8')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        report={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'at':time.time(),
            'note':'Warm native rendering only. Every iframe primed with every face. No save throughput claim. Canvas bytes estimate pixel surfaces, not total renderer/GPU memory. JS heap is not native canvas memory.','trials':[]};references={}
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=args.headless)
                try:
                    page=browser.new_page();page.set_default_timeout(600000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:'+str(server.server_port));page.locator('#import-deck').wait_for(timeout=120000)
                    page.evaluate("async payload=>{const ui=await import('/site/ui.js');await ui.api('/api/__test__/seed-render-profile',payload);await ui.job('/api/runtime/prepare',{});}",payload)
                    report['workerCompatibility']=page.evaluate(r'''async()=>{
                        const response=await fetch(`/js/creator-23.js`);if(!response.ok)throw new Error(`Native source unavailable`);
                        const source=await response.text();
                        const code=`try{eval(${JSON.stringify(source)});postMessage({loaded:true});}catch(error){postMessage({loaded:false,error:error.name+': '+error.message,documentAvailable:typeof document!==\`undefined\`,windowAvailable:typeof window!==\`undefined\`,offscreenCanvasAvailable:typeof OffscreenCanvas!==\`undefined\`});}`;
                        const url=URL.createObjectURL(new Blob([code],{type:`text/javascript`}));const worker=new Worker(url);
                        try{return await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(`Worker probe timeout`)),10000);worker.onmessage=event=>{clearTimeout(timer);resolve(event.data);};worker.onerror=error=>{clearTimeout(timer);reject(new Error(error.message));};});}
                        finally{worker.terminate();URL.revokeObjectURL(url);}
                    }''')
                    for index,count in enumerate([1,2,3,3,2,1]):
                        print('Trial',index,'renderers',count,flush=True)
                        row=page.evaluate(DRIVE,{'deckId':payload['deck']['id'],'count':count})
                        for image in row['images']:
                            raw=base64.b64decode(image.pop('png'));pixels=Image.open(io.BytesIO(raw)).convert('RGBA');key=image['key']
                            if key in references:assert all(channel.getbbox() is None for channel in ImageChops.difference(references[key],pixels).split()),image['name']
                            else:references[key]=pixels.copy()
                            image['pixelsIdentical']=True;(evidence/(str(index)+'-'+str(len(row['images']))+'-'+key[:10]+'.png')).write_bytes(raw)
                        report['trials'].append(row);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                        print(json.dumps({key:row[key] for key in ('count','seconds','maxTimerGapMs','maxLongTaskMs','canvasPixelBytes')}),flush=True)
                    assert not errors,errors
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()