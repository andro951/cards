import {api,activity,endActivity,work,job,downloadExportFile,downloadBlob} from './ui.js';
import {renderWorkerCount} from './native-render-pool.js';
import {ReviewZip} from './review-zip.js';
import {recordDiagnostic} from './diagnostics.js';

export async function downloadReview(deckId,options={}) {
    return exportReview(deckId,{...options,consume:output=>output.blob?downloadBlob(output.blob,output.filename):downloadExportFile(output)});
}

//The same worker/ZIP path serves downloads and local batch staging.
export async function exportReview(deckId,{cardId=null,faceId=null,owner=null,consume=output=>output}={}) {
    const task=owner||work.begin({label:`Review images`,resources:[`deck:${deckId}`]}),signal=task.controller.signal;
    const workers=[],pending=new Set(),started=performance.now();
    const cancelled=()=>new Error(`Review download cancelled.`);
    const stop=()=>{
        for(const worker of workers) {worker.terminate();}
        for(const reject of pending) {reject(cancelled());}
        pending.clear();
    };
    signal.addEventListener(`abort`,stop,{once:true});
    try {
        activity(`Review images`,`Preparing download`,`PNG · half-size`,0,0,task);
        if(typeof Worker!==`function`||typeof OffscreenCanvas!==`function`||typeof createImageBitmap!==`function`||!OffscreenCanvas.prototype.convertToBlob) {
            const path=cardId?`/api/decks/${deckId}/cards/${cardId}/review-image`:`/api/decks/${deckId}/review-images`;
            const output=await job(path,cardId?{faceId}:{},{label:`Review images`,owner:task});
            if(signal.aborted) {
                await api(output.cleanup,{},`POST`,task);
                throw cancelled();
            }

            return await consume(output,task);
        }

        const plan=await api(`/api/decks/${deckId}/review-plan`,{cardId,faceId},`POST`,task);
        if(signal.aborted)
            throw cancelled();

        const zip=cardId?null:new ReviewZip();
        let next=0,done=0,single=null,packing=Promise.resolve();
        const count=renderWorkerCount(plan.items.length,true);
        await Promise.all(Array.from({length:count},async()=>{
            const worker=new Worker(new URL(`./review-worker.js`,import.meta.url),{type:`module`});workers.push(worker);
            while(next<plan.items.length) {
                if(signal.aborted)
                    throw cancelled();

                const item=plan.items[next++],assetUrl=new URL(`/api/assets/${item.assetId}`,location.origin);
                if(window.__pfOwner)
                    assetUrl.searchParams.set(`owner`,window.__pfOwner);

                const output=await new Promise((resolve,reject)=>{
                    pending.add(reject);
                    worker.onmessage=event=>{pending.delete(reject);event.data.error?reject(new Error(event.data.error)):resolve(event.data.blob);};
                    worker.onerror=event=>{pending.delete(reject);reject(new Error(event.message||`Review worker failed.`));};
                    worker.postMessage({item,assetUrl:String(assetUrl),root:window.__pfWorkspaceDirectory||null});
                });
                if(signal.aborted)
                    throw cancelled();

                //Serialize archive metadata while workers continue processing other images.
                if(zip) {
                    packing=packing.then(()=>zip.add(item.filename,output));
                    await packing;
                }
                else
                    single=output;

                done++;activity(`Review images`,item.name,`PNG · half-size`,done,plan.items.length,task);
            }
        }));
        if(signal.aborted)
            throw cancelled();

        const blob=zip?zip.finish():single;
        const result=await consume({blob,filename:plan.filename,count:done},task);
        recordDiagnostic(`review export`,JSON.stringify({seconds:(performance.now()-started)/1000,count:done,bytes:blob.size,workers:count,format:`png`,scale:.5}));
        if(!owner)
            endActivity(`Review download ready`,false,task);
        return result;
    }
    catch(error) {
        if(!owner)
            endActivity(signal.aborted?`Review download cancelled`:`Review download failed`,true,task);
        throw error;
    }
    finally {
        stop();signal.removeEventListener(`abort`,stop);
        if(!owner)
            work.finish(task);
    }
}
