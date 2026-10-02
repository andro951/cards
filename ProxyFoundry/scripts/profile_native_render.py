"""Compare isolated native-render experiments in the production static browser.

Temporary site copies include asset acquisition time and compare decoded PNG
pixels against a delayed two-pass reference. Production asset retention is used
in every variant; the pre-implementation retention results are historical.
"""
import base64
import copy
import functools
import http.server
import io
import json
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from test_website import build_site,copy_site
from test_native_deck import records,artwork as fixture_artwork
from test_v58_station import card as station_card
from foundry.server import App
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants

SEED='''
import time
original_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/cache-state':
        with app.store.connect() as db:rows=[tuple(row) for row in db.execute('SELECT url,asset_id FROM http_cache ORDER BY url')]
        return {'status':200,'mime':'application/json','body':json.dumps(rows).encode(),'headers':{}}
    if str(url)=='/api/__test__/seed-render-profile':
        payload=json.loads(body)
        for image in payload['assets']:
            asset=app.store.add_asset(base64.b64decode(image['bytes']),image['mime'])
            app.runtime_assets.add(asset['id'])
        if payload.get('deck'):app.store.put('decks',payload['deck'])
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
                    rows.append({'batched':batched,'repeat':repeat,'seconds':time.perf_counter()-started,'checkpoints':counter[0],'files':len(frames),'bytes':sum(len(value[0]) for value in replay.values()),'databaseBytes':app.store.db_path.stat().st_size})
        finally:
            app.ws.net.transport=original_transport
            app.store.persist=original_persist
        return {'status':200,'mime':'application/json','body':json.dumps(rows).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
'''

EXPERIMENT='''
  const experiment=new URL(location.href).searchParams.get(`experiment`)||`baseline`;
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
    selected=records() if '--broad' in sys.argv else [r for r in records() if r['name'] in ['Verdant Test','Triome Test','Chronicle Test','Walker Test']]
    station=station_card(colors=['U','R'],pre=True,tiers=2)
    station.update(id='33333333-3333-4333-8333-000000000001',image_uris={'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/profile.jpg'},artist='Fixture Artist',rarity='rare',layout='normal')
    selected.append(station)
    selected.append({**selected[0],'id':'33333333-3333-4333-8333-000000000002','name':'Godzilla Profile'})
    selected.append({'id':'33333333-3333-4333-8333-000000000003','name':'Prepare Profile // Brainstorm','layout':'prepare','rarity':'rare','colors':['U'],'artist':'Fixture Artist','card_faces':[
        {'name':'Prepare Profile','type_line':'Creature — Merfolk Wizard','mana_cost':'{U}','power':'1','toughness':'1','oracle_text':'{T}: This creature becomes prepared.','image_uris':station['image_uris']},
        {'name':'Brainstorm','type_line':'Instant','mana_cost':'{U}','oracle_text':'Draw three cards, then put two cards from your hand on top of your library in any order.'}]})
    original=ROOT.parent/'supernatural/art/syr_gwyn_hero_of_ashvale.png'
    with Image.open(original if original.is_file() else io.BytesIO(fixture_artwork())) as picture:art=picture.convert('RGB').resize((1005,1407) if '--broad' in sys.argv else (2010,2814))
    encoded=io.BytesIO();art.save(encoded,'PNG',compress_level=1);raw=encoded.getvalue()
    art_files={}
    for index,record in enumerate(selected):
        #Distinct content IDs model a deck of different art, not one cached image.
        image=art.copy();image.putpixel((0,0),(index+1,0,0))
        buffer=io.BytesIO();image.save(buffer,'PNG',compress_level=1)
        url=f'https://cards.scryfall.io/art_crop/front/a/b/profile-{index}.png'
        art_files[url]=buffer.getvalue();record['image_uris']={'art_crop':url}
        for face in record.get('card_faces',[]):
            if face.get('image_uris'):face['image_uris']={'art_crop':url}
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
    if '--populated' in sys.argv:
        populated=copy.deepcopy(deck);populated.pop('revision',None);populated['id']=str(uuid.uuid4());populated['name']='Populated benchmark workspace'
        populated['cards']=[copy.deepcopy(deck['cards'][index%len(deck['cards'])]) for index in range(121)]
        for entry in populated['cards']:
            entry['id']=str(uuid.uuid4())
            for face in entry['faces']:face['id']=str(uuid.uuid4())
        payload['deck']=populated
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
        source=source.replace("await measureNative('native.readiness'", "if(![`no-wait`,`combined`].includes(experiment))await sleep(550);\n      await measureNative('native.readiness'")
        source=source.replace("await measureNative('native.first-draw',request.key,async()=>{","if(![`single-draw`,`combined`].includes(experiment))await measureNative('native.first-draw',request.key,async()=>{")
        bridge.write_text(source,encoding='utf-8')
        (evidence/'experimental-bridge.js').write_text(source,encoding='utf-8')
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site))
        folder_mode='--folder' in sys.argv
        if folder_mode:
            import re
            (site/'profile-connect.html').write_text(re.sub(r'<script\b[\s\S]*?</script>','',(site/'index.html').read_text()),encoding='utf-8')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',8769 if folder_mode else 0),handler)
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
                browser=playwright.chromium.launch_persistent_context(str(ROOT/'test-results/selected-folder-profile'),headless=False,viewport={'width':1440,'height':1040}) if folder_mode else playwright.chromium.launch(headless='--headless' in sys.argv)
                page=browser.new_page(viewport={'width':1440,'height':1040}) if not folder_mode else browser.new_page();page.set_default_timeout(180000)
                if folder_mode:
                    for other in browser.pages:
                        if other!=page:other.close()
                page.on('pageerror',lambda error:print('Browser error:',error,flush=True))
                page.on('console',lambda message:print('Browser console:',message.text,flush=True) if message.type=='error' or message.text.startswith('PROFILE') else None)
                current=['baseline']
                page.expose_function('profileRow',lambda row:capture(current[0],row))
                origin=f'http://127.0.0.1:{server.server_port}'
                if folder_mode:
                    page.goto(origin+'/profile-connect.html')
                    page.evaluate('''async()=>{
                        document.body.hidden=false;document.body.replaceChildren();
                        for(const registration of await navigator.serviceWorker.getRegistrations())await registration.unregister();
                        for(const key of await caches.keys())await caches.delete(key);
                        const storage=await import(`/web/storage-choice.js`);let folder=await storage.savedFolder();
                        const connect=async()=>{const child=await folder.getDirectoryHandle(`BulkProxyForge-Native-Benchmark-${crypto.randomUUID().slice(0,8)}`,{create:true});await storage.useFolder(child);window.connected=true;};
                        try{if(folder&&await folder.queryPermission({mode:`readwrite`})===`granted`){await connect();return;}}catch(error){folder=null;}
                        const button=document.createElement(`button`);button.textContent=`Allow benchmark folder access`;
                        button.onclick=async()=>{
                            try{if(!folder)folder=await window.showDirectoryPicker({mode:`readwrite`,startIn:`documents`});
                                if(await folder.requestPermission({mode:`readwrite`})===`granted`)await connect();
                            }catch(error){folder=null;button.textContent=`Allow benchmark folder access`;}
                        };document.body.append(button);
                    }''')
                    if not page.evaluate('Boolean(window.connected)'):
                        print('Awaiting existing benchmark folder permission.',flush=True);page.get_by_role('button',name='Allow benchmark folder access').click();page.wait_for_function('window.connected',timeout=900000)
                page.goto(origin+'/')
                try:page.locator('#import-deck').wait_for(timeout=90000)
                except Exception:
                    print('Startup page:',page.locator('body').inner_text(),flush=True)
                    browser.close();raise
                storage_type=page.evaluate('''async()=> (await (await fetch(`/api/bootstrap`)).json()).storageType''')
                assert storage_type==('selected-folder' if folder_mode else 'browser'),storage_type
                page.evaluate('''async payload=>{const response=await fetch(`/api/__test__/seed-render-profile`,{method:`POST`,headers:{'Content-Type':`application/json`},body:JSON.stringify(payload)});if(!response.ok)throw new Error(await response.text());}''',payload)
                page.evaluate('''async()=>{const ui=await import(`/site/ui.js`);await ui.job(`/api/runtime/prepare`,{}, {label:`Profile dependencies`});}''')
                experiments=[] if '--cache-only' in sys.argv else ['baseline','no-wait'] if '--readiness-only' in sys.argv else ['baseline','reuse-scripts'] if '--scripts-only' in sys.argv else ['baseline','no-wait','single-draw','combined','reuse-scripts']
                for experiment in experiments:
                    print('Running',experiment,flush=True)
                    current[0]=experiment
                    results=page.evaluate(DRIVE,{'data':data,'experiment':experiment,'rounds':2})
                    results=report[experiment]
                    (evidence/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(experiment,'seconds',round(sum(r['seconds'] for r in results),3),'identical',sum(r['pixelsIdentical'] for r in results),'/',len(results),flush=True)
                    if '--verify' in sys.argv:
                        assert all(row['pixelsIdentical'] for row in results),[(row['name'],row['round']) for row in results if not row['pixelsIdentical']]
                paths=list(dict.fromkeys(frame['src'] for item in data for frame in item['data']['frames']))
                report['frame-cache-persistence']=page.evaluate('''async paths=>{const response=await fetch(`/api/__test__/frame-cache-profile`,{method:`POST`,headers:{'Content-Type':`application/json`},body:JSON.stringify({paths})});if(!response.ok)throw new Error(await response.text());return response.json();}''',paths)
                if folder_mode:
                    before=page.evaluate('''async()=> (await (await fetch(`/api/__test__/cache-state`)).json())''')
                    persisted=page.evaluate('''async()=>{
                        const {savedFolder}=await import(`/web/storage-choice.js`);const folder=await savedFolder();
                        const file=await (await folder.getFileHandle(`workspace.sqlite3`)).getFile();
                        return {folder:folder.name,databaseBytes:file.size};
                    }''')
                    page.reload();page.locator('#import-deck').wait_for(timeout=90000)
                    after=page.evaluate('''async()=> (await (await fetch(`/api/__test__/cache-state`)).json())''')
                    assert before==after,(before,after)
                    report['folder-durability']={**persisted,'cacheEntries':len(after),'reloadMatches':True}
                target=evidence/(f'cache-{storage_type}-populated.json' if '--cache-only' in sys.argv and '--populated' in sys.argv else 'cache-results.json' if '--cache-only' in sys.argv else 'results.json')
                target.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print('Cache persistence:',report['frame-cache-persistence'],flush=True)
                browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
