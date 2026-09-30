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
  navigator.serviceWorker.controller.postMessage({type:'owner',owner});
  const worker=new Worker('/web/engine-worker.js',{type:'module'});
  const {savedFolder}=await import('/web/storage-choice.js');
  const folder=await savedFolder();
  const pending=new Map();
  let readyResolve;
  let readyReject;
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});

  worker.onmessage=event=>{
    const data=event.data;
    if(data.type==='status')message.textContent=data.message;
    if(data.type==='ready')readyResolve();
    if(data.type==='fatal')readyReject(new Error(data.message));
    if(data.type==='response'||data.type==='error'){
      const port=pending.get(data.id);
      pending.delete(data.id);
      if(port)port.postMessage(data,data.body?[data.body.buffer]:[]);
    }
  };
  worker.postMessage({type:'start',folder});

  navigator.serviceWorker.addEventListener('message',async event=>{
    const data=event.data;
    if(data.type!=='request')return;
    const port=event.ports[0];
    try{
      await ready;
      pending.set(data.id,port);
      worker.postMessage(data,data.body?[data.body]:[]);
    }
    catch(error){port.postMessage({type:'error',id:data.id,message:String(error)});}
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
