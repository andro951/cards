import {$,state,api,blobRequest,job,activity,endActivity,sleep,toast} from './ui.js';
let activeFrame=null;
export async function renderDecks(ids,{onUpdate=async()=>{},prepare=true,force=false}={}){
  if(state.busy)throw new Error('Another task is running. Wait for it or cancel first.');
  state.busy=true;let cancelled=false,listener=null,rejectPending=null,pending=null,ready=false,readyResolve,readyReject,ping;
  const origin=state.bootstrap.runtimeOrigin;
  const cleanup=()=>{clearInterval(ping);if(listener)window.removeEventListener('message',listener);activeFrame?.remove();activeFrame=null;};
  try{
    if(prepare)for(const id of ids){const before=await api('/api/decks/'+id);force=force||!!before.upgradeRequired;await job('/api/decks/'+id+'/prepare',{}, {label:'Prepare deck'});await onUpdate(id);}
    const plan=await api('/api/render-sessions',{deckIds:ids,force});
    activity('Render deck','Render plan',`Pipeline ${plan.pipelineVersion||state.bootstrap.pipelineVersion||'unknown'} · force=${plan.force?'yes':'no'} · ${plan.targets.length} queued · ${plan.cached} cached`,0,plan.targets.length);
    if(!plan.targets.length){if(plan.errors.length)throw new Error(plan.errors.join('\n'));endActivity('All images are already up to date');toast('Cached images reused. No rendering needed.');return;}
    if(force)activity('Render deck','Pipeline upgrade','Ignoring cached PNGs and rebuilding every prepared face…',0,plan.targets.length);
    await job('/api/runtime/prepare',{}, {label:'Load CardConjurer'});
    $('#activity-cancel').textContent='Cancel';$('#activity-cancel').disabled=false;$('#activity-cancel').onclick=()=>{cancelled=true;rejectPending?.(new Error('Rendering cancelled. Completed images are saved.'));readyReject?.(new Error('Rendering cancelled.'));cleanup();};
    activity('Render deck','Starting native renderer','Loading the pinned CardConjurer runtime…',0,plan.targets.length);
    const readyPromise=new Promise((r,j)=>{readyResolve=r;readyReject=j;});
    listener=event=>{
      if(event.origin!==origin||event.source!==activeFrame?.contentWindow||event.data?.source!=='pf-native-runtime')return;
      const m=event.data;
      if(m.type==='ready'){ready=true;readyResolve();return;}
      if(m.type==='failed'&&!ready){readyReject(new Error(m.error));return;}
      if(!pending||m.key!==pending.key)return;
      if(m.type==='progress'){activity('Render deck',pending.name,m.message,pending.index,plan.targets.length);return;}
      if(m.type==='failed')pending.reject(new Error(m.error));
      if(m.type==='rendered'){if(!(m.blob instanceof Blob)||m.blob.size===0)pending.reject(new Error('Native renderer returned an empty PNG.'));else pending.resolve(m);}
    };
    window.addEventListener('message',listener);
    activeFrame=document.createElement('iframe');activeFrame.className='render-frame';activeFrame.title='Isolated native CardConjurer renderer';activeFrame.setAttribute('sandbox','allow-scripts allow-same-origin');
    activeFrame.src=origin+'/runtime/host?parent='+encodeURIComponent(location.origin);document.body.append(activeFrame);
    ping=setInterval(()=>activeFrame?.contentWindow.postMessage({source:'pf-app',type:'ping'},origin),800);
    await withTimeout(readyPromise,65000,'The native renderer did not start. Check Diagnostics in Settings.');clearInterval(ping);
    for(let i=0;i<plan.targets.length;i++){
      if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
      const t=plan.targets[i];activity('Render deck',t.name,'Loading saved face…',i,plan.targets.length);
      const detail=await api('/api/render-sessions/'+plan.id+'/'+t.key);
      activity('Render deck',t.name,`Fresh render · key ${t.key.slice(0,12)} · ${detail.data.version||'unknown'} · set symbol zoom=${detail.data.setSymbolZoom??'n/a'} x=${detail.data.setSymbolX??'n/a'} y=${detail.data.setSymbolY??'n/a'}`,i,plan.targets.length);
      const promise=new Promise((resolve,reject)=>{pending={...t,index:i,resolve,reject};rejectPending=reject;});
      activeFrame.contentWindow.postMessage({source:'pf-app',type:'render',key:t.key,data:detail.data},origin);
      const output=await withTimeout(promise,150000,t.name+': native render timed out. Retry will keep completed images.');
      pending=null;rejectPending=null;
      await blobRequest('/api/render-sessions/'+plan.id+'/'+t.key,output.blob,'image/png');
      activity('Render deck',t.name,'PNG saved · '+output.width+' × '+output.height,i+1,plan.targets.length);
      await onUpdate();
    }
    if(plan.errors.length){endActivity('Rendered available cards; some need attention',true);throw new Error(plan.errors.join('\n'));}
    endActivity('All card images saved');toast('Rendering complete. Your decks are ready for order review.');
  }catch(e){api('/api/client-error',{error:'Native render: '+(e.stack||e.message)}).catch(()=>{});endActivity(e.message,true);throw e;}finally{cleanup();state.busy=false;await onUpdate();}
}
function withTimeout(p,ms,msg){return new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error(msg)),ms);p.then(x=>{clearTimeout(t);resolve(x)},e=>{clearTimeout(t);reject(e)});});}
