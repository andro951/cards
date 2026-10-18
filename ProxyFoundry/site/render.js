import {withGenerationScreen,generationScreen} from './generation-progress.js';
import {recordDiagnostic} from './diagnostics.js';
import {$,state,api,blobRequest,job,activity,endActivity,toast,work} from './ui.js';
import {ensureArtworkReady} from './artwork-review.js';
import {NativeRenderer,NativeRenderPool,renderWorkerCount} from './native-render-pool.js';

function logTiming(stage,started,outcome,detail={}){
  const seconds=(performance.now()-started)/1000;
  if(seconds<.1)return;
  const diagnostic={stage,seconds:Number(seconds.toFixed(4)),outcome,...detail,storageType:state.bootstrap.storageType||'unknown'};
  if(state.generationTransaction){collectGenerationTiming(diagnostic);return;}
  recordDiagnostic('timing',JSON.stringify(diagnostic));
  api('/api/render-diagnostic',{stage:'timing',diagnostic}).catch(error=>recordDiagnostic('timing log error',error.message));
}
function collectGenerationTiming(diagnostic) {
    const timings=state.generationTransaction?.timings;
    if(!timings||!diagnostic?.stage||typeof diagnostic.seconds!==`number`)
        return;

    const aggregate=timings[diagnostic.stage]||={count:0,seconds:0,max:0};
    aggregate.count+=diagnostic.count||1;aggregate.seconds+=diagnostic.seconds;aggregate.max=Math.max(aggregate.max,diagnostic.seconds);
}
async function measure(stage,operation,detail={}){
  const started=performance.now();let outcome='failed';
  try{
    const result=await operation();outcome='ok';return result;
  }finally{logTiming(stage,started,outcome,detail);}
}


async function runRenderPlan(plan,options={}){
    const {label='Render deck',onUpdate=async()=>{},onImage=null,idleMessage='All images are already up to date',idleToast='Cached images reused. No rendering needed.',successMessage='All card images saved',successToast='Rendering complete. Your decks are ready for order review.',owner=null,generation=null,moreTargets=null}=options;
    if(!owner)return work.render(task=>runRenderPlan(plan,{...options,owner:task}),{label,background:!onImage,signal:options.signal});
    const signal=owner.controller.signal;
    const renderTotal=plan.total||plan.targets.length;
    const report=(title,detail,done=0)=>{activity(label,title,detail,done,renderTotal,owner);if(!onImage)generationScreen.active?.update('render',done,renderTotal);};
    const started=performance.now();let outcome='failed',pool=null,lastUpdate=0,saver=null;
    try{
        if(signal.aborted)throw new Error('Rendering cancelled. Completed images are saved.');
        report('Render plan',`Pipeline ${plan.pipelineVersion||state.bootstrap.pipelineVersion||'unknown'} · ${plan.targets.length} queued · ${plan.cached} cached`);
        if(!plan.targets.length){if(plan.errors.length)throw new Error(plan.errors.join('\n'));outcome='cached';endActivity(idleMessage,false,owner);if(idleToast)toast(idleToast);return {rows:[]};}
        await measure('runtime.prepare',()=>job('/api/runtime/prepare',{}, {label:'Load CardConjurer',owner}));
        if(signal.aborted)throw new Error('Rendering cancelled. Completed images are saved.');
        const workers=typeof Worker==='function'&&typeof OffscreenCanvas==='function'&&typeof OffscreenCanvas.prototype.convertToBlob==='function'&&typeof createImageBitmap==='function';
        const count=renderWorkerCount(Math.max(plan.targets.length,plan.total||0),workers);
        if(state.bootstrap.browser&&!onImage){
            const {BrowserRenderSave}=await import('../web/render-save.js');
            saver=await BrowserRenderSave.open(api,undefined,generation);
        }
        report('Starting native renderer',workers?`Starting ${count} rendering worker${count===1?'':'s'}…`:'Loading the native renderer…');
        pool=new NativeRenderPool({count,signal,concurrentSaves:!!generation,createRenderer:()=>new NativeRenderer({
            origin:state.bootstrap.runtimeOrigin,basePath:window.__pfBasePath||'',owner:window.__pfOwner||'',worker:workers,
            diagnostic:message=>{
                if(generation) {
                    if(message.stage===`timing`)
                        collectGenerationTiming(message.diagnostic);
                    else if(message.stage===`renderer.failure`)
                        recordDiagnostic(`Render failure`,JSON.stringify(message.diagnostic));

                    return;
                }

                api('/api/render-diagnostic',{key:message.key,stage:message.stage,diagnostic:message.diagnostic}).catch(error=>recordDiagnostic('Render diagnostic',error.message));
            },
            progress:(target,message)=>{if(!signal.aborted)report(target.name,message,pool.saved);}
        })});
        await measure('runtime.start',()=>Promise.all(pool.renderers.map(renderer=>renderer.ready)),{workers:count});
        await pool.run(plan.targets,{
            pipeline:!!generation,moreTargets,
            load:async target=>{
                const detail=await measure('render.load-face',()=>api('/api/render-sessions/'+plan.id+'/'+target.key),{card:target.name,key:target.key});
                target.saveTarget={key:target.key,deckId:detail.deckId,cardId:detail.cardId,faceId:detail.faceId};
                return detail.data;
            },
            save:(target,output)=>measure('render.save',()=>onImage?onImage(target,output.blob):saver?saver.save(target.saveTarget,output):blobRequest('/api/render-sessions/'+plan.id+'/'+target.key,output.blob,'image/png'),{card:target.name,key:target.key,bytes:output.blob.size}),
            saved:async(target,output,done)=>{
                if(signal.aborted)return;
                report(target.name,`${onImage?'Preview ready':'PNG saved'} · ${output.width} × ${output.height}`,done);
                if(!generation&&performance.now()-lastUpdate>=2000){lastUpdate=performance.now();await onUpdate();}
            }
        });
        if(!onImage)generationScreen.active?.update('finish');
        await saver?.flush();
        if(plan.errors.length){endActivity('Rendered available cards; some need attention',true,owner);throw new Error(plan.errors.join('\n'));}
        outcome='ok';
        if(!generation){endActivity(successMessage,false,owner);if(successToast)toast(successToast);}
        return {rows:saver?.rows||[]};
    }catch(error){
        if(generation)error=new Error(signal.aborted?`Generation cancelled. Previous card images are unchanged.`:error.message.replace(`Completed images are saved.`,`Previous card images are unchanged.`));
        if(signal.aborted){if(work.visible()===owner)$('#activity').classList.add('hidden');}
        else{api('/api/client-error',{error:'Native render: '+(error.stack||error.message)}).catch(()=>{});endActivity(error.message,true,owner);}
        throw error;
    }finally{
        logTiming('render.total',started,signal.aborted?'cancelled':outcome,{cards:plan.targets.length,cached:plan.cached});
        pool?.close();
        if(!generation){try{await saver?.flush();}finally{await onUpdate();}}
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
    let generation=null;
    try {
    if(state.bootstrap.browser) {
        generation=await api(`/api/generation/begin`,{deckIds:ids});
        owner.atomicGeneration=true;
        state.generationTransaction={...generation,timings:{}};
    }

    let preparationTask=null,preparationError=null;
    const prepareAll=async()=>{
      for(const id of ids){
        await job('/api/decks/'+id+'/prepare',{}, {label:'Prepare deck',owner,onProgress:p=>{
          preparation.set(id,{done:p.done||0,total:p.total||preparation.get(id).total});
          const rows=[...preparation.values()];if(screen.estimate.phase!=='render')screen.update('prepare',rows.reduce((sum,row)=>sum+row.done,0),rows.reduce((sum,row)=>sum+row.total,0));
        }});if(!generation)await update(id);
      }
    };
    if(prepare){
      if(generation) {
        preparationTask=prepareAll();preparationTask.catch(error=>{preparationError=error;});
      }
      else await prepareAll();
    }
    if(owner.controller.signal.aborted)throw new Error('Generation cancelled. Previous card images are unchanged.');
    let plan,moreTargets=null;
    if(generation&&prepare&&!force) {
      let cursor=0;
      const read=async stopped=>{
        let next;
        do {
          if(preparationError)throw preparationError;
          if(owner.controller.signal.aborted||stopped?.aborted)throw new Error(`Generation stopped.`);
          next=await api(`/api/generation/targets?id=${generation.id}&after=${cursor}`);
          if(next.errors.length)throw new Error(next.errors.join(`\n`));
          cursor=next.cursor;
          if(!next.targets.length&&!next.complete)await new Promise(resolve=>setTimeout(resolve,100));
        } while(!next.targets.length&&!next.complete);
        return next;
      };
      plan=await read();
      if(!plan.complete)moreTargets=read;
    }
    else {
      if(preparationTask)await preparationTask;
      plan=await api('/api/render-sessions',{deckIds:ids,force});
    }

    const rendered=await runRenderPlan(plan,{label:'Render deck',onUpdate:update,owner,generation,moreTargets,successMessage:'All card images saved',successToast:null,idleToast:null});
    if(preparationTask)await preparationTask;
    if(generation) {
        if(owner.controller.signal.aborted)
            throw new Error(`Generation cancelled. No card images were updated.`);

        screen.update(`finish`);screen.cancel.disabled=true;
        await api(`/api/generation/commit`,{id:generation.id,rows:rendered?.rows||[],timings:state.generationTransaction.timings});
        generation=null;state.generationTransaction=null;
        endActivity(`All card images saved`,false,owner);
        for(const id of ids) {
            await update(id);
        }
    }

    return rendered;
    }
    finally {
        if(generation) {
            await api(`/api/generation/abort`,{id:generation.id});
        }

        state.generationTransaction=null;
    }
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
