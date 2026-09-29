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
  if(url.origin!==self.location.origin||!dynamic.test(url.pathname))return;
  event.respondWith(handle(event));
});

async function handle(event){
  try{return await handleRequest(event);}
  catch(error){return new Response(JSON.stringify({error:String(error.stack||error)}),{status:500,headers:{'Content-Type':'application/json'}});}
}

async function handleRequest(event){
  const url=new URL(event.request.url);
  const source=event.clientId?await self.clients.get(event.clientId):null;
  const nestedOwner=source?.frameType==='nested'?new URL(source.url).searchParams.get('owner'):null;
  const owned=nestedOwner&&owners.get(nestedOwner)?await self.clients.get(owners.get(nestedOwner)):null;
  const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
  const client=source?.frameType==='top-level'?source:owned
    ||windows.find(item=>item.frameType==='top-level'&&new URL(item.url).pathname==='/')
    ||windows.find(item=>item.frameType==='top-level');
  if(!client)return new Response(JSON.stringify({error:'Open Bulk Proxy Forge in its browser tab.'}),{status:503,headers:{'Content-Type':'application/json'}});

  const channel=new MessageChannel();
  const body=event.request.method==='POST'?await event.request.arrayBuffer():null;
  const id=crypto.randomUUID();
  const result=new Promise(resolve=>{
    channel.port1.onmessage=e=>resolve(e.data);
  });
  client.postMessage({type:'request',id,method:event.request.method,url:new URL(event.request.url).pathname+url.search,
                      headers:Object.fromEntries(event.request.headers),body},[channel.port2,...(body?[body]:[])]);
  const response=await result;
  if(response.type==='error')return new Response(JSON.stringify({error:response.message}),{status:500,headers:{'Content-Type':'application/json'}});
  const headers=new Headers(response.headers||{});
  headers.set('Content-Type',response.mime);
  if(response.filename)headers.set('Content-Disposition',`attachment; filename="${response.filename}"`);
  return new Response(response.body,{status:response.status,headers});
}
