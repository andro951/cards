import {mountWorkspaceFiles} from './workspace-fs.js';
import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';

let python;
let mount;
let ready;
let owner;
let initialized=false;
let completedJobs=[];
self.publishJob=encoded=>{
  const job=JSON.parse(encoded);
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
    if(entry.kind==='file')python.FS.writeFile('/workspace/'+name,new Uint8Array(await (await entry.getFile()).arrayBuffer()));
  }
  mountWorkspaceFiles(python.FS,owner);
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
from js import syncFetch, location, publishJob, jobCancelled, checkpointMetadata
import json
from foundry.browser import create_app, request
def transport(url):
    result = syncFetch(url)
    return bytes(result.bytes.to_py()), str(result.mime), {}
app = create_app('/workspace', transport, str(location.origin),
    lambda job:publishJob(json.dumps(job,ensure_ascii=False,default=str)),
    lambda ident:bool(jobCancelled(ident)), checkpointMetadata)
def browser_request(method, url, body, headers):
    global last_response
    last_response = request(app, str(method), str(url), bytes(body.to_py()), dict(headers.to_py()))
    return {k:v for k,v in last_response.items() if k != 'body'}
`);
  initialized=true;
  self.postMessage({type:'ready'});
}

let sequence=Promise.resolve();
self.onmessage=event=>{
  if(event.data.type==='start'){
    owner=event.data.owner;
    ready=start(event.data.folder).catch(error=>self.postMessage({type:'fatal',message:String(error.stack||error)}));
    return;
  }
  sequence=sequence.then(()=>handle(event)).then(runJobs);
};

async function handle(event){
  const {id,method,url,body,headers}=event.data;
  if(!id)return;
  let invoke,response,saved,content;
  try{
    await ready;
    invoke=python.globals.get('browser_request');
    response=invoke(method,url,new Uint8Array(body||[]),headers||{});
    const metadata=response.toJs({dict_converter:Object.fromEntries});
    saved=python.globals.get('last_response');
    content=saved.get('body');
    const bytes=content.toJs();
    if(method==='POST')await mount.syncfs();
    self.postMessage({type:'response',id,...metadata,body:bytes},[bytes.buffer]);
  }
  catch(error){self.postMessage({type:'error',id,message:String(error.stack||error)});}
  finally{
    //Every PyProxy owns a Python reference; leaked responses retain whole PNGs.
    content?.destroy();
    saved?.destroy();
    response?.destroy();
    invoke?.destroy();
    if(python?.globals.has('last_response'))
      python.globals.delete('last_response');
  }
}


async function runJobs(){
  if(!initialized)return;
  python.runPython('app.jobs.run_pending()');
  if(!completedJobs.length)return;
  try{
    await mount.syncfs();
    for(const job of completedJobs){self.postMessage({type:'job',job});}
  }
  catch(error){
    for(const job of completedJobs){
      self.postMessage({type:'job',job:{...job,state:'failed',error:`Workspace save failed: ${error.message}`,message:'Workspace save failed. Download diagnostics before reloading.'}});
    }
  }
  finally{completedJobs=[];}
}
