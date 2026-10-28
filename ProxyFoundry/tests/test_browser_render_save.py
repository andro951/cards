"""Browser direct-write saver boundaries without a Python/image upload round trip."""
import base64,io,json,shutil,subprocess
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def test_real_browser_save_recovers_stale_handle_and_preserves_existing_assets(tmp_path):
    import functools,http.server,os,threading,pytest
    if os.environ.get('PF_BROWSER')!='1':pytest.skip('Opt-in isolated browser storage')
    from playwright.sync_api import sync_playwright
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    out=io.BytesIO();Image.new('RGBA',(40,56),'blue').save(out,'PNG')
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,**({'channel':os.environ['PF_BROWSER_CHANNEL']} if os.environ.get('PF_BROWSER_CHANNEL') else {}))
            page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/web/')
            result=page.evaluate('''async png=>{
                const {BrowserRenderSave}=await import('/web/render-save.js');
                const root=await (await navigator.storage.getDirectory()).getDirectoryHandle('save-test',{create:true});
                const saver=await BrowserRenderSave.open(null,root,{id:'isolated'});
                const original=saver.write;let injected=0,handles=0;
                saver.write=async(folder,name,data)=>original({getFileHandle:async(...args)=>{
                    const handle=await folder.getFileHandle(...args);handles++;
                    return {getFile:()=>handle.getFile(),createWritable:async()=>{
                        if(!injected++){throw new DOMException('State changed since read from disk','InvalidStateError');}
                        return handle.createWritable();
                    }};
                }},name,data);
                const blob=new Blob([Uint8Array.from(atob(png),c=>c.charCodeAt(0))]);
                const target={key:'a'.repeat(64),deckId:'deck',cardId:'card',faceId:'face'};
                await Promise.all([1,2,3].map(()=>saver.save(target,{blob,width:40,height:56})));
                const hash=saver.rows[0].hash,folder=await saver.assets.getDirectoryHandle(hash.slice(0,2));
                const handle=await folder.getFileHandle(hash),before=await handle.getFile();
                await new Promise(resolve=>setTimeout(resolve,30));
                const reopened=await BrowserRenderSave.open(null,root,{id:'second'});
                await reopened.save(target,{blob,width:40,height:56});
                const after=await handle.getFile();
                return {rows:saver.rows.length,handles,preserved:before.lastModified===after.lastModified,bytes:await after.text()===await blob.text()};
            }''',base64.b64encode(out.getvalue()).decode())
            assert result=={'rows':3,'handles':2,'preserved':True,'bytes':True}
            browser.close()
    finally:server.shutdown();server.server_close()


def test_direct_browser_save_validation_grouping_and_retry():
    out=io.BytesIO();Image.new('RGBA',(40,56),'blue').save(out,'PNG')
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/render-save.js').read_bytes()).decode()
    code='''
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
globalThis.performance={now:()=>100};
let decoded=0,closed=0,failWrite=false,failCommit=false,commits=0;
globalThis.createImageBitmap=async()=>{decoded++;return {width:40,height:56,close(){closed++;}};};
class Directory{
 constructor(){this.directories=new Map();this.files=new Map();}
 async getDirectoryHandle(name){if(!this.directories.has(name))this.directories.set(name,new Directory());return this.directories.get(name);}
 async getFileHandle(name){
  const files=this.files;
  return {async getFile(){return files.get(name)||new Blob([]);},async createWritable(){
   const chunks=[];
   return new WritableStream({write(value){if(failWrite)throw Error('full');chunks.push(value);},close(){files.set(name,new Blob(chunks));}});
  }};
 }

}
const {BrowserRenderSave}=await import(MODULE);
const root=new Directory();
const api=async()=>{commits++;if(failCommit)throw Error('checkpoint');};
const saver=await BrowserRenderSave.open(api,root);
const png=new Blob([Buffer.from(PNG_DATA,'base64')]);
const target={key:'a'.repeat(64),deckId:'deck',cardId:'card',faceId:'face'};
const output={blob:png,width:40,height:56};
await assert.rejects(()=>saver.save(target,{...output,width:41}),/dimensions/);
failWrite=true;await assert.rejects(()=>saver.save(target,output),/full/);failWrite=false;
assert.equal(saver.pending,0);assert.equal(saver.journal.files.size,0);
for(let i=0;i<9;i++){await saver.save(target,output);}
assert.equal(commits,0);assert.equal(saver.journal.files.size,9);
failCommit=true;await assert.rejects(()=>saver.save(target,output),/checkpoint/);
assert.equal(saver.pending,10);assert.equal(saver.journal.files.size,10);
failCommit=false;await saver.flush();assert.equal(saver.pending,0);assert.equal(commits,2);
await saver.flush();assert.equal(commits,2);
let count=0;for(const folder of saver.assets.directories.values()){count+=folder.files.size;}
assert.equal(count,1,'Identical PNGs share their stored bytes.');assert.equal(decoded,closed);
'''.replace('MODULE',json.dumps(module)).replace('PNG_DATA',json.dumps(base64.b64encode(out.getvalue()).decode()))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_render_worker_selection_is_bounded_for_memory_and_cpu():
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'site/native-render-pool.js').read_bytes()).decode()
    code='''import assert from 'node:assert/strict';
const {renderWorkerCount}=await import(MODULE);
for(const [targets,workers,device,expected] of [
 [121,true,{deviceMemory:8,hardwareConcurrency:8},3],
 [2,true,{deviceMemory:8,hardwareConcurrency:8},2],
 [121,true,{deviceMemory:4,hardwareConcurrency:8},1],
 [121,true,{deviceMemory:8,hardwareConcurrency:2},1],
 [121,true,{},1],[121,false,{deviceMemory:8,hardwareConcurrency:8},1]
]){assert.equal(renderWorkerCount(targets,workers,device),expected);}
'''.replace('MODULE',json.dumps(module))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
