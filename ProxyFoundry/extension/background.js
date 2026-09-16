/* Final ZIP transport only. CardConjurer runs in the workspace, not this extension. */
importScripts('transfer-protocol.js');
const VERSION='1.1.0';
const TARGET='https://www.tcgplaytest.com';
const {CHUNK_BYTES:CHUNK, metadata:validateMetadata, batchAt}=ProxyFoundryTransfer;
function localOrigin(url){try{const u=new URL(url);if(u.protocol==='http:'&&['127.0.0.1','localhost'].includes(u.hostname)&&u.port&&!u.username&&!u.password)return u.origin;}catch{}throw new Error('The order must come from a local Bulk Proxy Forge workspace.');}
function validateTransfer(value,sender){
  const origin=localOrigin(sender.url||sender.tab?.url||'');
  if(!Number.isInteger(sender.tab?.id)||sender.frameId!==0)throw new Error('Open the order from the main Bulk Proxy Forge tab.');
  if(!value||value.origin!==origin||!/^[-a-f0-9]{36}$/.test(value.id)||!/^[-_A-Za-z0-9]{32,100}$/.test(value.secret))throw new Error('Invalid print transfer. Rebuild or reopen the order.');
  return {origin,id:value.id,secret:value.secret,expires:Date.now()+60*60*1000,sourceTab:sender.tab.id};
}
async function getTransfer(sender){
  const u=new URL(sender.url||sender.tab?.url||'');
  if(u.origin!==TARGET||sender.frameId!==0||!Number.isInteger(sender.tab?.id))throw new Error('Print data is available only to its authorized TCGPlaytest tab.');
  const key='transfer:'+sender.tab.id;const result=await chrome.storage.session.get(key);const t=result[key];
  if(!t||t.expires<Date.now()){await chrome.storage.session.remove(key);throw new Error('Transfer expired. Open this order again from Bulk Proxy Forge.');}
  // Renew an active transfer without a session write for every 1 MB message.
  if(t.expires-Date.now()<30*60*1000){t.expires=Date.now()+60*60*1000;await chrome.storage.session.set({[key]:t});}
  return t;
}
async function request(t,kind,offset,batch){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30000);
  try{
    const headers={'X-Proxy-Transfer-Token':t.secret};
    let path=kind;
    if(kind==='zip'){
      if(!Number.isSafeInteger(offset)||offset<0||offset>=batch.zipBytes)throw new Error('Invalid order chunk.');
      headers.Range=`bytes=${offset}-${Math.min(offset+CHUNK,batch.zipBytes)-1}`;
      path=t.legacy?'zip':`batches/${batch.index}/zip`;
    }
    const r=await fetch(t.origin+'/api/transfer/'+t.id+'/'+path,{headers,signal:controller.signal,cache:'no-store',credentials:'omit'});
    if(!r.ok){let message='';try{message=(await r.json()).error||'';}catch{}throw new Error(message||'Local order transfer failed: HTTP '+r.status);}
    if(kind==='metadata')return r.json();
    if(r.status!==206)throw new Error('Expected a bounded order download range.');
    const bytes=new Uint8Array(await r.arrayBuffer());
    const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(r.headers.get('Content-Range')||'');
    if(bytes.length!==Math.min(CHUNK,batch.zipBytes-offset)||!range||Number(range[1])!==offset||
       Number(range[2])-offset+1!==bytes.length||Number(range[3])!==batch.zipBytes)throw new Error('Order range did not match the requested batch chunk.');
    let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return {base64:btoa(text),batch:batch.index,offset,length:bytes.length,total:batch.zipBytes};
  }catch(e){if(e.name==='AbortError')throw new Error('Local order transfer timed out. Keep the Bulk Proxy Forge launcher running.');throw e;}finally{clearTimeout(timer);}
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(!['PF_WORKSPACE_OPEN_ORDER','PF_ORDER_METADATA','PF_ORDER_CHUNK','PF_ORDER_FINISHED'].includes(message?.type))return;
  (async()=>{
    try{
      if(message.type==='PF_WORKSPACE_OPEN_ORDER'){
        const t=validateTransfer(message.transfer,sender);const meta=validateMetadata(await request(t,'metadata'));
        const tab=await chrome.tabs.create({url:'about:blank',active:true});
        try{await chrome.storage.session.set({['transfer:'+tab.id]:{...t,...meta}});await chrome.tabs.update(tab.id,{url:TARGET+'/?view=design&proxyFoundryOrder='+encodeURIComponent(t.id)});}catch(e){await chrome.tabs.remove(tab.id).catch(()=>{});throw e;}
        respond({ok:true,tabId:tab.id,count:meta.count,batchCount:meta.batches.length});return;
      }
      const t=await getTransfer(sender);
      if(message.type==='PF_ORDER_METADATA'){respond({ok:true,protocol:2,count:t.count,zipBytes:t.zipBytes,batches:t.batches,version:VERSION});return;}
      if(message.type==='PF_ORDER_CHUNK'){
        const batch=batchAt(t,message.batch??0);
        const chunk=await request(t,'zip',message.offset,batch);respond({ok:true,...chunk});return;
      }
      if(message.type==='PF_ORDER_FINISHED'){await chrome.storage.session.remove('transfer:'+sender.tab.id);respond({ok:true});}
    }catch(e){respond({ok:false,error:e.message||String(e)});}
  })();return true;
});
chrome.tabs.onRemoved.addListener(tabId=>chrome.storage.session.remove('transfer:'+tabId).catch(()=>{}));
