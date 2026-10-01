import {WorkspaceFiles} from './workspace-files.js';
import {recordDiagnostic,setEngineStatus,downloadBrowserDiagnostics} from '/site/diagnostics.js';
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

try{
const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});
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
  const worker=new Worker('/web/engine-worker.js',{type:'module'});
  const {savedFolder}=await import('/web/storage-choice.js');
  const folder=await savedFolder();
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
  const files=new WorkspaceFiles(folder||await navigator.storage.getDirectory());
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
  };
  worker.onerror=event=>failEngine(event.message||'The card engine stopped. Reload the page to continue; completed images are saved.');
  worker.onmessageerror=()=>failEngine('The card engine response could not be read. Reload the page to continue; completed images are saved.');

  worker.onmessage=async event=>{
    const data=event.data;
    if(data.type==='job'){jobs.set(data.job.id,{...data.job,cancelled:data.job.cancelled||jobs.get(data.job.id)?.cancelled||false});recordDiagnostic('task',`${data.job.kind}: ${data.job.message} (${data.job.done}/${data.job.total})`);}
    if(data.type==='status'){message.textContent=data.message;setEngineStatus(data.message);}
    if(data.type==='ready'){setEngineStatus('Ready');readyResolve();}
    if(data.type==='fatal')failEngine(data.message);
    if(data.type==='response'||data.type==='error'){
      const port=pending.get(data.id);
      pending.delete(data.id);
      if(data.type==='error')recordDiagnostic('engine request failed',data.message);
      if(port){
        if(data.file){
          try{data.body=await files.file(data.file);}
          catch(error){data.type='error';data.message=`Saved workspace file could not be read: ${error.message}`;}
        }
        port.postMessage(data,data.body?.buffer?[data.body.buffer]:[]);port.close();
      }
    }
  };
  worker.postMessage({type:'start',folder,owner});

  navigator.serviceWorker.addEventListener('message',async event=>{
    const data=event.data;
    if(data.type==='owner-probe'){event.ports[0]?.postMessage({owner});event.ports[0]?.close();return;}
    if(data.type!=='request')return;
    const port=event.ports[0];
    try{
      if(engineFailure)throw new Error(engineFailure);
      if(data.url.startsWith('/workspace-io?')){
        try{
          const result=await files.respond(data);
          port.postMessage({type:'response',id:data.id,...result},result.body?.buffer?[result.body.buffer]:[]);
        }
        catch(error){
          recordDiagnostic('workspace storage',`${error.name}: ${error.message}`);
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
      worker.postMessage(data,data.body?[data.body]:[]);
    }
    catch(error){port.postMessage({type:'error',id:data.id,message:String(error)});port.close();}
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
      const response=await fetch('/api/transfer/'+data.id+'/'+data.kind+suffix,{headers,cache:'no-store'});
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
    const appReady=new Promise((resolve,reject)=>{
      window.addEventListener('pf-ui-ready',resolve,{once:true});
      window.addEventListener('pf-ui-error',event=>reject(new Error(event.detail)),{once:true});
    });
    await Promise.all([import('/site/app.js'),appReady]);
    shell.style.display='';
    startup.remove();
  }
  catch(error){message.textContent=`Could not open the browser workspace: ${error.message}`;}
}
}
catch(error){message.textContent=`Could not open the browser workspace: ${error.message}`;}
