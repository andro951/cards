import {api,blobRequest,job,activity,endActivity,work,modal,$,state} from './ui.js';
import {recordDiagnostic} from './diagnostics.js';
import {renderDecks} from './render.js';
import {exportReview} from './review-export.js';
import {createBatchReviewFlow} from './batch-review-flow.js';

//#region Local preview transport
let previewToken=null,previewDecks=[],batchRevisions=new Map();
const browserPreview=()=>Boolean(state.bootstrap.browser);
const deckSnapshot=deck=>({id:deck.id,name:deck.name,status:deck.status,printStatus:deck.printStatus,revision:deck.revision,summary:{faces:deck.summary?.faces||0}});
export const temporaryBatchReviewAvailable=async()=>{
    if(!browserPreview())
        return api(`/api/dev/batch-review/availability`);

    if(location.hostname!==`127.0.0.1`)
        return {available:false};

    const response=await fetch(`/dev-batch-review/availability`,{cache:`no-store`});
    if(!response.ok)
        return {available:false};

    const result=await response.json();previewToken=result.token;
    return result;
};
const batchApi=async(path,data,owner)=>{
    if(!browserPreview())
        return api(`/api/dev/batch-review${path}`,data,`POST`,owner);

    const response=await fetch(`/dev-batch-review${path}`,{
        method:data===undefined?`GET`:`POST`,
        headers:{"Content-Type":`application/json`,"X-BPF-Batch":previewToken},
        body:data===undefined?undefined:JSON.stringify(data)
    });
    const result=await response.json();
    if(!response.ok)
        throw new Error(result.error||`Local batch request failed.`);

    return result;
};
const batchCandidates=async()=>{
    if(!browserPreview())
        return batchApi(`/candidates`);

    if(!(await temporaryBatchReviewAvailable()).available)
        return {available:false,decks:[]};

    previewDecks=(await api(`/api/decks`)).map(deckSnapshot);
    const decks=[],skipped=[];
    for(const deck of previewDecks) {
        if([`draft`,`prepared`].includes(deck.status)&&deck.printStatus!==`tokens-not-ready`&&deck.summary.faces>0)
            decks.push(deck);
        else if(deck.printStatus===`tokens-not-ready`||deck.status===`attention`)
            skipped.push({name:deck.name,reason:deck.printStatus===`tokens-not-ready`?`Token assignments need attention`:`Needs attention before generation`});
        else if(deck.status===`draft`)
            skipped.push({name:deck.name,reason:`Empty deck`});
    }

    return {available:true,decks,skipped};
};
//#endregion

//#region Batch ownership and shared exports
let batchTask=null,activeSession=null,comparisonStarted=false;
const checkCancelled=()=>{
    if(batchTask.controller.signal.aborted)
        throw new Error(`Review batch cancelled. Previous comparison inputs are unchanged.`);
};
const stageReview=async(sessionId,deck,output,revision)=>{
    checkCancelled();
    const base=`/${sessionId}`;
    if(output.blob) {
        await batchApi(`${base}/upload/start`,{deckId:deck.id,filename:output.filename,bytes:output.blob.size,revision},batchTask);
        const chunkSize=8*1024*1024;
        for(let offset=0;offset<output.blob.size;offset+=chunkSize) {
            checkCancelled();
            activity(`Batch review`,`Saving review ZIP for ${deck.name}`,`${Math.round(offset/output.blob.size*100)}% uploaded`,offset,output.blob.size,batchTask);
            const path=`${base}/upload/${deck.id}?offset=${offset}`;
            if(browserPreview())
                await blobRequest(`/dev-batch-review${path}`,output.blob.slice(offset,offset+chunkSize),`application/octet-stream`,{"X-BPF-Batch":previewToken});
            else
                await blobRequest(`/api/dev/batch-review${path}`,output.blob.slice(offset,offset+chunkSize));
        }

        checkCancelled();
        await batchApi(`${base}/upload/complete`,{deckId:deck.id},batchTask);
    }
    else {
        const download=new URL(output.download,location.origin);
        const match=/^\/api\/review-downloads\/([-a-f0-9]{36})\/([A-Za-z0-9_.-]+\.zip)$/.exec(download.pathname);
        if(download.origin!==location.origin||!match||match[2]!==output.filename)
            throw new Error(`${deck.name}: invalid review export result.`);

        await batchApi(`${base}/stage`,{deckId:deck.id,token:match[1],filename:output.filename,revision},batchTask)
            .finally(()=>output.cleanup?api(output.cleanup,{},`POST`,batchTask).catch(error=>recordDiagnostic(`Review export cleanup failed`,error.message)):null);
    }

    batchRevisions.set(deck.id,revision);
    return {filename:output.filename};
};
const reviewFlow=createBatchReviewFlow({
    getCandidates:async()=>{
        const response=await batchCandidates();
        if(!response.available)
            throw new Error(`ImageFolderCompareAll is not available beside this ProxyFoundry checkout.`);

        checkCancelled();
        return response;
    },
    start:async deckIds=>{
        batchRevisions.clear();
        const session=await batchApi(`/start`,{deckIds,...(browserPreview()?{decks:previewDecks.filter(deck=>deckIds.includes(deck.id))}:{})},batchTask);
        activeSession=session.id;
        return session;
    },
    render:async deckIds=>{
        const result=await renderDecks(deckIds,{notify:false,signal:batchTask.controller.signal});
        if(result!==false)
            work.claim(batchTask,[`workspace`]);

        return result;
    },
    exportAndStage:async(sessionId,deck)=>{
        checkCancelled();
        const current=await api(`/api/decks/${deck.id}`);
        if(browserPreview())
            await batchApi(`/${sessionId}/ready`,{decks:[deckSnapshot(current)]},batchTask);

        return exportReview(deck.id,{owner:batchTask,consume:async output=>{
            if(browserPreview()&&!output.blob) {
                const response=await fetch(output.download);
                if(!response.ok)
                    throw new Error(`The browser review export is unavailable.`);

                return stageReview(sessionId,deck,{filename:output.filename,blob:await response.blob()},current.revision)
                    .finally(()=>api(output.cleanup,{},`POST`,batchTask));
            }

            return stageReview(sessionId,deck,output,current.revision);
        }});
    },
    commit:async sessionId=>{
        checkCancelled();
        if(browserPreview()) {
            const current=(await api(`/api/decks`)).map(deckSnapshot).filter(deck=>batchRevisions.has(deck.id));
            if(current.length!==batchRevisions.size||current.some(deck=>deck.revision!==batchRevisions.get(deck.id)||deck.status!==`ready`||deck.printStatus!==`ready`))
                throw new Error(`A deck changed after its review export. Previous comparison inputs are unchanged.`);

            await batchApi(`/${sessionId}/ready`,{decks:current},batchTask);
        }

        //Let the checker finish publishing or restoring its result folders.
        batchTask.cancellable=false;comparisonStarted=true;
        try {
            if(!browserPreview())
                return await job(`/api/dev/batch-review/${sessionId}/commit`,{},
                    {label:`Run ImageFolderCompareAll`,owner:batchTask});

            const started=await batchApi(`/${sessionId}/commit`,{},batchTask);
            while(true) {
                const status=await batchApi(`/jobs/${started.id}`);
                activity(`Batch review`,`Run ImageFolderCompareAll`,status.message,status.done,status.total,batchTask);
                if(status.state===`done`)
                    return status.result;

                if(status.state===`failed`)
                    throw new Error(status.error);

                await new Promise(resolve=>setTimeout(resolve,500));
            }
        }
        finally {
            batchTask.cancellable=true;
        }
    },
    abort:sessionId=>batchApi(`/${sessionId}/abort`,{},batchTask),
    onAbortError:error=>recordDiagnostic(`Review batch cleanup failed`,error.message)
});
export const runTemporaryBatchReview=async()=>{
    if(reviewFlow.busy)
        throw new Error(`A review batch is already running.`);

    work.requireIdle();
    const owner=work.begin({label:`Batch review`,resources:[`batch-review`]});
    batchTask=owner;
    try {
        activity(`Batch review`,`Checking decks`,`Finding decks that need regeneration`,0,0,owner);
        const result=await reviewFlow.run();
        endActivity(`Batch review complete`,false,owner);
        return result;
    }
    catch(error) {
        endActivity(error.message,true,owner);
        throw error;
    }
    finally {
        activeSession=null;comparisonStarted=false;batchTask=null;work.finish(owner);
    }
};
//Closing a tab before comparison releases its staging lease; published inputs are untouched.
window.addEventListener(`pagehide`,()=>{
    if(!activeSession||comparisonStarted)
        return;

    const prefix=browserPreview()?`/dev-batch-review`:`/api/dev/batch-review`;
    const headers=browserPreview()?{"X-BPF-Batch":previewToken}:{"X-Proxy-CSRF":state.csrf};
    fetch(`${prefix}/${activeSession}/abort`,{method:`POST`,headers:{...headers,"Content-Type":`application/json`},body:`{}`,keepalive:true})
        .catch(error=>recordDiagnostic(`Batch tab cleanup`,error.message));
});
//#endregion

//#region Results
export function showBatchReviewResult(result) {
    modal(`Batch review complete`,``);
    const body=$(`#modal-host .modal-body`);
    const summary=document.createElement(`p`);
    const counts=result.result?.counts;
    summary.textContent=result.decks.length?`Saved review ZIPs for ${result.decks.length} decks and ran ImageFolderCompareAll.`:`No decks need regeneration.`;
    body.append(summary);
    if(counts) {
        const changes=document.createElement(`p`);
        changes.textContent=`Changed: ${counts.changed} · New: ${counts.new} · Removed: ${counts.removed} · Unchanged: ${counts.unchanged}`;
        body.append(changes);
    }

    if(result.skipped.length) {
        const heading=document.createElement(`p`);heading.textContent=`Skipped decks:`;body.append(heading);
        const list=document.createElement(`ul`);
        for(const deck of result.skipped) {
            const item=document.createElement(`li`);item.textContent=`${deck.name}: ${deck.reason}`;list.append(item);
        }

        body.append(list);
    }

    if(result.result?.report) {
        const details=document.createElement(`details`),heading=document.createElement(`summary`),report=document.createElement(`pre`);
        heading.textContent=`Comparison report`;report.textContent=result.result.report;report.style.whiteSpace=`pre-wrap`;
        details.append(heading,report);body.append(details);
    }
}
//#endregion
