import {loadPyodide} from 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';

let python;
let mount;
let ready;
async function start(folder){
  self.postMessage({type:'status',message:'Loading card engine…'});
  python=await loadPyodide();
  await python.loadPackage('pillow');
  mount=await python.mountNativeFS('/workspace',folder||await navigator.storage.getDirectory());
  const archive=await fetch('/web/runtime.zip');
  if(!archive.ok)
    throw new Error(`Card engine bundle could not be loaded (${archive.status}).`);
  python.unpackArchive(await archive.arrayBuffer(),'zip',{extractDir:'/app/ProxyFoundry'});

  self.syncFetch=url=>{
    const host=new URL(url).hostname;
    const target=['archidekt.com','www.archidekt.com','mtggoldfish.com','www.mtggoldfish.com'].includes(host)
      ?`/gateway/deck?url=${encodeURIComponent(url)}`:url;
    const xhr=new XMLHttpRequest();
    xhr.open('GET',target,false);
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
from js import syncFetch, location
from foundry.browser import create_app, request
def transport(url):
    result = syncFetch(url)
    return bytes(result.bytes.to_py()), str(result.mime), {}
app = create_app('/workspace', transport, str(location.origin))
def browser_request(method, url, body, headers):
    global last_response
    last_response = request(app, str(method), str(url), bytes(body.to_py()), dict(headers.to_py()))
    return {k:v for k,v in last_response.items() if k != 'body'}
`);
  self.postMessage({type:'ready'});
}

let sequence=Promise.resolve();
self.onmessage=event=>{
  if(event.data.type==='start'){
    ready=start(event.data.folder).catch(error=>self.postMessage({type:'fatal',message:String(error.stack||error)}));
    return;
  }
  sequence=sequence.then(()=>handle(event));
};

async function handle(event){
  const {id,method,url,body,headers}=event.data;
  if(!id)return;
  try{
    await ready;
    const invoke=python.globals.get('browser_request');
    const response=invoke(method,url,new Uint8Array(body||[]),headers||{});
    const metadata=response.toJs({dict_converter:Object.fromEntries});
    response.destroy();
    invoke.destroy();
    const content=python.globals.get('last_response').get('body');
    const bytes=content.toJs();
    content.destroy();
    if(method==='POST')await mount.syncfs();
    self.postMessage({type:'response',id,...metadata,body:bytes},[bytes.buffer]);
  }
  catch(error){self.postMessage({type:'error',id,message:String(error.stack||error)});}
}

