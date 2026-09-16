/* Final ZIP transport only. CardConjurer runs in the local workspace, not this extension. */
importScripts('transfer-protocol.js');
const VERSION=PF_TRANSFER.VERSION;
const TARGET='https://www.tcgplaytest.com';
const CHUNK=1024*1024;
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
  // Large active transfers can exceed an hour; expire after inactivity instead.
  if(t.expires-Date.now()<55*60*1000){t.expires=Date.now()+60*60*1000;await chrome.storage.session.set({[key]:t});}
  return t;
}
async function request(t,kind,offset,batch=0){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30000);
  try{
    const headers={'X-Proxy-Transfer-Token':t.secret};
    if(kind==='zip'){if(!Number.isSafeInteger(offset)||offset<0)throw new Error('Invalid order chunk.');headers.Range=`bytes=${offset}-${offset+CHUNK-1}`;}
    const resource=kind==='zip'&&t.protocol===2?`batches/${batch}/zip`:kind;
    const r=await fetch(t.origin+'/api/transfer/'+t.id+'/'+resource,{headers,signal:controller.signal,cache:'no-store',credentials:'omit'});
    if(!r.ok){let message='';try{message=(await r.json()).error||'';}catch{}throw new Error(message||'Local order transfer failed: HTTP '+r.status);}
    if(kind==='metadata')return r.json();
    if(r.status!==206)throw new Error('Expected a bounded order download range.');
    const bytes=new Uint8Array(await r.arrayBuffer());if(bytes.length>CHUNK||!bytes.length)throw new Error('Invalid order chunk size.');
    const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(r.headers.get('Content-Range')||'');
    if(!range||Number(range[1])!==offset||Number(range[2])-offset+1!==bytes.length)throw new Error('Order range did not match requested chunk.');
    let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return {base64:btoa(text),batch,offset,length:bytes.length,total:Number(range[3])};
  }catch(e){if(e.name==='AbortError')throw new Error('Local order transfer timed out. Keep the Bulk Proxy Forge launcher running.');throw e;}finally{clearTimeout(timer);}
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(!['PF_WORKSPACE_OPEN_ORDER','PF_ORDER_METADATA','PF_ORDER_CHUNK','PF_ORDER_FINISHED'].includes(message?.type))return;
  (async()=>{
    try{
      if(message.type==='PF_WORKSPACE_OPEN_ORDER'){
        const t=validateTransfer(message.transfer,sender);const meta=PF_TRANSFER.normalize(await request(t,'metadata'));
        const tab=await chrome.tabs.create({url:'about:blank',active:true});
        try{await chrome.storage.session.set({['transfer:'+tab.id]:{...t,...meta}});await chrome.tabs.update(tab.id,{url:TARGET+'/?view=design&proxyFoundryOrder='+encodeURIComponent(t.id)});}catch(e){await chrome.tabs.remove(tab.id).catch(()=>{});throw e;}
        respond({ok:true,tabId:tab.id,count:meta.count,batchCount:meta.batches.length});return;
      }
      const t=await getTransfer(sender);
      if(message.type==='PF_ORDER_METADATA'){respond({ok:true,protocol:t.protocol,count:t.count,zipBytes:t.zipBytes,batches:t.batches,filename:'BulkProxyForge_Order.zip',version:VERSION});return;}
      if(message.type==='PF_ORDER_CHUNK'){
        const index=message.batch??0;
        if(!Number.isSafeInteger(index)||index<0||index>=t.batches.length)throw new Error('Requested batch is outside the saved order.');
        const batch=t.batches[index];
        if(!Number.isSafeInteger(message.offset)||message.offset<0||message.offset>=batch.zipBytes)throw new Error('Requested chunk is outside the saved batch.');
        const chunk=await request(t,'zip',message.offset,index);if(chunk.total!==batch.zipBytes)throw new Error('The order changed during transfer. Stop and reopen it.');respond({ok:true,...chunk});return;
      }
      if(message.type==='PF_ORDER_FINISHED'){await chrome.storage.session.remove('transfer:'+sender.tab.id);respond({ok:true});}
    }catch(e){respond({ok:false,error:e.message||String(e)});}
  })();return true;
});
chrome.tabs.onRemoved.addListener(tabId=>chrome.storage.session.remove('transfer:'+tabId).catch(()=>{}));
