"""Profile the real static browser save path without modifying product source."""
import functools
import hashlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_website import build_site,copy_site

EXPERIMENT='''
if profile_variant in ('direct-render','combined'):
    import inspect,textwrap
    import foundry.storage as storage_module
    source=textwrap.dedent(inspect.getsource(storage_module.Store.render_put))
    source=source.replace("temp=output.with_name('.'+output.name+'.'+uid()+'.tmp')","temp=output")
    source=source.replace('os.replace(temp,output)','pass')
    source=source.replace('temp.unlink(missing_ok=True)','pass')
    exec(source,storage_module.__dict__)
    storage_module.Store.render_put=storage_module.render_put
profile_checkpoint=app.store.checkpoint
profile_hold=False
def experiment_checkpoint():
    if not profile_hold:profile_checkpoint()
app.store.checkpoint=experiment_checkpoint
'''

PYTHON_PROFILE='''
import time
import foundry.timing as timing_module
save_profile=[]
original_timing=timing_module.record_timing
def profile_timing(store,stage,started,outcome='ok',**details):
    save_profile.append({'stage':stage,'seconds':time.perf_counter()-started})
    original_timing(store,stage,started,outcome,**details)
timing_module.record_timing=profile_timing
original_buffer_bytes=buffer_bytes
def buffer_bytes(buffer):
    started=time.perf_counter()
    result=original_buffer_bytes(buffer)
    save_profile.append({'stage':'input.buffer-to-python','seconds':time.perf_counter()-started})
    return result
original_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/profile-save':
        target={'key':uuid.uuid4().hex,'name':'Profile '+uuid.uuid4().hex}
        started=time.perf_counter()
        result=app.ws.save_render(target,body,[2010,2814])
        elapsed=time.perf_counter()-started
        return {'status':200,'mime':'application/json','body':json.dumps({'seconds':elapsed,'asset':result['asset_id']}).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
'''

JS_PROFILE='''
let saveProfileActive=false;
let saveFileCalls=[];
const originalSend=XMLHttpRequest.prototype.send;
const originalOpen=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url,...rest){
    this.profileUrl=String(url);
    return originalOpen.call(this,method,url,...rest);
};
XMLHttpRequest.prototype.send=function(body){
    const started=performance.now();
    try{return originalSend.call(this,body);}
    finally{
        if(saveProfileActive){
            const url=new URL(this.profileUrl,location.origin);
            saveFileCalls.push({operation:url.searchParams.get(`operation`),path:url.searchParams.get(`path`),seconds:(performance.now()-started)/1000,bytes:body?.byteLength||0});
        }
    }
};
'''

def main():
    folder_mode=len(sys.argv)>1
    variant=os.environ.get('PF_SAVE_VARIANT','baseline')
    assert variant in ('baseline','direct-render','single-checkpoint','combined')
    with tempfile.TemporaryDirectory(prefix='bpf-save-profile-') as temporary:
        tmp=Path(temporary);build_site(tmp);site=copy_site(tmp)
        review=ROOT/'test-results/supernatural-full-art/syr_gwyn_hero_of_ashvale_review.png'
        with Image.open(review) as image:canvas=image.crop((2011,0,4021,2814))
        png=io.BytesIO();canvas.save(png,'PNG',compress_level=1)
        (site/'profile.png').write_bytes(png.getvalue())
        worker=site/'web/engine-worker.js'
        source=worker.read_text(encoding='utf-8')
        injected=PYTHON_PROFILE
        if variant!='baseline':
            injected=injected.replace('original_request=request',f'profile_variant={variant!r}\n'+EXPERIMENT+'\noriginal_request=request')
            injected=injected.replace('result=app.ws.save_render(target,body,[2010,2814])',"global profile_hold\n        profile_hold=profile_variant in ('single-checkpoint','combined')\n        try:result=app.ws.save_render(target,body,[2010,2814])\n        finally:profile_hold=False")
        source=source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):')
        source=source.replace('let initialized=false;','let initialized=false;\n'+JS_PROFILE)
        source=source.replace("invoke=python.globals.get('browser_request');", "saveProfileActive=url==='/api/__test__/profile-save';saveFileCalls=[];if(saveProfileActive)python.runPython('save_profile.clear()');\n    invoke=python.globals.get('browser_request');")
        source=source.replace("self.postMessage({type:'response',id,...metadata,body:responseBody}", "if(saveProfileActive){const result=JSON.parse(responseBody);result.profile=JSON.parse(python.runPython('json.dumps(save_profile)'));result.fileCalls=saveFileCalls;responseBody=JSON.stringify(result);saveProfileActive=false;}\n    self.postMessage({type:'response',id,...metadata,body:responseBody}")
        worker.write_text(source,encoding='utf-8')
        bootstrap=site/'web/bootstrap.js'
        source=bootstrap.read_text(encoding='utf-8').replace('const pending=new Map();','''
  window.saveStorageProfile=[];
  const originalExecute=files.execute;
  files.execute=async(...args)=>{
    const started=performance.now();
    try{return await originalExecute(...args);}
    finally{window.saveStorageProfile.push({operation:args[0],path:args[1],seconds:(performance.now()-started)/1000});}
  };
  const pending=new Map();''')
        bootstrap.write_text(source,encoding='utf-8')
        (site/'profile-connect.html').write_text('',encoding='utf-8')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',8769 if folder_mode else 0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as playwright:
                browser=None
                if folder_mode:context=playwright.chromium.launch_persistent_context(str(ROOT/'test-results/selected-folder-profile'),headless=False)
                else:
                    browser=playwright.chromium.launch();context=browser.new_context()
                try:
                    origin='http://127.0.0.1:'+str(server.server_port)
                    page=context.new_page()
                    page.on('pageerror',lambda error:print('Page error:',error,flush=True))
                    disk_folder=None
                    if folder_mode:
                        page.goto(origin+'/profile-connect.html')
                        name='profile-'+uuid.uuid4().hex[:8]
                        page.evaluate('''async name=>{
                            const storage=await import(`/web/storage-choice.js`);
                            const folder=await storage.savedFolder();
                            if(!folder)throw new Error(`No previously selected benchmark folder.`);
                            const connect=async()=>{
                                const child=await folder.getDirectoryHandle(name,{create:true});
                                await storage.useFolder(child);window.connected=true;
                            };
                            if(await folder.queryPermission({mode:`readwrite`})===`granted`)await connect();
                            else{
                                const button=document.createElement(`button`);
                                button.textContent=`Allow benchmark folder access`;
                                button.onclick=async()=>{
                                    if(await folder.requestPermission({mode:`readwrite`})===`granted`)await connect();
                                };
                                document.body.append(button);
                            }
                        }''',name)
                        if not page.evaluate('Boolean(window.connected)'):
                            print('Awaiting existing benchmark folder permission.',flush=True)
                            page.get_by_role('button').click()
                            page.wait_for_function('window.connected',timeout=900000)
                        disk_folder=Path(sys.argv[1])/name
                    page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
                    storage_type=page.evaluate("async()=> (await (await fetch('/api/bootstrap')).json()).storageType")
                    assert storage_type==('selected-folder' if folder_mode else 'browser'),storage_type
                    runs=page.evaluate('''async()=>{
                        const png=await (await fetch(`/profile.png`)).blob();
                        const runs=[];
                        for(let index=0;index<3;index++){
                            if(window.saveStorageProfile)window.saveStorageProfile=[];
                            const started=performance.now();
                            const response=await fetch(`/api/__test__/profile-save`,{method:`POST`,headers:{'Content-Type':`image/png`},body:png});
                            const result=await response.json();
                            if(!response.ok)throw new Error(JSON.stringify(result));
                            runs.push({...result,totalSeconds:(performance.now()-started)/1000,storageCalls:window.saveStorageProfile||[]});
                        }
                        return runs;
                    }''')
                    expected=hashlib.sha256(png.getvalue()).hexdigest()
                    assert all(run['asset']==expected for run in runs)
                    direct_writes=page.evaluate('''async folderMode=>{
                        const directory=folderMode?await (await import(`/web/storage-choice.js`)).savedFolder():await navigator.storage.getDirectory();
                        const png=await (await fetch(`/profile.png`)).blob();
                        const rows=[];
                        for(let index=0;index<3;index++){
                            const started=performance.now();
                            const handle=await directory.getFileHandle(`direct-profile-`+index+`.png`,{create:true});
                            const stream=await handle.createWritable();await stream.write(png);await stream.close();
                            rows.push((performance.now()-started)/1000);
                        }
                        return rows;
                    }''',folder_mode)
                    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
                    restored=page.evaluate('''async asset=>{
                        const bytes=await (await fetch(`/api/assets/`+asset)).arrayBuffer();
                        return [...new Uint8Array(await crypto.subtle.digest(`SHA-256`,bytes))].map(byte=>byte.toString(16).padStart(2,`0`)).join(``);
                    }''',expected)
                    assert restored==expected
                    if disk_folder:assert hashlib.sha256((disk_folder/'assets'/expected[:2]/expected).read_bytes()).hexdigest()==expected
                    report={'storageType':storage_type,'variant':variant,'bytes':len(png.getvalue()),'runs':runs,'directWriteSeconds':direct_writes,'reloadVerified':True,'folder':str(disk_folder) if disk_folder else None}
                    suffix='' if variant=='baseline' else '-'+variant
                    output=ROOT/'test-results'/('save-profile-'+storage_type+suffix+'.json')
                    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print('Profile passed:',output,flush=True)
                    for run in runs:
                        grouped={}
                        for call in run['fileCalls']:
                            category=(call['operation'],(call['path'] or '').split('/')[0]);row=grouped.setdefault(category,[0,0])
                            row[0]+=1;row[1]+=call['seconds']
                        print(json.dumps({'total':run['totalSeconds'],'stages':run['profile'],'fileCalls':[{'category':key,'count':value[0],'seconds':value[1]} for key,value in grouped.items()]},indent=2),flush=True)
                finally:
                    context.close()
                    if browser:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
