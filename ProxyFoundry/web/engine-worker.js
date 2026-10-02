import {mountWorkspaceFiles} from './workspace-fs.js';
import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';

const buildId='development';
let python;
let mount;
let workspaceMount;
let ready;
let owner;
let initialized=false;
let completedJobs=[];
self.publishJob=encoded=>{
  const job=JSON.parse(responseText(encoded));
  if(['done','failed','cancelled'].includes(job.state))completedJobs.push(job);
  else self.postMessage({type:'job',job});
};
self.jobCancelled=ident=>{
  const result=self.syncFetch(`/api/jobs/${ident}/control?owner=${encodeURIComponent(owner)}`);
  return JSON.parse(new TextDecoder().decode(result.bytes)).cancelled;
};
async function start(folder){
  self.postMessage({type:'status',message:'Loading card engine…'});
  python=await loadPyodide();
  await python.loadPackage('pillow');
  const directory=folder||await navigator.storage.getDirectory();
  python.FS.mkdirTree('/workspace');
  for await(const [name,entry] of directory.entries()){
    if(entry.kind==='file'&&['workspace.sqlite3','workspace.sqlite3-wal','workspace.sqlite3-shm'].includes(name))python.FS.writeFile('/workspace/'+name,new Uint8Array(await (await entry.getFile()).arrayBuffer()));
  }
  workspaceMount=mountWorkspaceFiles(python.FS,owner);
  self.copyWorkspaceFile=(source,destination)=>workspaceMount.copyFile(String(source).replace('/workspace/',''),String(destination).replace('/workspace/',''));
  self.checkpointMetadata=path=>{
    const request=new XMLHttpRequest();
    request.open('POST',`/workspace-io?owner=${encodeURIComponent(owner)}&operation=checkpoint&path=workspace.sqlite3`,false);
    request.responseType='arraybuffer';request.send(python.FS.readFile(String(path)));
    if(request.status!==200)throw new Error(`Workspace checkpoint failed (${request.status}).`);
  };
  mount={syncfs:async()=>python.runPython('app.store.checkpoint()')};
  const archive=await fetch('/web/runtime.zip',{cache:'no-store'});
  if(!archive.ok)
    throw new Error(`Card engine bundle could not be loaded (${archive.status}).`);
  python.unpackArchive(await archive.arrayBuffer(),'zip',{extractDir:'/app/ProxyFoundry'});

  const bundleVersion=JSON.parse(new TextDecoder().decode(python.FS.readFile('/app/ProxyFoundry/build.json'))).id;
  if(bundleVersion!==buildId)throw new Error('The website engine bundle is a different version. Reload the page to finish updating.');

  self.syncFetch=url=>{
    const xhr=new XMLHttpRequest();
    xhr.open('GET',url,false);
    xhr.responseType='arraybuffer';
    xhr.setRequestHeader('Accept','application/json;q=0.9,image/*;q=0.8,*/*;q=0.7');
    xhr.send();
    if(xhr.status!==200)
      throw new Error(`HTTP ${xhr.status} ${url}`);
    return {bytes:new Uint8Array(xhr.response),mime:xhr.getResponseHeader('Content-Type')||'application/octet-stream'};
  };

  python.runPython(`
import sys
sys.path.insert(0,'/app/ProxyFoundry')
from js import syncFetch, location, publishJob, jobCancelled, checkpointMetadata, copyWorkspaceFile
import base64, json, uuid
from pathlib import Path
from foundry.browser import create_app, request
def buffer_bytes(buffer):
    if not buffer.byteLength:
        return b''
    path=Path('/tmp')/('.http-'+str(uuid.uuid4()))
    try:
        with path.open('wb') as saved:
            buffer.to_file(saved)
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)

def transport(url):
    result = syncFetch(url)
    return buffer_bytes(result.bytes), str(result.mime), {}
app = create_app('/workspace', transport, str(location.origin),
    lambda job:publishJob('\u0100'+json.dumps(job,ensure_ascii=False,default=str)),
    lambda ident:bool(jobCancelled(ident)), checkpointMetadata, storage_type='${folder?'selected-folder':'browser'}', copy_file=copyWorkspaceFile)
def browser_request(method, url, body, headers):
    global last_response
    last_response = request(app, str(method), str(url), buffer_bytes(body), dict(headers.to_py()))
    metadata={k:v for k,v in last_response.items() if k != 'body'}
    encoded={'metadata':'\u0100'+json.dumps(metadata,ensure_ascii=False)}
    if not metadata.get('file'):
        if metadata['mime']=='application/json':
            encoded['jsonBody']='\u0100'+last_response['body'].decode('utf-8')
        else:
            encoded['binaryBody']='\u0100'+base64.b64encode(last_response['body']).decode('ascii')
    return encoded
`);
  initialized=true;
  self.postMessage({type:'ready',buildId});
}

//The marker avoids Pyodide's signed ASCII/buffer offsets above 2 GiB.
//Large saved files travel as file descriptors; only inline replies use this codec.
function responseText(value){
  if(typeof value!=='string'||value.charCodeAt(0)!==0x100)throw new Error('The card engine response text could not be read.');
  return value.slice(1);
}
function responseBytes(value){
  const encoded=responseText(value);
  if(Uint8Array.fromBase64)return Uint8Array.fromBase64(encoded);
  const decoded=atob(encoded),bytes=new Uint8Array(decoded.length);
  for(let i=0;i<decoded.length;i++)bytes[i]=decoded.charCodeAt(i);
  return bytes;
}

let sequence=Promise.resolve();
let cleanupTimer=null;
let jobTimer=null;
function scheduleJobs(){
  if(jobTimer!==null)return;
  //A timer turn lets foreground requests enter the queue before another chunk.
  jobTimer=setTimeout(()=>{
    jobTimer=null;
    sequence=sequence.then(runJobs).then(pending=>{if(pending)scheduleJobs();});
  },0);
}
function scheduleCleanup(){
  if(cleanupTimer!==null)return;
  cleanupTimer=setTimeout(()=>{
    cleanupTimer=null;
    sequence=sequence.then(async()=>{
      if(!initialized)return;
      try{
        const result=JSON.parse(python.runPython('json.dumps(app.store.cleanup_step())'));
        if(result.processed)await mount.syncfs();
        if(result.errors.length)self.postMessage({type:'cleanup-warning',message:result.errors[0]});
        if(result.pending>result.errors.length)scheduleCleanup();
      }
      catch(error){self.postMessage({type:'cleanup-warning',message:String(error.message||error)});}
    });
  },150);
}
self.onmessage=event=>{
  if(event.data.type==='start'){
    owner=event.data.owner;
    ready=start(event.data.folder).catch(error=>self.postMessage({type:'fatal',message:String(error.stack||error)}));
    return;
  }
  sequence=sequence.then(()=>handle(event)).then(()=>{scheduleJobs();scheduleCleanup();});
};

async function handle(event){
  const {id,method,url,body,headers}=event.data;
  if(!id)return;
  let invoke,response;
  try{
    await ready;
    workspaceMount.setInput(id,headers?.['content-type']==='image/png'?new Uint8Array(body||[]):new Uint8Array());
    invoke=python.globals.get('browser_request');
    response=invoke(method,url,new Uint8Array(body||[]),headers||{});
    const encoded=response.toJs({dict_converter:Object.fromEntries});
    const metadata=JSON.parse(responseText(encoded.metadata));
    let responseBody;
    if(encoded.jsonBody!==undefined)responseBody=responseText(encoded.jsonBody);
    else responseBody=metadata.file?new Uint8Array():responseBytes(encoded.binaryBody);
    if(typeof responseBody==='string'){
      try{JSON.parse(responseBody);}catch(error){throw new Error(`Invalid engine JSON (${url}, ${responseBody.length} characters): ${error.message}`);}
    }
    if(method==='POST')await mount.syncfs();
    self.postMessage({type:'response',id,...metadata,body:responseBody},responseBody.buffer?[responseBody.buffer]:[]);
  }
  catch(error){self.postMessage({type:'error',id,message:String(error.stack||error)});}
  finally{
    workspaceMount?.clearInput();
    //Every PyProxy owns a Python reference; leaked responses retain whole PNGs.
    response?.destroy();
    invoke?.destroy();
    if(python?.globals.has('last_response'))
      python.globals.delete('last_response');
  }
}


async function runJobs(){
  if(!initialized)return;
  try{
    const pending=python.runPython('app.jobs.run_pending(limit=1)');
    if(!completedJobs.length)return pending;
    await mount.syncfs();
    for(const job of completedJobs){self.postMessage({type:'job',job});}
    return pending;
  }
  catch(error){
    for(const job of completedJobs){
      self.postMessage({type:'job',job:{...job,state:'failed',error:`Workspace save failed: ${error.message}`,message:'Workspace save failed. Download diagnostics before reloading.'}});
    }
    initialized=false;self.postMessage({type:'fatal',message:`Workspace operation failed: ${error.message}. Download browser diagnostics before reloading.`});
  }
  finally{completedJobs=[];}
}
