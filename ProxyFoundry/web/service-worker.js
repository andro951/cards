const basePath='';
const dynamic=/^\/(api|runtime|js|img|fonts|css|creator)\//;
const owners=new Map();

self.addEventListener('message',event=>{
  if(event.data?.type==='owner'&&event.source?.id&&typeof event.data.owner==='string'){
    owners.set(event.data.owner,event.source.id);
  }
});

self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));

self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin)return;
  if(basePath&&/^\/(site|web)\//.test(url.pathname)){event.respondWith(fetch(basePath+url.pathname+url.search));return;}
  const path=basePath&&url.pathname.startsWith(basePath+'/')?url.pathname.slice(basePath.length):url.pathname;
  if(!dynamic.test(path)&&path!=='/workspace-io'&&path!=='/github-setup-fetch')return;
  event.respondWith(handle(event));
});

async function handle(event){
  try{return await handleRequest(event);}
  catch(error){return new Response(JSON.stringify({error:String(error.stack||error)}),{status:500,headers:{'Content-Type':'application/json'}});}
}

async function handleRequest(event){
  const url=new URL(event.request.url);
  const route=basePath&&url.pathname.startsWith(basePath+'/')?url.pathname.slice(basePath.length):url.pathname;
  if(route===`/github-setup-fetch`) {
    const urls=await event.request.json();
    if(event.request.method!==`POST`||!Array.isArray(urls)||urls.length>6||urls.some(value=>{
      const remote=new URL(value);
      return remote.protocol!==`https:`||remote.hostname!==`raw.githubusercontent.com`||remote.username||remote.password||remote.port;
    }))
      throw new Error(`Invalid GitHub setup batch.`);

    const files=await Promise.all(urls.map(async address=>{
      const response=await fetch(address);
      if(!response.ok)
        throw new Error(`HTTP ${response.status} ${address}`);

      if(Number(response.headers.get(`Content-Length`))>64*1024*1024)
        throw new Error(`GitHub setup file is too large.`);

      const bytes=new Uint8Array(await response.arrayBuffer());
      if(!bytes.length||bytes.length>64*1024*1024)
        throw new Error(`GitHub setup file is empty or too large.`);

      return {bytes,mime:response.headers.get(`Content-Type`)||`application/octet-stream`};
    }));
    const header=new TextEncoder().encode(JSON.stringify(files.map(file=>({size:file.bytes.length,mime:file.mime}))));
    const size=new Uint8Array(4);new DataView(size.buffer).setUint32(0,header.length);
    return new Response(new Blob([size,header,...files.map(file=>file.bytes)]),{headers:{'Content-Type':`application/octet-stream`}});
  }

  const source=event.clientId?await self.clients.get(event.clientId):null;
  const nestedOwner=url.searchParams.get('owner')||(source?.frameType==='nested'?new URL(source.url).searchParams.get('owner'):null);
  const owned=nestedOwner&&owners.get(nestedOwner)?await self.clients.get(owners.get(nestedOwner)):null;
  let client=source?.frameType==='top-level'?source:owned;
  if(!client&&nestedOwner){
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    const candidates=await Promise.all(windows.filter(item=>item.frameType==='top-level').map(async item=>{
      const channel=new MessageChannel();
      const answer=await new Promise(resolve=>{
        const timer=setTimeout(()=>{channel.port1.close();resolve(null);},2000);
        channel.port1.onmessage=event=>{clearTimeout(timer);channel.port1.close();resolve(event.data?.owner);};
        item.postMessage({type:'owner-probe'},[channel.port2]);
      });
      if(answer===nestedOwner){owners.set(answer,item.id);return item;}
      return null;
    }));
    client=candidates.find(Boolean);
  }
  if(!client)return new Response(JSON.stringify({error:'Open Bulk Proxy Forge in its browser tab.'}),{status:503,headers:{'Content-Type':'application/json'}});

  const channel=new MessageChannel();
  const body=event.request.method==='POST'?await event.request.arrayBuffer():null;
  const id=crypto.randomUUID();
  const result=new Promise(resolve=>{
    const timer=setTimeout(()=>{channel.port1.close();resolve({type:'error',message:'The workspace did not respond within two minutes. Download browser diagnostics before reloading; completed images are saved.'});},120000);
    channel.port1.onmessage=e=>{clearTimeout(timer);channel.port1.close();resolve(e.data);};
    channel.port1.onmessageerror=()=>{clearTimeout(timer);channel.port1.close();resolve({type:'error',message:'The workspace response could not be read.'});};
  });
  client.postMessage({type:'request',id,method:event.request.method,url:(basePath&&url.pathname.startsWith(basePath+'/')?url.pathname.slice(basePath.length):url.pathname)+url.search,
                      headers:Object.fromEntries(event.request.headers),body},[channel.port2,...(body?[body]:[])]);
  const response=await result;
  if(response.type==='error')return new Response(JSON.stringify({error:response.message}),{status:500,headers:{'Content-Type':'application/json'}});
  const headers=new Headers(response.headers||{});
  headers.set('Content-Type',response.mime);
  if(response.filename)headers.set('Content-Disposition',`attachment; filename="${response.filename}"`);
  return new Response(response.body,{status:response.status,headers});
}
