/* Final ZIP transport only. CardConjurer runs in the local workspace, not this extension. */
const VERSION='1.1.0';
const TARGET='https://www.tcgplaytest.com';
const CHUNK=1024*1024;
function localOrigin(url){try{const u=new URL(url);if(u.protocol==='http:'&&['127.0.0.1','localhost'].includes(u.hostname)&&u.port&&!u.username&&!u.password)return u.origin;}catch{}throw new Error('The order must come from a local Proxy Foundry workspace.');}
function validateTransfer(value,sender){
  const origin=localOrigin(sender.url||sender.tab?.url||'');
  if(!Number.isInteger(sender.tab?.id)||sender.frameId!==0)throw new Error('Open the order from the main Proxy Foundry tab.');
  if(!value||value.origin!==origin||!/^[-a-f0-9]{36}$/.test(value.id)||!/^[-_A-Za-z0-9]{32,100}$/.test(value.secret))throw new Error('Invalid print transfer. Rebuild or reopen the order.');
  return {origin,id:value.id,secret:value.secret,expires:Date.now()+60*60*1000,sourceTab:sender.tab.id};
}
async function getTransfer(sender){
  const u=new URL(sender.url||sender.tab?.url||'');
  if(u.origin!==TARGET||sender.frameId!==0||!Number.isInteger(sender.tab?.id))throw new Error('Print data is available only to its authorized TCGPlaytest tab.');
  const key='transfer:'+sender.tab.id;const result=await chrome.storage.session.get(key);const t=result[key];
  if(!t||t.expires<Date.now()){await chrome.storage.session.remove(key);throw new Error('Transfer expired. Open this order again from Proxy Foundry.');}
  t.expires=Date.now()+60*60*1000;await chrome.storage.session.set({[key]:t});return t;
}
async function request(t,kind,offset,batch){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30000);
  try{
    const headers={'X-Proxy-Transfer-Token':t.secret};
    if(kind==='zip'){if(!Number.isSafeInteger(offset)||offset<0)throw new Error('Invalid order chunk.');headers.Range=`bytes=${offset}-${offset+CHUNK-1}`;}
    const r=await fetch(t.origin+'/api/transfer/'+t.id+'/'+kind+(Number.isSafeInteger(batch)?'?batch='+batch:''),{headers,signal:controller.signal,cache:'no-store',credentials:'omit'});
    if(!r.ok){let message='';try{message=(await r.json()).error||'';}catch{}throw new Error(message||'Local order transfer failed: HTTP '+r.status);}
    if(kind==='metadata')return r.json();
    if(r.status!==206)throw new Error('Expected a bounded order download range.');
    const bytes=new Uint8Array(await r.arrayBuffer());if(bytes.length>CHUNK||!bytes.length)throw new Error('Invalid order chunk size.');
    const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(r.headers.get('Content-Range')||'');
    if(!range||Number(range[1])!==offset||Number(range[2])-offset+1!==bytes.length)throw new Error('Order range did not match requested chunk.');
    let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return {base64:btoa(text),offset,length:bytes.length,total:Number(range[3])};
  }catch(e){if(e.name==='AbortError')throw new Error('Local order transfer timed out. Keep the Proxy Foundry launcher running.');throw e;}finally{clearTimeout(timer);}
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(!['PF_WORKSPACE_OPEN_ORDER','PF_ORDER_METADATA','PF_ORDER_CHUNK','PF_ORDER_FINISHED'].includes(message?.type))return;
  (async()=>{
    try{
      if(message.type==='PF_WORKSPACE_OPEN_ORDER'){
        const t=validateTransfer(message.transfer,sender);const meta=await request(t,'metadata');
        if(!Number.isSafeInteger(meta.count)||meta.count<1||!Number.isSafeInteger(meta.zipBytes)||meta.zipBytes<22)throw new Error('Invalid paired-order package.');
        if(meta.protocolVersion===2){
          if(!Array.isArray(meta.batches)||!meta.batches.length||meta.batches.length>meta.count)throw new Error('Invalid ZIP batches.');
          let count=0;
          for(const [i,b] of meta.batches.entries()){
            if(b.index!==i||!Number.isSafeInteger(b.count)||b.count<1||!Number.isSafeInteger(b.zipBytes)||b.zipBytes<22||b.zipBytes>1024**3)throw new Error('Invalid or oversized ZIP batch.');
            count+=b.count;
          }
          if(count!==meta.count)throw new Error('ZIP batches do not match the saved card count.');
        }else if(meta.zipBytes>1024**3)throw new Error('Update Bulk Proxy Forge to enable automatic 1 GB ZIP batches.');
        const tab=await chrome.tabs.create({url:'about:blank',active:true});
        try{await chrome.storage.session.set({['transfer:'+tab.id]:{...t,...meta}});await chrome.tabs.update(tab.id,{url:TARGET+'/?view=design&proxyFoundryOrder='+encodeURIComponent(t.id)});}catch(e){await chrome.tabs.remove(tab.id).catch(()=>{});throw e;}
        respond({ok:true,tabId:tab.id,count:meta.count});return;
      }
      const t=await getTransfer(sender);
      if(message.type==='PF_ORDER_METADATA'){respond({ok:true,count:t.count,zipBytes:t.zipBytes,filename:t.filename||'Proxy_Foundry_Order.zip',version:VERSION,protocolVersion:t.protocolVersion,batches:t.batches});return;}
      if(message.type==='PF_ORDER_CHUNK'){
        const batch=t.protocolVersion===2?message.batch:undefined;
        if(t.protocolVersion===2&&(!Number.isSafeInteger(batch)||batch<0||batch>=t.batches.length))throw new Error('Invalid ZIP batch.');
        const total=t.protocolVersion===2?t.batches[batch].zipBytes:t.zipBytes;
        if(message.offset>=total)throw new Error('Requested chunk is outside the saved batch.');
        const chunk=await request(t,'zip',message.offset,batch);if(chunk.total!==total)throw new Error('The order changed during transfer. Stop and reopen it.');respond({ok:true,...chunk,batch});return;
      }
      if(message.type==='PF_ORDER_FINISHED'){await chrome.storage.session.remove('transfer:'+sender.tab.id);respond({ok:true});}
    }catch(e){respond({ok:false,error:e.message||String(e)});}
  })();return true;
});
chrome.tabs.onRemoved.addListener(tabId=>chrome.storage.session.remove('transfer:'+tabId).catch(()=>{}));
