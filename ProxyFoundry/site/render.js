import {withGenerationScreen,generationScreen} from './generation-progress.js';
import {recordDiagnostic} from './diagnostics.js';
import {$,state,api,blobRequest,job,activity,endActivity,toast,work} from './ui.js';
import {ensureArtworkReady} from './artwork-review.js';
import {NativeRenderer,NativeRenderPool,renderWorkerCount} from './native-render-pool.js';

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
    const report=(title,detail,done=0)=>{activity(label,title,detail,done,plan.targets.length,owner);if(!onImage)generationScreen.active?.update('render',done,plan.targets.length);};
    const started=performance.now();let outcome='failed',pool=null,lastUpdate=0,saver=null;
    try{
        if(signal.aborted)throw new Error('Rendering cancelled. Completed images are saved.');
        report('Render plan',`Pipeline ${plan.pipelineVersion||state.bootstrap.pipelineVersion||'unknown'} · ${plan.targets.length} queued · ${plan.cached} cached`);
        if(!plan.targets.length){if(plan.errors.length)throw new Error(plan.errors.join('\n'));outcome='cached';endActivity(idleMessage,false,owner);if(idleToast)toast(idleToast);return;}
        await measure('runtime.prepare',()=>job('/api/runtime/prepare',{}, {label:'Load CardConjurer',owner}));
        if(signal.aborted)throw new Error('Rendering cancelled. Completed images are saved.');
        const workers=typeof Worker==='function'&&typeof OffscreenCanvas==='function'&&typeof OffscreenCanvas.prototype.convertToBlob==='function'&&typeof createImageBitmap==='function';
        const count=renderWorkerCount(plan.targets.length,workers);
        if(state.bootstrap.browser&&!onImage){
            const {BrowserRenderSave}=await import('../web/render-save.js');
            saver=await BrowserRenderSave.open(api);
        }
        report('Starting native renderer',workers?`Starting ${count} rendering worker${count===1?'':'s'}…`:'Loading the native renderer…');
        pool=new NativeRenderPool({count,signal,createRenderer:()=>new NativeRenderer({
            origin:state.bootstrap.runtimeOrigin,basePath:window.__pfBasePath||'',owner:window.__pfOwner||'',worker:workers,
            diagnostic:message=>api('/api/render-diagnostic',{key:message.key,stage:message.stage,diagnostic:message.diagnostic}).catch(error=>recordDiagnostic('Render diagnostic',error.message)),
            progress:(target,message)=>{if(!signal.aborted)report(target.name,message,pool.saved);}
        })});
        await measure('runtime.start',()=>Promise.all(pool.renderers.map(renderer=>renderer.ready)),{workers:count});
        await pool.run(plan.targets,{
            load:async target=>{
                const detail=await measure('render.load-face',()=>api('/api/render-sessions/'+plan.id+'/'+target.key),{card:target.name,key:target.key});
                target.saveTarget={key:target.key,deckId:detail.deckId,cardId:detail.cardId,faceId:detail.faceId};
                return detail.data;
            },
            save:(target,output)=>measure('render.save',()=>onImage?onImage(target,output.blob):saver?saver.save(target.saveTarget,output):blobRequest('/api/render-sessions/'+plan.id+'/'+target.key,output.blob,'image/png'),{card:target.name,key:target.key,bytes:output.blob.size}),
            saved:async(target,output,done)=>{
                if(signal.aborted)return;
                report(target.name,`${onImage?'Preview ready':'PNG saved'} · ${output.width} × ${output.height}`,done);
                if(performance.now()-lastUpdate>=2000){lastUpdate=performance.now();await onUpdate();}
            }
        });
        if(!onImage)generationScreen.active?.update('finish');
        await saver?.flush();
        if(plan.errors.length){endActivity('Rendered available cards; some need attention',true,owner);throw new Error(plan.errors.join('\n'));}
        outcome='ok';endActivity(successMessage,false,owner);if(successToast)toast(successToast);
    }catch(error){
        if(signal.aborted){if(work.visible()===owner)$('#activity').classList.add('hidden');}
        else{api('/api/client-error',{error:'Native render: '+(error.stack||error.message)}).catch(()=>{});endActivity(error.message,true,owner);}
        throw error;
    }finally{
        logTiming('render.total',started,signal.aborted?'cancelled':outcome,{cards:plan.targets.length,cached:plan.cached});
        pool?.close();
        try{await saver?.flush();}finally{await onUpdate();}
    }
}

export async function renderDecks(ids,{onUpdate=async()=>{},prepare=true,force=false,signal=null,notify=true,artChecked=false}={}){
  if(!artChecked)for(const id of ids)if(!await ensureArtworkReady(id))return;
  const update=async id=>{
    const view=state.generationView;
    if(view?.route===state.route&&(!view.id||ids.includes(view.id)))
      await view.refresh().catch(error=>recordDiagnostic('Progress view refresh',error.message));
    await onUpdate(id);
  };
  const name=ids.length===1?(state.decks.find(deck=>deck.id===ids[0])?.name||(state.activeDeck?.id===ids[0]?state.activeDeck.name:'deck')):ids.length+' decks';
  const cards=ids.reduce((sum,id)=>sum+(state.decks.find(deck=>deck.id===id)?.summary?.faces||state.activeDeck?.summary?.faces||1),0);
  const preparation=new Map(ids.map(id=>[id,{done:0,total:state.decks.find(deck=>deck.id===id)?.summary?.faces||1}]));
  return withGenerationScreen(name,cards,screen=>work.render(owner=>measure('generation.total',async()=>{
    screen.attach(owner);screen.update('prepare');
    if(prepare){
      for(const id of ids){
        await job('/api/decks/'+id+'/prepare',{}, {label:'Prepare deck',owner,onProgress:p=>{
          preparation.set(id,{done:p.done||0,total:p.total||preparation.get(id).total});
          const rows=[...preparation.values()];screen.update('prepare',rows.reduce((sum,row)=>sum+row.done,0),rows.reduce((sum,row)=>sum+row.total,0));
        }});await update(id);
      }
    }
    if(owner.controller.signal.aborted)throw new Error('Generation cancelled. Completed images are saved.');
    const plan=await api('/api/render-sessions',{deckIds:ids,force});
    return runRenderPlan(plan,{label:'Render deck',onUpdate:update,owner,successMessage:'All card images saved',successToast:null,idleToast:null});
  },{decks:ids.length}).catch(error=>{endActivity(error.message,true,owner);throw error;}),{label:'Generate images for '+name,resources:ids.map(id=>'deck:'+id),signal,kind:'generation'}));
}

export async function renderCard(deckId,cardId,{onUpdate=async()=>{},force=false}={}){
  if(!await ensureArtworkReady(deckId))return;
  return withGenerationScreen('Card image',1,screen=>work.render(async owner=>{
    screen.attach(owner);
    const plan=await api('/api/render-sessions/card',{deckId,cardId,force});
    return runRenderPlan(plan,{label:'Render card',onUpdate,owner,idleMessage:'This card is already up to date',idleToast:'Cached image reused. No rendering needed.',successMessage:'Card image saved',successToast:null});
  },{label:'Generate card image',resources:['deck:'+deckId],kind:'generation'}));
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
