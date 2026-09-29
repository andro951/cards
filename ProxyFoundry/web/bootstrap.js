const message=document.querySelector('#main');
const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});
await navigator.serviceWorker.ready;
if(!navigator.serviceWorker.controller){
  message.textContent='Opening browser workspace…';
  location.reload();
}
else{
  const worker=new Worker('/web/engine-worker.js',{type:'module'});
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

  try{
    await ready;
    await import('/site/app.js');
  }
  catch(error){message.textContent=`Could not open the browser workspace: ${error.message}`;}
}
