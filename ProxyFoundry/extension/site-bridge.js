(() => {
  if(window.__proxyFoundryWorkspaceBridge)return;
  if(!document.querySelector('meta[name="proxy-foundry"][content="workspace-v1"]'))return;
  window.__proxyFoundryWorkspaceBridge=true;
  const post=(type,data={})=>window.postMessage({...data,source:'proxy-foundry-helper',type,version:'1.2.0',capabilities:['paired-zip-batches']},location.origin);
  chrome.runtime.onMessage.addListener((message,sender,respond)=>{
    if(message?.type!=='PF_BROWSER_TRANSFER')return;
    (async()=>{
      try{
        if(!/^[-a-f0-9]{36}$/.test(message.id)||!/^[-_A-Za-z0-9]{32,100}$/.test(message.secret)||!['metadata','zip'].includes(message.kind))throw new Error('Invalid print transfer.');
        const requestId=crypto.randomUUID();
        const reply=await new Promise((resolve,reject)=>{
          const timer=setTimeout(()=>{window.removeEventListener('message',listener);reject(new Error('The browser workspace did not respond.'));},30000);
          function listener(event){
            if(event.source!==window||event.origin!==location.origin||event.data?.source!=='proxy-foundry-workspace'||event.data.type!=='PF_TRANSFER_REPLY'||event.data.requestId!==requestId)return;
            clearTimeout(timer);window.removeEventListener('message',listener);resolve(event.data);
          }
          window.addEventListener('message',listener);
          post('PF_TRANSFER_REQUEST',{requestId,id:message.id,secret:message.secret,kind:message.kind,offset:message.offset,batch:message.batch});
        });
        respond(reply.ok?{ok:true,data:reply.data}:{ok:false,error:reply.error||'Saved order could not be read.'});
      }catch(error){respond({ok:false,error:error.message||String(error)});}
    })();return true;
  });
  let opening=false;
  window.addEventListener('message',async e=>{
    if(e.source!==window||e.origin!==location.origin||e.data?.source!=='proxy-foundry-workspace')return;
    if(e.data.type==='PF_WORKSPACE_PING'){post('PF_WORKSPACE_PONG');return;}
    if(e.data.type!=='PF_WORKSPACE_OPEN'||opening)return;
    opening=true;
    try{const r=await chrome.runtime.sendMessage({type:'PF_WORKSPACE_OPEN_ORDER',transfer:e.data.transfer});if(!r?.ok)throw new Error(r?.error||'Could not open the order.');post('PF_WORKSPACE_OPENED',{tabId:r.tabId});}
    catch(err){post('PF_WORKSPACE_ERROR',{error:err.message||String(err)});}finally{opening=false;}
  });
  post('PF_WORKSPACE_PONG');
})();
