export function renderWorkerCount(targets,workers,device=navigator){
    if(!workers||targets<2)return 1;
    const memory=device.deviceMemory||4,cores=device.hardwareConcurrency||2;
    if(memory<=4||cores<=2)return 1;
    return Math.min(targets,memory>=8&&cores>=4?3:2);
}

export class NativeRenderer {
    constructor({origin,basePath=``,owner=``,worker=true,diagnostic=()=>{},progress=()=>{}}){
        this.origin=origin;this.diagnostic=diagnostic;this.progress=progress;this.closed=false;
        this.ready=new Promise((resolve,reject)=>{this.resolveReady=resolve;this.rejectReady=reject;});
        //Attach a handler immediately so cancellation during startup cannot leak a rejection.
        this.ready.catch(()=>{});
        this.frame=document.createElement(`iframe`);this.frame.className=`render-frame`;
        this.frame.title=worker?`Native CardConjurer rendering worker`:`Native CardConjurer renderer`;
        this.frame.setAttribute(`sandbox`,`allow-scripts allow-same-origin`);
        this.frame.src=origin+basePath+`/runtime/host?parent=${encodeURIComponent(location.origin)}&owner=${encodeURIComponent(owner)}${worker?`&worker=1`:``}`;
        window.addEventListener(`message`,this.receive);document.body.append(this.frame);
        this.ping=setInterval(()=>this.frame.contentWindow?.postMessage({source:`pf-app`,type:`ping`},origin),800);
        this.startup=setTimeout(()=>this.close(new Error(`The native renderer did not start. Check Diagnostics in Settings.`)),65000);
    }
    receive = event => {
        if(event.origin!==this.origin||event.source!==this.frame.contentWindow||event.data?.source!==`pf-native-runtime`)return;
        const message=event.data;
        if(message.type===`ready`){clearInterval(this.ping);clearTimeout(this.startup);this.resolveReady();return;}
        if(message.type===`diagnostic`){this.diagnostic(message);return;}
        if(message.type===`failed`){
            this.diagnostic({key:message.key,stage:`renderer.failure`,diagnostic:{error:message.error,errors:message.errors||[]}});
            const error=new Error(message.error);
            if(this.pending)this.pending.reject(error);else this.rejectReady(error);
            return;
        }
        if(!this.pending||message.key!==this.pending.key)return;
        if(message.type===`progress`)this.progress(this.pending.target,message.message);
        if(message.type===`rendered`){
            if(!(message.blob instanceof Blob)||!message.blob.size)this.pending.reject(new Error(`Native renderer returned an empty PNG.`));
            else this.pending.resolve(message);
        }
    };
    render = async (target,data) => {
        await this.ready;
        if(this.closed)throw new Error(`Native renderer is closed.`);
        if(this.pending)throw new Error(`Native renderer already has a face in progress.`);
        let timer;
        try{
            return await new Promise((resolve,reject)=>{
                this.pending={target,key:target.key,resolve,reject};
                timer=setTimeout(()=>reject(new Error(`${target.name}: native render timed out. Completed images are saved.`)),150000);
                this.frame.contentWindow.postMessage({source:`pf-app`,type:`render`,key:target.key,data},this.origin);
            });
        }finally{clearTimeout(timer);this.pending=null;}
    };
    close = (error=new Error(`Rendering cancelled. Completed images are saved.`)) => {
        if(this.closed)return;
        this.closed=true;clearInterval(this.ping);clearTimeout(this.startup);
        this.pending?.reject(error);this.rejectReady(error);
        this.frame.contentWindow?.postMessage({source:`pf-app`,type:`dispose`},this.origin);
        window.removeEventListener(`message`,this.receive);this.frame.remove();
    };
}

export class NativeRenderPool {
    constructor({count=2,createRenderer,signal=null}){
        this.signal=signal;this.failure=null;this.next=0;this.saved=0;this.saveTail=Promise.resolve();
        this.renderers=[];
        try{for(let index=0;index<Math.max(1,Math.min(4,count));index++)this.renderers.push(createRenderer());}
        catch(error){for(const renderer of this.renderers)renderer.close(error);throw error;}
        signal?.addEventListener(`abort`,this.cancel,{once:true});
        if(signal?.aborted)this.cancel();
    }
    check = () => {if(this.failure)throw this.failure;};
    cancel = () => this.stop(new Error(`Rendering cancelled. Completed images are saved.`));
    stop = error => {
        this.failure??=error;
        for(const renderer of this.renderers)renderer.close(this.failure);
    };
    run = async (targets,{load,save,saved=()=>{}}) => {
        const consume=async renderer=>{
            await renderer.ready;
            while(this.next<targets.length){
                this.check();const index=this.next++;const target={...targets[index],index};
                const data=await load(target);this.check();
                const started=performance.now();const output=await renderer.render(target,data);this.check();
                renderer.diagnostic?.({key:target.key,stage:`timing`,diagnostic:{stage:`render.native`,seconds:Number(((performance.now()-started)/1000).toFixed(4)),outcome:`ok`}});
                //Each worker holds at most one completed PNG. Storage commits stay sequential.
                const commit=this.saveTail.then(async()=>{
                    this.check();await save(target,output);this.saved++;await saved(target,output,this.saved);
                });
                this.saveTail=commit;
                await commit;
            }
        };
        try{
            const jobs=this.renderers.map(renderer=>consume(renderer).catch(error=>{this.stop(error);throw error;}));
            const results=await Promise.allSettled(jobs);
            const failure=results.find(result=>result.status===`rejected`);
            if(failure)throw failure.reason;
            return this.saved;
        }finally{this.close();}
    };
    close = () => {
        this.signal?.removeEventListener(`abort`,this.cancel);
        for(const renderer of this.renderers)renderer.close();
    };
}