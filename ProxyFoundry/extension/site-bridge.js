(() => {
  if(window.__proxyFoundryWorkspaceBridge)return;
  if(!document.querySelector('meta[name="proxy-foundry"][content="workspace-v1"]'))return;
  window.__proxyFoundryWorkspaceBridge=true;
  const post=(type,data={})=>window.postMessage({...data,source:'proxy-foundry-helper',type,version:'1.1.0',capabilities:['paired-zip-batches']},location.origin);
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
