import {RequestQueue,requestPriority} from './request-queue.js';
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
const foregroundJobs=new Set();
self.publishJob=encoded=>{
  const job=JSON.parse(responseText(encoded));
  if(['done','failed','cancelled'].includes(job.state))foregroundJobs.delete(job.id);
  else if(job.priority===0)foregroundJobs.add(job.id);
  if(['done','failed','cancelled'].includes(job.state))completedJobs.push(job);
  else self.postMessage({type:'job',job});
};
self.jobCancelled=ident=>{
  const result=self.syncFetch(`/api/jobs/${ident}/control?owner=${encodeURIComponent(owner)}`);
  return JSON.parse(new TextDecoder().decode(result.bytes)).cancelled;
};
async function start(folder){
  const started=performance.now();
  let stage='pyodide',measured=started;
  const mark=next=>{
    const now=performance.now(),seconds=(now-measured)/1000;
    if(seconds>=.1)self.postMessage({type:'startup-timing',stage,seconds,storageType:folder?'selected-folder':'browser'});
    stage=next;measured=now;
  };
  try{
  self.postMessage({type:'status',message:'Loading card engine…'});
  python=await loadPyodide();
  mark('pillow');
  self.postMessage({type:'status',message:'Loading image tools…'});
  await python.loadPackage('pillow');
  mark('workspace-open');
  self.postMessage({type:'status',message:'Opening saved workspace…'});
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
  mark('bundle-fetch');
  self.postMessage({type:'status',message:'Loading application bundle…'});
  const archive=await fetch('/web/runtime.zip',{cache:'no-store'});
  if(!archive.ok)
    throw new Error(`Card engine bundle could not be loaded (${archive.status}).`);
  const archiveBytes=await archive.arrayBuffer();
  mark('bundle-unpack');
  python.unpackArchive(archiveBytes,'zip',{extractDir:'/app/ProxyFoundry'});
  mark('python-app-init');
  self.postMessage({type:'status',message:'Starting workspace tools…'});

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

  self.syncGithubBatch=urls=>{
    const xhr=new XMLHttpRequest();
    xhr.open(`POST`,`/github-setup-fetch`,false);
    xhr.responseType=`arraybuffer`;
    xhr.setRequestHeader(`Content-Type`,`application/json`);
    xhr.send(String(urls));
    if(xhr.status!==200)
      throw new Error(`GitHub setup download failed (HTTP ${xhr.status}).`);

    return new Uint8Array(xhr.response);
  };

  python.runPython(`
import sys
sys.path.insert(0,'/app/ProxyFoundry')
from js import syncFetch, syncGithubBatch, location, publishJob, jobCancelled, checkpointMetadata, copyWorkspaceFile
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
def transport_many(urls):
    import struct
    raw=buffer_bytes(syncGithubBatch(json.dumps(urls)))
    size=struct.unpack('>I',raw[:4])[0]
    rows=json.loads(raw[4:4+size]);offset=4+size;result={}
    if len(rows)!=len(urls):raise ValueError('Incomplete GitHub setup batch')
    for url,row in zip(urls,rows):
        end=offset+row['size']
        if end>len(raw):raise ValueError('Truncated GitHub setup batch')
        result[url]=(raw[offset:end],row['mime'],{});offset=end
    return result
transport.fetch_many=transport_many
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
  mark('ready');
  self.postMessage({type:'ready',buildId});
  }
  finally{
    self.postMessage({type:'startup-timing',stage:'engine-total',seconds:(performance.now()-started)/1000,storageType:folder?'selected-folder':'browser',outcome:initialized?'ok':'failed',lastStage:stage});
  }
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

const requests=new RequestQueue();
let cleanupTimer=null;
let jobTimer=null;
function scheduleJobs(){
  if(jobTimer!==null)return;
  //A timer turn lets foreground requests enter the queue before another chunk.
  jobTimer=setTimeout(()=>{
    jobTimer=null;
    requests.enqueue(runJobs,()=>foregroundJobs.size?0:2).then(pending=>{if(pending)scheduleJobs();});
  },0);
}
function scheduleCleanup(){
  if(cleanupTimer!==null)return;
  cleanupTimer=setTimeout(()=>{
    cleanupTimer=null;
    requests.enqueue(async()=>{
      if(!initialized)return;
      try{
        const result=JSON.parse(python.runPython('json.dumps(app.store.cleanup_step())'));
        if(result.processed)await mount.syncfs();
        if(result.errors.length)self.postMessage({type:'cleanup-warning',message:result.errors[0]});
        if(result.pending>result.errors.length)scheduleCleanup();
      }
      catch(error){self.postMessage({type:'cleanup-warning',message:String(error.message||error)});}
    },3);
  },150);
}
self.onmessage=event=>{
  if(event.data.type==='start'){
    owner=event.data.owner;
    ready=start(event.data.folder).catch(error=>self.postMessage({type:'fatal',message:String(error.stack||error)}));
    return;
  }
  requests.enqueue(()=>handle(event),requestPriority(event.data)).then(()=>{scheduleJobs();scheduleCleanup();});
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
