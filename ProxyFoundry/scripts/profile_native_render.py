"""Compare isolated native-render experiments in the production static browser.

No product renderer is modified. Every experiment includes its asset acquisition
time and compares decoded PNG pixels against two unmodified reference passes.
"""
import base64
import functools
import http.server
import io
import json
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from test_website import build_site,copy_site
from test_native_deck import records
from test_v58_station import card as station_card
from foundry.server import App
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants

SEED='''
import time
original_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/seed-render-profile':
        payload=json.loads(body)
        for image in payload['assets']:
            asset=app.store.add_asset(base64.b64decode(image['bytes']),image['mime'])
            app.runtime_assets.add(asset['id'])
        return {'status':200,'mime':'application/json','body':b'{}','headers':{}}
    if str(url)=='/api/__test__/frame-cache-profile':
        from contextlib import nullcontext
        frames=[]
        for path in json.loads(body)['paths']:
            if path.startswith('/img/frames/') and path.endswith('.png') and not path.endswith('Thumb.png'):
                raw,mime=app.runtime.fetch(path)
                frames.append((raw,mime))
                if len(frames)==10:break
        rows=[]
        original_transport=app.ws.net.transport
        original_persist=app.store.persist
        counter=[0]
        def persist(path):
            counter[0]+=1
            return original_persist(path)
        app.store.persist=persist
        try:
            for repeat in range(3):
                for batched in [False,True]:
                    nonce=uuid.uuid4().hex
                    replay={f'https://raw.githubusercontent.com/profile/{nonce}/{index}.png':(raw+nonce.encode(),mime,{}) for index,(raw,mime) in enumerate(frames)}
                    app.ws.net.transport=lambda url:replay[url]
                    counter[0]=0;started=time.perf_counter()
                    with app.store.render_save() if batched else nullcontext():
                        for url in replay:app.ws.net.fetch(url,immutable=True)
                    rows.append({'batched':batched,'repeat':repeat,'seconds':time.perf_counter()-started,'checkpoints':counter[0],'files':len(frames),'bytes':sum(len(value[0]) for value in replay.values())})
        finally:
            app.ws.net.transport=original_transport
            app.store.persist=original_persist
        return {'status':200,'mime':'application/json','body':json.dumps(rows).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
'''

EXPERIMENT='''
  const experiment=new URL(location.href).searchParams.get(`experiment`)||`baseline`;
  const retainedAssets=new Map();
  async function retainAssets(data){
    const started=performance.now();
    //Read each card's artwork again so shared fixture art cannot inflate savings.
    if(retainedAssets.has(data.artSource)){
      URL.revokeObjectURL(retainedAssets.get(data.artSource));retainedAssets.delete(data.artSource);
    }
    const paths=new Set([data.artSource,data.setSymbolSource,data.watermarkSource]);
    for(const frame of data.frames||[]){
      paths.add(frame.src);
      for(const mask of frame.masks||[])paths.add(mask.src);
    }
    await Promise.all([...paths].filter(path=>path?.startsWith(`/`)).map(async path=>{
      if(retainedAssets.has(path))return;
      const response=await fetch(path);
      if(!response.ok)throw new Error(`Asset retention failed: ${path}`);
      retainedAssets.set(path,URL.createObjectURL(await response.blob()));
    }));
    for(const name of [`artSource`,`setSymbolSource`,`watermarkSource`]){
      if(retainedAssets.has(data[name]))data[name]=retainedAssets.get(data[name]);
    }
    for(const frame of data.frames||[]){
      frame.src=retainedAssets.get(frame.src)||frame.src;
      for(const mask of frame.masks||[])mask.src=retainedAssets.get(mask.src)||mask.src;
    }
    post(`diagnostic`,{stage:`timing`,diagnostic:{stage:`experiment.retain-assets`,seconds:(performance.now()-started)/1000}});
  }
'''

DRIVE='''async ({data,experiment,rounds})=>{
    const frame=document.createElement(`iframe`);
    frame.className=`render-frame`;
    frame.setAttribute(`sandbox`,`allow-scripts allow-same-origin`);
    frame.src=`/runtime/host?parent=${encodeURIComponent(location.origin)}&owner=${encodeURIComponent(window.__pfOwner)}&experiment=${experiment}`;
    document.body.append(frame);
    const results=[];
    let resolveReady,rejectReady,pending=null;
    const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
    const listener=event=>{
      if(event.source!==frame.contentWindow||event.data?.source!==`pf-native-runtime`)return;
      const message=event.data;
      if(message.type===`ready`)resolveReady();
      if(message.type===`failed`){
        const error=new Error(message.error);
        if(pending)pending.reject(error);else rejectReady(error);
      }
      if(message.type===`diagnostic`&&pending&&message.stage===`timing`)pending.stages.push(message.diagnostic);
      if(message.type===`rendered`&&pending)pending.resolve(message.blob);
    };
    window.addEventListener(`message`,listener);
    const timer=setInterval(()=>frame.contentWindow?.postMessage({source:`pf-app`,type:`ping`},location.origin),500);
    const deadline=setTimeout(()=>{
      const native=frame.contentWindow;
      const error=new Error(`Profile renderer timed out: ${experiment} ${JSON.stringify({runtime:!!native.__PF_RUNTIME,errors:native.__PF_RUNTIME?.errors,phase:native.__PF_RUNTIME?.phase,loadCard:typeof native.loadCard,frames:native.availableFrames?.length,version:native.card?.version,body:native.document.body.innerText.slice(0,300)})}`);
      if(pending)pending.reject(error);else rejectReady(error);
    },600000);
    try{
      await ready;clearInterval(timer);
      for(let round=0;round<rounds;round++){
        for(let index=0;index<data.length;index++){
          const started=performance.now();
          const blob=await new Promise((resolve,reject)=>{
            pending={resolve,reject,stages:[]};
            frame.contentWindow.postMessage({source:`pf-app`,type:`render`,key:`profile-${round}-${index}`,data:data[index].data},location.origin);
          });
          const seconds=(performance.now()-started)/1000;
          const png=await new Promise(resolve=>{
            const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(`,`)[1]);reader.readAsDataURL(blob);
          });
          results.push({name:data[index].name,round,seconds,stages:pending.stages,png});
          await window.profileRow(results[results.length-1]);
          delete results[results.length-1].png;
          console.log(`PROFILE ${experiment} ${round} ${data[index].name}: ${seconds.toFixed(3)}s`);
          pending=null;
        }
      }
      return results;
    }finally{
      clearTimeout(deadline);clearInterval(timer);window.removeEventListener(`message`,listener);frame.remove();
    }
}'''

def fixtures(tmp):
    selected=[r for r in records() if r['name'] in ['Verdant Test','Triome Test','Chronicle Test','Walker Test']]
    station=station_card(colors=['U','R'],pre=True,tiers=2)
    station.update(id='33333333-3333-4333-8333-000000000001',image_uris={'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/profile.jpg'},artist='Fixture Artist',rarity='rare',layout='normal')
    selected.append(station)
    selected.append({**selected[0],'id':'33333333-3333-4333-8333-000000000002','name':'Godzilla Profile'})
    selected.append({'id':'33333333-3333-4333-8333-000000000003','name':'Prepare Profile // Brainstorm','layout':'prepare','rarity':'rare','colors':['U'],'artist':'Fixture Artist','card_faces':[
        {'name':'Prepare Profile','type_line':'Creature — Merfolk Wizard','mana_cost':'{U}','power':'1','toughness':'1','oracle_text':'{T}: This creature becomes prepared.','image_uris':station['image_uris']},
        {'name':'Brainstorm','type_line':'Instant','mana_cost':'{U}','oracle_text':'Draw three cards, then put two cards from your hand on top of your library in any order.'}]})
    original=ROOT.parent/'supernatural/art/syr_gwyn_hero_of_ashvale.png'
    with Image.open(original) as picture:art=picture.convert('RGB').resize((2010,2814))
    encoded=io.BytesIO();art.save(encoded,'PNG',compress_level=1);raw=encoded.getvalue()
    art_files={}
    for index,record in enumerate(selected):
        #Distinct content IDs model a deck of different art, not one cached image.
        image=art.copy();image.putpixel((0,0),(index+1,0,0))
        buffer=io.BytesIO();image.save(buffer,'PNG',compress_level=1)
        url=f'https://cards.scryfall.io/art_crop/front/a/b/profile-{index}.png'
        art_files[url]=buffer.getvalue();record['image_uris']={'art_crop':url}
        if record.get('card_faces'):record['card_faces'][0]['image_uris']={'art_crop':url}
    store=Store(tmp/'fixture-workspace');net=Network(store);byid={r['id']:r for r in selected}
    def transport(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(byid[url.rsplit('/',1)[-1]]).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return art_files[url],'image/png',{}
        raise RuntimeError('Unexpected fixture network request: '+url)
    net.transport=transport;app=App(store,net);asset=ingest_image(store,raw)
    symbol_bytes=io.BytesIO();art.resize((100,100)).save(symbol_bytes,'PNG')
    symbol=ingest_image(store,symbol_bytes.getvalue())
    deck=app.ws.create({'name':'Render profile','source':[{'id':r['id']} for r in selected],'settings':{'symbols':rarity_variants(store,symbol['id']),'backAsset':asset['id']}})
    for entry in deck['cards']:
        if entry['name']=='Godzilla Profile':entry['faces'][0]['templateOverride']='godzilla-card'
    store.put('decks',deck,deck['revision'])
    deck=app.ws.prepare(deck['id'])
    data=[];assets=set()
    for entry in deck['cards']:
        for face in entry['faces']:
            assert not face.get('error'),face
            compiled=face['compiled'];data.append({'name':face['name'],'data':compiled['data']})
            assets.update([compiled['artId'],compiled['symbolId']])
    payload={'assets':[{'mime':store.asset(ident)['mime'],'bytes':base64.b64encode(store.asset_path(ident).read_bytes()).decode()} for ident in assets]}
    for handler in app.log.handlers:
        handler.close()
    return data,payload

def main():
    evidence=ROOT/'test-results/native-profile';evidence.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bpf-native-profile-') as temporary:
        tmp=Path(temporary);data,payload=fixtures(tmp);build_site(tmp);site=copy_site(tmp)
        worker=site/'web/engine-worker.js'
        worker.write_text(worker.read_text().replace('def browser_request(method, url, body, headers):',SEED+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
        bridge=site/'site/runtime-bridge.js';source=bridge.read_text()
        source=source.replace('const pendingScripts=new Set();','const pendingScripts=new Set();\n'+EXPERIMENT)
        source=source.replace('loadedScripts.delete(path);','if(experiment!==`reuse-scripts`)loadedScripts.delete(path);')
        source=source.replace("if(seconds>=.1)post",'if(true)post')
        source=source.replace("await measureNative('native.assets',request.key,()=>preload(data));","if([`retained-assets`,`combined`].includes(experiment))await retainAssets(data);\n      await measureNative('native.assets',request.key,()=>preload(data));")
        source=source.replace("()=>sleep(550)","()=>sleep([`no-wait`,`combined`].includes(experiment)?0:550)")
        source=source.replace("await measureNative('native.first-draw',request.key,async()=>{","if(![`single-draw`,`combined`].includes(experiment))await measureNative('native.first-draw',request.key,async()=>{")
        bridge.write_text(source,encoding='utf-8')
        (evidence/'experimental-bridge.js').write_text(source,encoding='utf-8')
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site))
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        report={};references={}
        def capture(experiment,row):
            png=base64.b64decode(row.pop('png'));image=Image.open(io.BytesIO(png)).convert('RGBA')
            name=row['name'];index=[d['name'] for d in data].index(name)
            path=evidence/f'{experiment}-{row["round"]}-{index}.png';path.write_bytes(png)
            if experiment=='baseline' and row['round']==0:references[name]=image
            if name in references:
                delta=ImageChops.difference(references[name],image)
                row['pixelsIdentical']=not any(channel.getbbox() for channel in delta.split())
            row['png']=str(path);report.setdefault(experiment,[]).append(row)
            if experiment=='baseline' and row['round']==1:references[name]=image
            (evidence/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless='--headless' in sys.argv)
                page=browser.new_page(viewport={'width':1440,'height':1040});page.set_default_timeout(180000)
                page.on('pageerror',lambda error:print('Browser error:',error,flush=True))
                page.on('console',lambda message:print('Browser console:',message.text,flush=True) if message.type=='error' or message.text.startswith('PROFILE') else None)
                current=['baseline']
                page.expose_function('profileRow',lambda row:capture(current[0],row))
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.locator('#import-deck').wait_for(timeout=90000)
                page.evaluate('''async payload=>{const response=await fetch(`/api/__test__/seed-render-profile`,{method:`POST`,headers:{'Content-Type':`application/json`},body:JSON.stringify(payload)});if(!response.ok)throw new Error(await response.text());}''',payload)
                page.evaluate('''async()=>{const ui=await import(`/site/ui.js`);await ui.job(`/api/runtime/prepare`,{}, {label:`Profile dependencies`});}''')
                experiments=[] if '--cache-only' in sys.argv else ['baseline','reuse-scripts'] if '--scripts-only' in sys.argv else ['baseline','retained-assets','no-wait','single-draw','combined','reuse-scripts']
                for experiment in experiments:
                    print('Running',experiment,flush=True)
                    current[0]=experiment
                    results=page.evaluate(DRIVE,{'data':data,'experiment':experiment,'rounds':2})
                    results=report[experiment]
                    (evidence/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(experiment,'seconds',round(sum(r['seconds'] for r in results),3),'identical',sum(r['pixelsIdentical'] for r in results),'/',len(results),flush=True)
                paths=list(dict.fromkeys(frame['src'] for item in data for frame in item['data']['frames']))
                report['frame-cache-persistence']=page.evaluate('''async paths=>{const response=await fetch(`/api/__test__/frame-cache-profile`,{method:`POST`,headers:{'Content-Type':`application/json`},body:JSON.stringify({paths})});if(!response.ok)throw new Error(await response.text());return response.json();}''',paths)
                target=evidence/('cache-results.json' if '--cache-only' in sys.argv else 'results.json')
                target.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print('Cache persistence:',report['frame-cache-persistence'],flush=True)
                browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
