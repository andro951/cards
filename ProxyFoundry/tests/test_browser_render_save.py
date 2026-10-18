"""Browser direct-write saver boundaries without a Python/image upload round trip."""
import base64,io,json,shutil,subprocess
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


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
  return {async createWritable(){
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
