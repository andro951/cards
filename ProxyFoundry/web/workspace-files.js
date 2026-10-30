"use strict";

//Binary files stay in the selected browser/folder workspace, outside Python memory.
export class WorkspaceFiles {
    constructor(directory,downloadStaging=directory) {
        this.directory=directory;
        this.downloadStaging=downloadStaging;
        this.writers=new Map();
        this.inputBuffers=new Map();
        this.directories=new Map();
        this.downloads=new Map();
        this.orderZips=new Map();
        this.assetWrites=new Map();
        this.downloadWaiting=[];this.downloadBuffered=0;
    }

    parts = path => {
        const parts=String(path).split(`/`).filter(Boolean);
        if(!parts.length||parts.some(part=>part===`.`||part===`..`||part.includes(`\\`)||part.includes(`\0`)))
            throw new Error(`Invalid workspace file path.`);

        return parts;
    }
    parent = async (path,create=false) => {
        const parts=this.parts(path);
        let directory=this.directory;
        let key=`workspace`;
        if(parts[0]===`tmp`&&parts[1]===`review-downloads`) {
            //Review exports are temporary browser files, never selected-folder order packages.
            directory=this.downloadStaging;parts.shift();
            key=`staging`;
        }

        for(const part of parts.slice(0,-1)) {
            key+=`/`+part;
            const entryKey=key;
            if(!this.directories.has(key))
                this.directories.set(key,directory.getDirectoryHandle(part,{create}).catch(error=>{this.directories.delete(entryKey);throw error;}));

            directory=await this.directories.get(key);
        }

        return {directory,name:parts.at(-1)};
    }
    file = async path => {
        const {directory,name}=await this.parent(path);
        return (await directory.getFileHandle(name)).getFile();
    }
    invalidate = path => {
        for(const key of this.directories.keys()) {
            if(key===`workspace/`+path||key.startsWith(`workspace/`+path+`/`))
                this.directories.delete(key);
        }
    };
    close = async path => {
        const writer=this.writers.get(path);
        if(!writer)
            return;

        try{await writer.close();}
        catch(error){await writer.abort().catch(()=>{});throw error;}
        finally{this.writers.delete(path);}
    }
    writer = async path => {
        if(this.writers.has(path))
            return this.writers.get(path);

        const {directory,name}=await this.parent(path);
        const handle=await directory.getFileHandle(name,{create:true});
        const writer=await handle.createWritable({keepExistingData:true});
        this.writers.set(path,writer);
        return writer;
    }

    putAsset = async (path,body) => {
        if(!/^assets\/[a-f0-9]{2}\/[a-f0-9]{64}$/.test(path)||path.split(`/`)[1]!==path.split(`/`)[2].slice(0,2))
            throw new Error(`Invalid asset path.`);

        const {directory,name}=await this.parent(path,true);
        const handle=await directory.getFileHandle(name,{create:true});
        const writer=await handle.createWritable();
        await (body instanceof Blob?body:new Blob([body])).stream().pipeTo(writer);
        return {ok:true};
    }

    admitDownloads = () => {
        while(this.downloadWaiting.length&&(!this.downloadBuffered||this.downloadBuffered+this.downloadWaiting[0].size<=48*1024*1024)) {
            const next=this.downloadWaiting.shift();this.downloadBuffered+=next.size;next.resolve();
        }
    };
    acquireDownload = size => new Promise(resolve=>{this.downloadWaiting.push({size,resolve});this.admitDownloads();});

    prefetch = async (body,signal=null,onResult=null) => {
        const urls=JSON.parse(new TextDecoder().decode(body));
        if(!Array.isArray(urls)||!urls.length||urls.length>(onResult?10000:6)||urls.some(url=>typeof url!==`string`||!/^https:\/\/raw\.githubusercontent\.com\/[^/?#]+\/[^/?#]+\/[a-fA-F0-9]{40}\/[^?#]+$/.test(url)))
            throw new Error(`Invalid immutable artwork batch.`);

        const writes=new Map();
        const download=async (url,deadline)=>{
            const timeout=AbortSignal.timeout(Math.max(1,Math.ceil(deadline-performance.now())));
            const response=await fetch(url,{redirect:`error`,signal:signal?AbortSignal.any([signal,timeout]):timeout});
            if(!response.ok) {
                const error=new Error(`Artwork download failed (HTTP ${response.status}).`);
                error.retryable=response.status===429||response.status>=500;
                throw error;
            }

            const size=Number(response.headers.get(`Content-Length`));
            if(size>64*1024*1024)
                throw new Error(`Artwork is too large.`);

            //Known bodies share a 48 MiB budget; missing length headers retain the
            //previous limit of six simultaneous bodies. A known large file runs alone.
            const weight=size>0?size:8*1024*1024;
            await this.acquireDownload(weight);
            try {
                const blob=await response.blob();
                if(!blob.size||blob.size>64*1024*1024)
                    throw new Error(`Artwork is empty or too large.`);

                const bytes=await blob.arrayBuffer();
                let width=null,height=null;
                const header=new DataView(bytes);
                if(bytes.byteLength>=33&&header.getUint32(0)===0x89504e47&&header.getUint32(4)===0x0d0a1a0a) {
                    let plain=true;
                    for(let offset=8;offset+12<=bytes.byteLength;) {
                        const length=header.getUint32(offset),kind=header.getUint32(offset+4);
                        if(length>bytes.byteLength-offset-12){plain=false;break;}
                        if(kind===0x65584966||kind===0x6163544c)plain=false;
                        offset+=length+12;
                    }

                    if(plain&&header.getUint32(16)*header.getUint32(20)<=48000000) {
                        const bitmap=await createImageBitmap(blob);
                        if(bitmap.width===header.getUint32(16)&&bitmap.height===header.getUint32(20)) {
                            width=bitmap.width;height=bitmap.height;
                        }

                        bitmap.close();
                    }
                }

                const id=[...new Uint8Array(await crypto.subtle.digest(`SHA-256`,bytes))].map(value=>value.toString(16).padStart(2,`0`)).join(``);
                if(!writes.has(id)) {
                    if(!this.assetWrites.has(id)) {
                        const finish=()=>this.assetWrites.delete(id);
                        const pending=this.putAsset(`assets/${id.slice(0,2)}/${id}`,blob).then(result=>{finish();return result;},error=>{finish();throw error;});
                        this.assetWrites.set(id,pending);
                    }

                    writes.set(id,this.assetWrites.get(id));
                }

                await writes.get(id);
                return {id,bytes:blob.size,mime:width?`image/png`:response.headers.get(`Content-Type`)||`application/octet-stream`,width,height};
            }
            finally{this.downloadBuffered-=weight;this.admitDownloads();}
        };
        const results=new Array(urls.length);let next=0;
        const consume=async()=>{
            while(next<urls.length&&!signal?.aborted) {
                const index=next++,url=urls[index];
                const deadline=performance.now()+60000;
                for(let attempt=0;attempt<2;attempt++) {
                    try{results[index]=await download(url,deadline);break;}
                    catch(error){
                        if(attempt===0&&performance.now()<deadline&&!signal?.aborted&&(error.retryable||[`TimeoutError`,`TypeError`].includes(error.name)))
                            continue;

                        results[index]={error:String(error.message||error).slice(0,500)};break;
                    }
                }

                onResult?.(url,results[index]);
            }
        };
        //A slow file occupies one slot; other slots publish and start their next file immediately.
        await Promise.all(Array.from({length:Math.min(6,urls.length)},()=>consume()));
        return results;
    }

    //#region Filesystem requests
    execute = async (operation,path,query,body) => {
        if(operation===`start-order-zip`) {
            const entries=JSON.parse(new TextDecoder().decode(body));
            if(!/^orders\/[a-f0-9-]{36}\.zip$/.test(path)||!Array.isArray(entries)||!entries.length||entries.length>20000)
                throw new Error(`Invalid paired ZIP plan.`);
            for(const entry of entries) {
                this.parts(entry.path);
                if(!/^(assets|renders)\//.test(entry.path)||!/^(FRONT|BACK)\/[0-9]{6}\.png$/.test(entry.name))
                    throw new Error(`Invalid paired ZIP entry.`);
            }

            const worker=new Worker(new URL(`../site/order-zip-worker.js`,import.meta.url),{type:`module`});
            const id=crypto.randomUUID(),task={worker,state:`running`,done:0,total:entries.length};
            task.finished=new Promise(resolve=>{
                const finish=()=>{worker.terminate();resolve();};
                worker.onmessage=event=>{Object.assign(task,event.data);if(task.state!==`running`)finish();};
                worker.onerror=event=>{Object.assign(task,{state:`failed`,error:event.message||`ZIP worker stopped.`});finish();};
                worker.onmessageerror=()=>{Object.assign(task,{state:`failed`,error:`ZIP worker response could not be read.`});finish();};
            });
            try {worker.postMessage({directory:this.directory,path,entries});}
            catch(error){worker.terminate();throw error;}
            this.orderZips.set(id,task);return {id};
        }

        if(operation===`poll-order-zip`||operation===`release-order-zip`) {
            const task=this.orderZips.get(path);
            if(!task)throw new Error(`Paired ZIP task expired.`);
            if(operation===`release-order-zip`) {
                if(task.state===`running`)task.worker.postMessage({cancel:true});
                await task.finished;this.orderZips.delete(path);return {ok:true};
            }

            const fields=[`state`,`done`,`total`,`message`,`error`,`bytes`,`phase`,`saveStage`,`savedBytes`,`totalBytes`,`saveElapsedSeconds`,`saveBytesPerSecond`,`saveEtaSeconds`];
            return Object.fromEntries(fields.filter(key=>task[key]!==undefined).map(key=>[key,task[key]]));
        }

        if(operation===`start-artwork`) {
            const urls=JSON.parse(new TextDecoder().decode(body));
            if(!Array.isArray(urls)||urls.length>10000)
                throw new Error(`Invalid artwork download plan.`);

            const id=crypto.randomUUID(),task={ready:[],pending:urls.length,controller:new AbortController()};
            this.downloads.set(id,task);
            task.finished=this.prefetch(body,task.controller.signal,(url,row)=>{
                task.ready.push({url,...row});task.pending--;
            }).catch(error=>{task.error=error.message;task.pending=0;});
            return {id};
        }

        if(operation===`poll-artwork`||operation===`cancel-artwork`) {
            const task=this.downloads.get(path);
            if(!task)
                throw new Error(`Artwork download plan expired.`);

            if(operation===`cancel-artwork`) {
                task.controller.abort();this.downloads.delete(path);return {ok:true};
            }

            const result={rows:task.ready.splice(0),pending:task.pending,error:task.error};
            if(!task.pending)this.downloads.delete(path);
            return result;
        }

        if(operation===`put-asset`)
            return this.putAsset(path,body);
        if(operation===`prefetch-artwork`)
            return this.prefetch(body);

        if(operation===`read`) {
            await this.close(path);
            const file=await this.file(path);
            return file.slice(Number(query.get(`offset`)),Number(query.get(`offset`))+Number(query.get(`length`)));
        }

        if(operation===`checkpoint`) {
            const handle=await this.directory.getFileHandle(`workspace.sqlite3`,{create:true});
            const writer=await handle.createWritable();await writer.write(body);await writer.close();
            for(const suffix of [`-wal`,`-shm`]) {
                await this.directory.removeEntry(`workspace.sqlite3${suffix}`).catch(error=>{
                    if(error.name!==`NotFoundError`)
                        throw error;
                });
            }

            return {ok:true};
        }

        if(operation===`write`) {
            await (await this.writer(path)).write({type:`write`,position:Number(query.get(`offset`)),data:body});
            return {size:body.byteLength};
        }

        if(operation===`close`) {
            await this.close(path);
            return {ok:true};
        }

        const {directory,name}=await this.parent(path);
        if(operation===`stat`) {
            const handle=await directory.getFileHandle(name).catch(error=>{
                if(error.name!==`TypeMismatchError`)
                    throw error;

                return directory.getDirectoryHandle(name);
            });
            if(handle.kind===`directory`)
                return {directory:true,size:4096,modified:0};

            const file=await handle.getFile();
            return {directory:false,size:file.size,modified:file.lastModified};
        }

        if(operation===`list`) {
            const handle=await directory.getDirectoryHandle(name);
            const names=[];
            for await(const entry of handle.keys()) {
                names.push(entry);
            }

            return names;
        }

        if(operation===`mkdir`) {
            await directory.getDirectoryHandle(name,{create:true});
            return {ok:true};
        }

        if(operation===`create`) {
            await directory.getFileHandle(name,{create:true});
            return {ok:true};
        }

        if(operation===`truncate`) {
            await (await this.writer(path)).truncate(Number(query.get(`size`)));
            await this.close(path);
            return {ok:true};
        }

        if(operation===`remove`) {
            await this.close(path);
            await directory.removeEntry(name);
            this.invalidate(path);
            return {ok:true};
        }

        if(operation===`rename`||operation===`copy`) {
            await this.close(path);
            const destination=query.get(`destination`);
            await this.close(destination);
            const file=await this.file(path);
            const target=await this.parent(destination);
            let existed=false;
            try{await target.directory.getFileHandle(target.name);existed=true;}
            catch(error){if(error.name!==`NotFoundError`)throw error;}
            let writer;
            try{
                writer=await (await target.directory.getFileHandle(target.name,{create:true})).createWritable();
                await file.stream().pipeTo(writer);
            }
            catch(error){
                await writer?.abort().catch(()=>{});
                if(!existed)await target.directory.removeEntry(target.name).catch(()=>{});
                throw error;
            }
            if(operation===`rename`)
                await directory.removeEntry(name);
            this.invalidate(path);this.invalidate(destination);
            return {ok:true};
        }

        throw new Error(`Unknown workspace file operation.`);
    }
    respond = async data => {
        const url=new URL(data.url,location.origin);
        const buffer=url.searchParams.get(`buffer`);
        if(buffer) {
            if(url.searchParams.get(`operation`)!==`write`||!this.inputBuffers.has(buffer))
                throw new Error(`The workspace input buffer is unavailable.`);

            data={...data,body:this.inputBuffers.get(buffer)};
        }

        const result=await this.execute(url.searchParams.get(`operation`),url.searchParams.get(`path`),url.searchParams,data.body);
        if(result instanceof Blob)
            return {status:200,mime:`application/octet-stream`,body:result};

        return {status:200,mime:`application/json`,body:new TextEncoder().encode(JSON.stringify(result))};
    }
    //#endregion Filesystem requests
}
