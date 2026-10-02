import {recordDiagnostic} from './diagnostics.js';
import {$,state,api,blobRequest,job,activity,endActivity,sleep,toast,work} from './ui.js';
let activeFrame=null;

function logTiming(stage,started,outcome,detail={}){
  const seconds=(performance.now()-started)/1000;
  if(seconds<.1)return;
  const diagnostic={stage,seconds:Number(seconds.toFixed(4)),outcome,...detail,storageType:state.bootstrap.storageType||'unknown'};
  recordDiagnostic('timing',JSON.stringify(diagnostic));
  api('/api/render-diagnostic',{stage:'timing',diagnostic}).catch(error=>recordDiagnostic('timing log error',error.message));
}
async function measure(stage,operation,detail={}){
  const started=performance.now();let outcome='failed';
  try{
    const result=await operation();outcome='ok';return result;
  }finally{logTiming(stage,started,outcome,detail);}
}


async function runRenderPlan(plan,options={}){
  const {label='Render deck',onUpdate=async()=>{},onImage=null,idleMessage='All images are already up to date',idleToast='Cached images reused. No rendering needed.',successMessage='All card images saved',successToast='Rendering complete. Your decks are ready for order review.',owner=null}=options;
  if(!owner)return work.render(task=>runRenderPlan(plan,{...options,owner:task}),{label,background:!onImage,signal:options.signal});
  const signal=owner.controller.signal;
  const report=(title,detail,done=0,total=0)=>activity(label,title,detail,done,total,owner);
  const started=performance.now();let outcome='failed';
  let cancelled=false,listener=null,rejectPending=null,pending=null,ready=false,readyResolve,readyReject,ping;
  const origin=state.bootstrap.runtimeOrigin;
  const cleanup=()=>{clearInterval(ping);if(listener)window.removeEventListener('message',listener);activeFrame?.contentWindow?.postMessage({source:'pf-app',type:'dispose'},origin);activeFrame?.remove();activeFrame=null;};
  const cancel=()=>{
    if(cancelled)return;
    cancelled=true;
    const error=new Error('Rendering cancelled. Completed images are saved.');
    rejectPending?.(error);readyReject?.(error);cleanup();
  };
  signal?.addEventListener('abort',cancel,{once:true});
  try{
    if(signal?.aborted)cancel();
    if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
    report('Render plan',`Pipeline ${plan.pipelineVersion||state.bootstrap.pipelineVersion||'unknown'} · force=${plan.force?'yes':'no'} · ${plan.targets.length} queued · ${plan.cached} cached`,0,plan.targets.length);
    if(!plan.targets.length){if(plan.errors.length)throw new Error(plan.errors.join('\n'));outcome='cached';endActivity(idleMessage,false,owner);if(idleToast)toast(idleToast);return;}
    if(plan.force)report('Pipeline upgrade','Ignoring cached PNGs and rebuilding every prepared face…',0,plan.targets.length);
    await measure('runtime.prepare',()=>job('/api/runtime/prepare',{}, {label:'Load CardConjurer',owner}));
    if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
    report('Starting native renderer','Loading the pinned CardConjurer runtime…',0,plan.targets.length);
    const readyPromise=new Promise((r,j)=>{readyResolve=r;readyReject=j;});
    listener=event=>{
      if(event.origin!==origin||event.source!==activeFrame?.contentWindow||event.data?.source!=='pf-native-runtime')return;
      const m=event.data;
      if(m.type==='ready'){ready=true;readyResolve();return;}
      if(m.type==='failed'&&!ready){readyReject(new Error(m.error));return;}
      if(m.type==='diagnostic'){api('/api/render-diagnostic',{key:m.key,stage:m.stage,diagnostic:m.diagnostic}).catch(()=>{});return;}
      if(!pending||m.key!==pending.key)return;
      if(m.type==='progress'){report(pending.name,m.message,pending.index,plan.targets.length);return;}
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
      const t=plan.targets[i];report(t.name,'Loading saved face and frame assets…',i,plan.targets.length);
      const detail=await measure('render.load-face',()=>api('/api/render-sessions/'+plan.id+'/'+t.key),{card:t.name,key:t.key});
      if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
      report(t.name,`Fresh render · key ${t.key.slice(0,12)} · ${detail.data.version||'unknown'} · set symbol zoom=${detail.data.setSymbolZoom??'n/a'} x=${detail.data.setSymbolX??'n/a'} y=${detail.data.setSymbolY??'n/a'}`,i,plan.targets.length);
      const promise=new Promise((resolve,reject)=>{pending={...t,index:i,resolve,reject};rejectPending=reject;});
      activeFrame.contentWindow.postMessage({source:'pf-app',type:'render',key:t.key,data:detail.data},origin);
      const output=await measure('render.native',()=>withTimeout(promise,150000,t.name+': native render timed out. Retry will keep completed images.'),{card:t.name,key:t.key});
      pending=null;rejectPending=null;
      if(cancelled)throw new Error('Rendering cancelled. Completed images are saved.');
      await measure('render.save',()=>onImage?onImage(t,output.blob):blobRequest('/api/render-sessions/'+plan.id+'/'+t.key,output.blob,'image/png'),{card:t.name,key:t.key,bytes:output.blob.size});
      report(t.name,(onImage?'Preview ready · ':'PNG saved · ')+output.width+' × '+output.height,i+1,plan.targets.length);
      await onUpdate();
    }
    if(plan.errors.length){endActivity('Rendered available cards; some need attention',true,owner);throw new Error(plan.errors.join('\n'));}
    outcome='ok';endActivity(successMessage,false,owner);if(successToast)toast(successToast);
  }catch(e){
    if(cancelled){if(work.visible()===owner)$('#activity').classList.add('hidden');}
    else{api('/api/client-error',{error:'Native render: '+(e.stack||e.message)}).catch(()=>{});endActivity(e.message,true,owner);}
    throw e;
  }finally{logTiming('render.total',started,cancelled?'cancelled':outcome,{cards:plan.targets.length,cached:plan.cached});signal?.removeEventListener('abort',cancel);cleanup();await onUpdate();}
}

export async function renderDecks(ids,{onUpdate=async()=>{},prepare=true,force=false,signal=null,notify=true}={}){
  const update=async id=>{
    const view=state.generationView;
    if(view?.route===state.route&&(!view.id||ids.includes(view.id)))
      await view.refresh().catch(error=>recordDiagnostic('Progress view refresh',error.message));
    await onUpdate(id);
  };
  const name=ids.length===1?(state.decks.find(deck=>deck.id===ids[0])?.name||(state.activeDeck?.id===ids[0]?state.activeDeck.name:'deck')):ids.length+' decks';
  return work.render(owner=>measure('generation.total',async()=>{
    if(prepare){
      for(const id of ids){
        await job('/api/decks/'+id+'/prepare',{}, {label:'Prepare deck',owner});await update(id);
      }
    }
    if(owner.controller.signal.aborted)throw new Error('Generation cancelled. Completed images are saved.');
    const plan=await api('/api/render-sessions',{deckIds:ids,force});
    return runRenderPlan(plan,{label:'Render deck',onUpdate:update,owner,successMessage:'All card images saved',successToast:notify?'Rendering complete. Your decks are ready for order review.':null,idleToast:notify?'Cached images reused. No rendering needed.':null});
  },{decks:ids.length}).catch(error=>{endActivity(error.message,true,owner);throw error;}),{label:'Generate images for '+name,resources:ids.map(id=>'deck:'+id),signal});
}

export async function renderCard(deckId,cardId,{onUpdate=async()=>{},force=false}={}){
  return work.render(async owner=>{
    const plan=await api('/api/render-sessions/card',{deckId,cardId,force});
    return runRenderPlan(plan,{label:'Render card',onUpdate,owner,idleMessage:'This card is already up to date',idleToast:'Cached image reused. No rendering needed.',successMessage:'Card image saved',successToast:'Card rendering complete.'});
  },{label:'Generate card image',resources:['deck:'+deckId]});
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
