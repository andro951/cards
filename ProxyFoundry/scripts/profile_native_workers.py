"""Compare dedicated native workers with the original DOM native renderer."""
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
from scripts.profile_native_render import fixtures,SEED,DRIVE
from tests.test_website import build_site,copy_site


def main():
    evidence=ROOT/'test-results/native-workers';evidence.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bpf-native-workers-') as temporary:
        tmp=Path(temporary)
        fixture=evidence/'fixture.json'
        if fixture.is_file():
            saved=json.loads(fixture.read_text(encoding='utf-8'));data,payload=saved['data'],saved['payload']
        else:
            data,payload=fixtures(tmp);fixture.write_text(json.dumps({'data':data,'payload':payload}),encoding='utf-8')
        build_site(tmp);site=copy_site(tmp)
        worker=site/'web/engine-worker.js'
        worker.write_text(worker.read_text(encoding='utf-8').replace('def browser_request(method, url, body, headers):',SEED+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        if '--local' in sys.argv:
            from foundry.storage import Store
            from foundry.server import App,LocalServer
            store=Store(ROOT/'test-results/worker-source-cache');app=App(store)
            for image in payload['assets']:
                asset=store.add_asset(base64.b64decode(image['bytes']),image['mime']);app.runtime_assets.add(asset['id'])
            server=LocalServer(app,0)
        else:server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        results={};references={}
        def capture(mode,row):
            raw=base64.b64decode(row.pop('png'));picture=Image.open(io.BytesIO(raw)).convert('RGBA')
            path=evidence/(mode+'-'+str(row['round'])+'-'+str([d['name'] for d in data].index(row['name']))+'.png');path.write_bytes(raw)
            if mode=='dom':references[row['name']]=picture
            reference=references.get(row['name'])
            assert reference is not None,'Missing serial reference for '+row['name']
            difference=ImageChops.difference(reference,picture)
            channels=difference.split();maximum=channels[0]
            for channel in channels[1:]:maximum=ImageChops.lighter(maximum,channel)
            histogram=maximum.histogram();pixels=picture.width*picture.height
            row['pixelsIdentical']=histogram[0]==pixels
            row['changedFraction']=sum(histogram[1:])/pixels
            row['visibleDifferenceFraction']=sum(histogram[5:])/pixels
            row['maximumChannelDifference']=max(index for index,count in enumerate(histogram) if count)
            row['png']=str(path);results.setdefault(mode,[]).append(row)
            print(mode,row['name'],round(row['seconds'],3),'identical',row['pixelsIdentical'],flush=True)
            (evidence/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=False,args=['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']);page=browser.new_page();page.set_default_timeout(180000)
                page.on('pageerror',lambda error:print('Browser error:',error,flush=True))
                page.on('console',lambda message:print(message.text,flush=True) if message.type=='error' else None)
                mode=['dom'];page.expose_function('profileRow',lambda row:capture(mode[0],row))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#import-deck').wait_for(timeout=120000)
                if '--local' not in sys.argv:page.evaluate('''async payload=>{const {api,job}=await import('/site/ui.js');await api('/api/__test__/seed-render-profile',payload);await job('/api/runtime/prepare',{});}''',payload)
                variants=['worker'] if '--worker-only' in sys.argv else ['dom','worker']
                if '--worker-only' in sys.argv:
                    for index,item in enumerate(data):
                        path=evidence/f'dom-0-{index}.png'
                        if path.is_file():references[item['name']]=Image.open(path).convert('RGBA')
                for variant in variants:
                    mode[0]=variant
                    driver=DRIVE.replace('&experiment=${experiment}', '&experiment=${experiment}&worker=1' if variant=='worker' else '&experiment=${experiment}')
                    driver=driver.replace('new Error(message.error)','new Error(message.error+JSON.stringify(message.errors||[]))')
                    if '--local' in sys.argv:driver=driver.replace('frame.src=`/runtime/host?', 'frame.src=`'+app.runtime_origin+'/runtime/host?').replace(',location.origin)',',`'+app.runtime_origin+'`)')
                    page.evaluate(driver,{'data':data[:1] if '--one' in sys.argv else data,'experiment':variant,'rounds':1})
                browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
            if '--local' in sys.argv:app.close()
        #HTMLImage and ImageBitmap alpha interpolation differ by a few channel levels
        #on transparent edges; reject layout/text changes and widespread visual drift.
        assert all(row['changedFraction']<.05 and row['visibleDifferenceFraction']<.001 for row in results['worker']),results['worker']


if __name__=='__main__':main()
