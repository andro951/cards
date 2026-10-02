import {recordDiagnostic} from './diagnostics.js';
import {$,state,api,blobRequest,job,activity,endActivity,sleep,toast} from './ui.js';
let activeFrame=null;

function logTiming(stage,started,outcome,detail={}){
  const seconds=(performance.now()-started)/1000;
  if(seconds<.1)return;
  const diagnostic={stage,seconds:Number(seconds.toFixed(4)),outcome,...detail};
  recordDiagnostic('timing',JSON.stringify(diagnostic));
  api('/api/render-diagnostic',{stage:'timing',diagnostic}).catch(error=>recordDiagnostic('timing log error',error.message));
}
async function measure(stage,operation,detail={}){
  const started=performance.now();let outcome='failed';
  try{
    const result=await operation();outcome='ok';return result;
  }finally{logTiming(stage,started,outcome,detail);}
}


async function runRenderPlan(plan,{label='Render deck',onUpdate=async()=>{},onImage=null,signal=null,idleMessage='All images are already up to date',idleToast='Cached images reused. No rendering needed.',successMessage='All card images saved',successToast='Rendering complete. Your decks are ready for order review.'}={}){
  const started=performance.now();let outcome='failed';
  if(state.busy)throw new Error('Another task is running. Wait for it or cancel first.');
  state.busy=true;let cancelled=false,preparing=false,listener=null,rejectPending=null,pending=null,ready=false,readyResolve,readyReject,ping;
  const origin=state.bootstrap.runtimeOrigin;
  const cleanup=()=>{clearInterval(ping);if(listener)window.removeEventListener('message',listener);activeFrame?.remove();activeFrame=null;};
  const cancel=()=>{
    if(cancelled)return;
    cancelled=true;
    if(preparing&&$('#activity-cancel').textContent==='Cancel')$('#activity-cancel').click();
    const error=new Error('Rendering cancelled. Completed images are saved.');
    rejectPending?.(error);readyReject?.(error);cleanup();
  };
  signal?.addEventListener('abort',cancel,{once:true});
  try{
    if(signal?.aborted)cancel();
    if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
    activity(label,'Render plan',`Pipeline ${plan.pipelineVersion||state.bootstrap.pipelineVersion||'unknown'} · force=${plan.force?'yes':'no'} · ${plan.targets.length} queued · ${plan.cached} cached`,0,plan.targets.length);
    if(!plan.targets.length){if(plan.errors.length)throw new Error(plan.errors.join('\n'));outcome='cached';endActivity(idleMessage);toast(idleToast);return;}
    if(plan.force)activity(label,'Pipeline upgrade','Ignoring cached PNGs and rebuilding every prepared face…',0,plan.targets.length);
    preparing=true;
    await measure('runtime.prepare',()=>job('/api/runtime/prepare',{}, {label:'Load CardConjurer'}));
    preparing=false;
    if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
    $('#activity-cancel').textContent='Cancel';$('#activity-cancel').disabled=false;$('#activity-cancel').onclick=cancel;
    activity(label,'Starting native renderer','Loading the pinned CardConjurer runtime…',0,plan.targets.length);
    const readyPromise=new Promise((r,j)=>{readyResolve=r;readyReject=j;});
    listener=event=>{
      if(event.origin!==origin||event.source!==activeFrame?.contentWindow||event.data?.source!=='pf-native-runtime')return;
      const m=event.data;
      if(m.type==='ready'){ready=true;readyResolve();return;}
      if(m.type==='failed'&&!ready){readyReject(new Error(m.error));return;}
      if(m.type==='diagnostic'){api('/api/render-diagnostic',{key:m.key,stage:m.stage,diagnostic:m.diagnostic}).catch(()=>{});return;}
      if(!pending||m.key!==pending.key)return;
      if(m.type==='progress'){activity(label,pending.name,m.message,pending.index,plan.targets.length);return;}
      if(m.type==='failed')pending.reject(new Error(m.error));
      if(m.type==='rendered'){if(!(m.blob instanceof Blob)||m.blob.size===0)pending.reject(new Error('Native renderer returned an empty PNG.'));else pending.resolve(m);}
    };
    window.addEventListener('message',listener);
    activeFrame=document.createElement('iframe');activeFrame.className='render-frame';activeFrame.title='Isolated native CardConjurer renderer';activeFrame.setAttribute('sandbox','allow-scripts allow-same-origin');
    activeFrame.src=origin+(window.__pfBasePath||'')+'/runtime/host?parent='+encodeURIComponent(location.origin)+'&owner='+encodeURIComponent(window.__pfOwner||'');document.body.append(activeFrame);
    ping=setInterval(()=>activeFrame?.contentWindow.postMessage({source:'pf-app',type:'ping'},origin),800);
    await measure('runtime.start',()=>withTimeout(readyPromise,65000,'The native renderer did not start. Check Diagnostics in Settings.'));clearInterval(ping);
    for(let i=0;i<plan.targets.length;i++){
      if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
      const t=plan.targets[i];activity(label,t.name,'Loading saved face…',i,plan.targets.length);
      const detail=await measure('render.load-face',()=>api('/api/render-sessions/'+plan.id+'/'+t.key),{card:t.name,key:t.key});
      if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
      activity(label,t.name,`Fresh render · key ${t.key.slice(0,12)} · ${detail.data.version||'unknown'} · set symbol zoom=${detail.data.setSymbolZoom??'n/a'} x=${detail.data.setSymbolX??'n/a'} y=${detail.data.setSymbolY??'n/a'}`,i,plan.targets.length);
      const promise=new Promise((resolve,reject)=>{pending={...t,index:i,resolve,reject};rejectPending=reject;});
      activeFrame.contentWindow.postMessage({source:'pf-app',type:'render',key:t.key,data:detail.data},origin);
      const output=await measure('render.native',()=>withTimeout(promise,150000,t.name+': native render timed out. Retry will keep completed images.'),{card:t.name,key:t.key});
      pending=null;rejectPending=null;
      if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
      await measure('render.save',()=>onImage?onImage(t,output.blob):blobRequest('/api/render-sessions/'+plan.id+'/'+t.key,output.blob,'image/png'),{card:t.name,key:t.key,bytes:output.blob.size});
      activity(label,t.name,(onImage?'Preview ready · ':'PNG saved · ')+output.width+' × '+output.height,i+1,plan.targets.length);
      await onUpdate();
    }
    if(plan.errors.length){endActivity('Rendered available cards; some need attention',true);throw new Error(plan.errors.join('\n'));}
    outcome='ok';endActivity(successMessage);toast(successToast);
  }catch(e){
    if(cancelled)$('#activity').classList.add('hidden');
    else{api('/api/client-error',{error:'Native render: '+(e.stack||e.message)}).catch(()=>{});endActivity(e.message,true);}
    throw e;
  }finally{logTiming('render.total',started,cancelled?'cancelled':outcome,{cards:plan.targets.length,cached:plan.cached});signal?.removeEventListener('abort',cancel);cleanup();state.busy=false;await onUpdate();}
}

export async function renderDecks(ids,{onUpdate=async()=>{},prepare=true,force=false}={}){
  if(prepare){
    for(const id of ids){
      await job('/api/decks/'+id+'/prepare',{}, {label:'Prepare deck'});await onUpdate(id);
    }
  }
  const plan=await api('/api/render-sessions',{deckIds:ids,force});
  return runRenderPlan(plan,{label:'Render deck',onUpdate,successMessage:'All card images saved',successToast:'Rendering complete. Your decks are ready for order review.'});
}

export async function renderCard(deckId,cardId,{onUpdate=async()=>{},force=false}={}){
  const plan=await api('/api/render-sessions/card',{deckId,cardId,force});
  return runRenderPlan(plan,{label:'Render card',onUpdate,idleMessage:'This card is already up to date',idleToast:'Cached image reused. No rendering needed.',successMessage:'Card image saved',successToast:'Card rendering complete.'});
}

export async function renderTemplatePreviews(deckId,group,settings,cardData,onImage,onPlan=()=>{},signal=null,choices=null){
  const plan=await api('/api/render-sessions/template-previews',{deckId,group,settings,cardData,choices});
  if(signal?.aborted)return;
  if(!plan.targets.length)throw new Error(Object.values(plan.previewErrors||{}).join('\n')||'No compatible frame could be previewed.');
  onPlan(plan);
  await runRenderPlan(plan,{label:'Preview frames',onImage,signal,idleMessage:'No frames to preview',
    successMessage:'Frame previews ready',successToast:'Frame previews are ready.'});
  return plan;
}

export async function renderTemplateSource(entries,onImage,signal=null){
  const plan=await api('/api/render-sessions/template-source',{entries});
  await runRenderPlan(plan,{label:'Preview Card Conjurer save',onImage,signal,
    successMessage:'Source previews ready',successToast:'Choose the card to turn into a reusable template.'});
  return plan;
}

export async function renderTemplateModel(model,onImage,signal=null){
  const plan=await job('/api/render-sessions/template-model',{model},{label:'Check template layouts',signal});
  await runRenderPlan(plan,{label:'Validate template',onImage,signal,
    successMessage:'Template preview ready',successToast:'Inspect the text and region outlines before saving.'});
  return plan;
}

function withTimeout(p,ms,msg){return new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error(msg)),ms);p.then(x=>{clearTimeout(t);resolve(x)},e=>{clearTimeout(t);reject(e)});});}
