import '/site/favicon.js';
import {WorkspaceFiles} from './workspace-files.js';
import {createWorkspaceFetch} from './workspace-transport.js';
import {recordDiagnostic,setEngineStatus,downloadBrowserDiagnostics} from '/site/diagnostics.js';
const basePath='';
const buildId='development';
const startupStarted=performance.now();
let startupStage='register-service-worker';
const startupError=error=>{
  recordDiagnostic('startup failure',JSON.stringify({stage:startupStage,name:error.name,message:error.message,stack:error.stack}));
  message.textContent=`Could not open the browser workspace: ${error.message}`;
  const retry=document.createElement('button');retry.className='button';retry.textContent='Retry opening workspace';
  retry.onclick=()=>location.reload();startup.append(retry);
};
window.__pfBasePath=basePath;
window.__pfBuildId=buildId;
const shell=document.querySelector('.app-shell');
shell.style.display='none';
const startup=document.createElement('main');
startup.id='browser-startup';
startup.setAttribute('role','status');
startup.setAttribute('aria-live','polite');
startup.style.display='flex';
startup.style.minHeight='100dvh';
startup.style.flexDirection='column';
startup.style.alignItems='center';
startup.style.justifyContent='center';
startup.style.gap='24px';
startup.style.padding='24px';
startup.style.textAlign='center';
const logo=document.createElement('img');
logo.src='/site/logo.png';
logo.alt='Bulk Proxy Forge';
logo.style.width='min(65vw, 300px)';
logo.style.height='auto';
const message=document.createElement('p');
message.textContent='Opening Bulk Proxy Forge…';
message.style.fontSize='15px';
startup.append(logo,message);
document.body.append(startup);
document.body.hidden=false;
const diagnosticButton=document.createElement('button');diagnosticButton.className='button';diagnosticButton.textContent='Download browser diagnostics';
diagnosticButton.onclick=downloadBrowserDiagnostics;startup.append(diagnosticButton);

function reloadUpdatedPage(automatic=false){
  const key='pf-startup-update-retry',now=Date.now();
  //A deployment can briefly serve mixed files. Retry once, without a reload loop.
  if(automatic&&now-Number(sessionStorage.getItem(key)||0)<60000)return false;

  sessionStorage.setItem(key,String(now));
  const url=new URL(location.href);url.searchParams.set('_pf_update',String(now));
  location.replace(url.href);
  return true;
}

try{
const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'});
await navigator.serviceWorker.ready;
if(!navigator.serviceWorker.controller){
  message.textContent='Opening browser workspace…';
  location.reload();
}
else{
  const owner=sessionStorage.getItem('pf-tab-owner')||crypto.randomUUID();
  sessionStorage.setItem('pf-tab-owner',owner);
  window.__pfOwner=owner;
  const announceOwner=()=>navigator.serviceWorker.controller?.postMessage({type:'owner',owner});
  announceOwner();navigator.serviceWorker.addEventListener('controllerchange',announceOwner);
  const worker=new Worker('/web/engine-worker.js?v='+buildId,{type:'module'});
  const {savedFolder,rememberedLocation,chooseFolder,useFolder,useBrowserStorage}=await import('/web/storage-choice.js');
  startupStage='read-workspace-preference';
  let folder=await savedFolder();
  if(!folder&&rememberedLocation()?.kind==='folder'){
    message.textContent='The saved workspace folder connection is missing. Reconnect your folder to open your saved decks.';
    await new Promise(resolve=>{
      const reconnect=document.createElement('button');reconnect.className='button primary';reconnect.textContent='Reconnect workspace folder';
      reconnect.onclick=async()=>{
        try{
          const selected=await chooseFolder({existingOnly:true});await useFolder(selected);folder=selected;
          reconnect.remove();alternative.remove();resolve();
        }catch(error){if(error.name!=='AbortError')message.textContent=error.message;}
      };
      const alternative=document.createElement('button');alternative.className='button';alternative.textContent='Open separate browser workspace';
      alternative.onclick=async()=>{
        if(!window.confirm('Open the separate browser workspace? Your saved folder decks remain in their existing folder.'))return;
        try{await useBrowserStorage();location.reload();}catch(error){message.textContent=error.message;}
      };
      startup.append(reconnect,alternative);
    });
  }
  startupStage='check-workspace-permission';
  if(folder&&await folder.queryPermission({mode:'readwrite'})!=='granted'){
    message.textContent='Reconnect your workspace folder to open your saved decks.';
    await new Promise(resolve=>{
      const reconnect=document.createElement('button');reconnect.className='button primary';reconnect.textContent='Reconnect workspace folder';
      reconnect.onclick=async()=>{
        const permission=await folder.requestPermission({mode:'readwrite'});
        if(permission==='granted'){reconnect.remove();alternative.remove();resolve();}
        else message.textContent='Folder access was not granted. Reconnect to keep using this workspace.';
      };
      const alternative=document.createElement('button');alternative.className='button';alternative.textContent='Open separate browser workspace';
      alternative.onclick=async()=>{
        if(!window.confirm('Open the separate browser workspace? Your folder workspace will stay in its current location.'))return;
        const {useBrowserStorage}=await import('/web/storage-choice.js');await useBrowserStorage();location.reload();
      };
      startup.append(reconnect,alternative);
    });
  }
  if(!navigator.locks)throw new Error('This browser cannot safely lock your workspace. Open the site in a current browser.');
  startupStage='lock-workspace';
  await new Promise(resolve=>{
    navigator.locks.request('bulk-proxy-forge-workspace',{ifAvailable:true},async lock=>{
      if(!lock){
        message.textContent='This workspace is already open in another tab. Close that tab, then retry.';
        const retry=document.createElement('button');retry.className='button';retry.textContent='Retry opening workspace';retry.onclick=()=>location.reload();startup.append(retry);return;
      }
      resolve();
      await new Promise(()=>{});
    }).catch(error=>{message.textContent=`Could not lock the workspace: ${error.message}`;});
  });
  startupStage='open-browser-storage';
  const browserRoot=await navigator.storage.getDirectory();
  startupStage='open-download-staging';
  const stagingRoot=await browserRoot.getDirectoryHandle(`bulk-proxy-forge-download-staging`,{create:true});
  const stagingSession=`session-${crypto.randomUUID()}`;
  const downloadStaging=await stagingRoot.getDirectoryHandle(stagingSession,{create:true});
  window.__pfWorkspaceDirectory=folder||browserRoot;
  const files=new WorkspaceFiles(folder||browserRoot,downloadStaging);
  const pending=new Map();
  const jobs=new Map();
  let engineFailure=null;
  let readyResolve;
  let readyReject;
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
  const failEngine=error=>{
    engineFailure=String(error);
    setEngineStatus('Failed: '+engineFailure);
    readyReject(new Error(engineFailure));
    for(const [id,port] of pending){
      port.postMessage({type:'error',id,message:engineFailure});port.close();
    }
    pending.clear();
    files.inputBuffers.clear();
  };
  const recoverVersion=error=>{
    failEngine(error);worker.terminate();
    recordDiagnostic('startup version mismatch',error);
    if(reloadUpdatedPage(true))return;

    const retry=document.createElement('button');retry.className='button primary';retry.textContent='Reload updated app';
    retry.onclick=()=>reloadUpdatedPage();startup.append(retry);
  };
  worker.onerror=event=>failEngine(event.message||'The card engine stopped. Reload the page to continue; completed images are saved.');
  worker.onmessageerror=()=>failEngine('The card engine response could not be read. Reload the page to continue; completed images are saved.');

  worker.onmessage=async event=>{
    const data=event.data;
    if(data.type==='startup-timing')recordDiagnostic('startup timing',JSON.stringify(data));
    if(data.type==='cleanup-warning')window.dispatchEvent(new CustomEvent('pf-cleanup-warning',{detail:data.message}));
    if(data.type==='job'){
      if(data.job.logWarning&&data.job.logWarning!==jobs.get(data.job.id)?.logWarning)
        recordDiagnostic('job log warning',`${data.job.id}: ${data.job.logWarning}`);
      const completed=[...jobs].filter(([,job])=>['done','failed','cancelled'].includes(job.state));
      for(const [id] of completed.slice(0,Math.max(0,completed.length-19)))jobs.delete(id);
      jobs.set(data.job.id,{...data.job,cancelled:data.job.cancelled||jobs.get(data.job.id)?.cancelled||false});
      window.dispatchEvent(new CustomEvent(`pf-job`,{detail:data.job}));
      recordDiagnostic('task',`${data.job.kind}: ${data.job.message} (${data.job.done}/${data.job.total})`);}
    if(data.type==='status'){message.textContent=data.message;setEngineStatus(data.message);}
    if(data.type==='ready'){
      if(data.buildId!==buildId)recoverVersion(`The website and card engine are different versions. Reload the page to finish updating; saved decks stay in your workspace. (Website ${buildId}, engine ${data.buildId}.)`);
      else{setEngineStatus('Ready');readyResolve();}
    }
    if(data.type==='fatal'){
      if(data.code==='BUILD_MISMATCH')recoverVersion(data.message);
      else failEngine(data.message);
    }
    if(data.type==='response'||data.type==='error'){
      files.inputBuffers.delete(data.id);
      const port=pending.get(data.id);
      pending.delete(data.id);
      if(data.type==='error')recordDiagnostic('engine request failed',data.message);
      if(port){
        if(data.file){
          try{data.body=data.fileSpans?await files.readSpans(data.file,data.fileSpans,data.fileSignature):await files.file(data.file);}
          catch(error){data.type='error';data.message=`Saved workspace file could not be read: ${error.message}`;}
        }
        port.postMessage(data,data.body?.buffer?[data.body.buffer]:[]);port.close();
      }
    }
  };
  startupStage='start-card-engine';
  worker.postMessage({type:'start',folder,owner});

  const dispatchWorkspaceRequest=async (data,port)=>{
    try{
      if(engineFailure)throw new Error(engineFailure);
      if(data.url.startsWith('/workspace-io?')){
        try{
          const result=await files.respond(data);
          port.postMessage({type:'response',id:data.id,...result},result.body?.buffer?[result.body.buffer]:[]);
        }
        catch(error){
          if(error.name!=='NotFoundError'){
            const estimate=error.name==='QuotaExceededError'?await navigator.storage.estimate().catch(()=>null):null;
            recordDiagnostic('workspace storage',`${error.name}: ${error.message} · ${data.url}${estimate?' · '+JSON.stringify(estimate):''}`);
          }
          const status=error.name==='NotFoundError'?404:error.name==='NotAllowedError'?403:error.name==='InvalidModificationError'?409:error.name==='QuotaExceededError'?507:500;
          const body=new TextEncoder().encode(JSON.stringify({error:error.message}));
          port.postMessage({type:'response',id:data.id,status,mime:'application/json',body},[body.buffer]);
        }
        port.close();return;
      }
      await ready;
      const match=/^\/api\/jobs\/([-a-f0-9]{36})(\/cancel|\/control)?(?:\?.*)?$/.exec(data.url);
      if(match&&jobs.has(match[1])){
        const job=jobs.get(match[1]);
        if(match[2]==='/cancel')job.cancelled=true;
        const result=match[2]==='/cancel'?{ok:true}:match[2]==='/control'?{cancelled:job.cancelled}:job;
        const body=new TextEncoder().encode(JSON.stringify(result));
        port.postMessage({type:'response',id:data.id,status:200,mime:'application/json',body},[body.buffer]);port.close();return;
      }
      pending.set(data.id,port);
      if(data.headers?.['content-type']==='image/png'&&data.body?.byteLength>=65536)files.inputBuffers.set(data.id,new Uint8Array(data.body.slice(0)));
      worker.postMessage(data,data.body?[data.body]:[]);
    }
    catch(error){port.postMessage({type:'error',id:data.id,message:String(error)});port.close();}
  };
  window.__pfWorkspaceFetch=createWorkspaceFetch(dispatchWorkspaceRequest,id=>{
    pending.get(id)?.close();pending.delete(id);files.inputBuffers.delete(id);
  },basePath);
  navigator.serviceWorker.addEventListener('message',event=>{
    const data=event.data;
    if(data.type==='owner-probe'){event.ports[0]?.postMessage({owner});event.ports[0]?.close();return;}
    if(data.type==='request')dispatchWorkspaceRequest(data,event.ports[0]);
  });

  window.addEventListener('message',async event=>{
    const data=event.data;
    if(event.source!==window||event.origin!==location.origin||data?.source!=='proxy-foundry-helper'||data.type!=='PF_TRANSFER_REQUEST')return;
    const reply={source:'proxy-foundry-workspace',type:'PF_TRANSFER_REPLY',requestId:data.requestId};
    try{
      if(!/^[-a-f0-9]{36}$/.test(data.id)||!/^[-_A-Za-z0-9]{32,100}$/.test(data.secret)||!['metadata','zip'].includes(data.kind))throw new Error('Invalid print transfer.');
      const suffix=Number.isSafeInteger(data.batch)?'?batch='+data.batch:'';
      const headers={'X-Proxy-Transfer-Token':data.secret};
      if(data.kind==='zip'){
        if(!Number.isSafeInteger(data.offset)||data.offset<0)throw new Error('Invalid order chunk.');
        headers.Range=`bytes=${data.offset}-${data.offset+1024*1024-1}`;
      }
      const response=await window.__pfWorkspaceFetch('/api/transfer/'+data.id+'/'+data.kind+suffix,{headers,cache:'no-store'});
      if(!response.ok)throw new Error((await response.json().catch(()=>({}))).error||'Saved order could not be read.');
      if(data.kind==='metadata')reply.data=await response.json();
      else{
        if(response.status!==206)throw new Error('Expected a bounded order download range.');
        const bytes=new Uint8Array(await response.arrayBuffer());
        const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range')||'');
        if(!range||Number(range[1])!==data.offset||Number(range[2])-data.offset+1!==bytes.length||bytes.length>1024*1024||!bytes.length)throw new Error('Order range did not match requested chunk.');
        let content='';for(let i=0;i<bytes.length;i+=32768)content+=String.fromCharCode(...bytes.subarray(i,i+32768));
        reply.data={base64:btoa(content),offset:data.offset,length:bytes.length,total:Number(range[3])};
      }
      reply.ok=true;
    }catch(error){reply.ok=false;reply.error=error.message||String(error);}
    window.postMessage(reply,location.origin);
  });

  try{
    await ready;
    startupStage='open-workspace-ui';
    const appReady=new Promise((resolve,reject)=>{
      window.addEventListener('pf-ui-ready',resolve,{once:true});
      window.addEventListener('pf-ui-error',event=>reject(new Error(event.detail)),{once:true});
    });
    await Promise.all([import('/site/app.js'),appReady]);
    if(new URL(location.href).searchParams.has('_pf_update')){
      const url=new URL(location.href);url.searchParams.delete('_pf_update');history.replaceState(history.state,'',url.href);
    }

    shell.style.display='';
    startup.remove();
    recordDiagnostic('startup timing',JSON.stringify({stage:'website-total',seconds:(performance.now()-startupStarted)/1000,outcome:'ok',storageType:folder?'selected-folder':'browser'}));
    //An old browser file handle can prevent deletion. Temporary export cleanup
    //must never block opening the workspace or touch saved decks and images.
    const cleanup=async()=>{
      for await(const [name] of stagingRoot.entries()){
        if(name===stagingSession)continue;
        await stagingRoot.removeEntry(name,{recursive:true}).catch(error=>recordDiagnostic('download staging cleanup',`${name}: ${error.name}: ${error.message}`));
      }
    };
    cleanup().catch(error=>recordDiagnostic('download staging cleanup',`${error.name}: ${error.message}`));
  }
  catch(error){startupError(error);}
}
}
catch(error){startupError(error);}
