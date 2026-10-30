import {StoredZip,crc32,PRINTER_ZIP_LIMIT,storedEntryBytes} from './stored-zip.js';

let cancelled=false;
const check=()=>{if(cancelled)throw new Error(`Order packaging cancelled.`);};
const parent=async(root,path)=>{
    const parts=path.split(`/`);let directory=root;
    for(const name of parts.slice(0,-1)) {directory=await directory.getDirectoryHandle(name);}
    return {directory,name:parts.at(-1)};
};
const build=async({directory,path,entries})=>{
    let writer,heartbeat,saveStarted=0,lastReport=0;
    const saving={phase:`saving`,savedBytes:0,totalBytes:0,saveStage:`opening`};
    const reportSaving=()=>{
        const now=performance.now(),elapsed=(now-saveStarted)/1000;
        const rate=elapsed>0?saving.savedBytes/elapsed:0;
        lastReport=now;
        self.postMessage({state:`running`,done:entries.length,total:entries.length,...saving,
            saveElapsedSeconds:elapsed,saveBytesPerSecond:rate,
            saveEtaSeconds:rate>0&&saving.saveStage===`writing`?(saving.totalBytes-saving.savedBytes)/rate:null,
            message:saving.saveStage===`finalizing`?`Finalizing paired ZIP…`:`Saving paired ZIP…`});
    };
    try {
        let zip=new StoredZip(),partBytes=22,first=1;const archives=[],files=new Map();
        const finishPart=last=>{archives.push({blob:zip.finish(),firstCard:first,lastCard:last,count:last-first+1});zip=new StoredZip();partBytes=22;first=last+1;};
        for(let index=0;index<entries.length;index++) {
            check();const entry=entries[index];
            if(index%2===0){
                let pairBytes=0;
                for(const item of entries.slice(index,index+2)){
                    if(!files.has(item.path)){
                        const source=await parent(directory,item.path),file=await (await source.directory.getFileHandle(source.name)).getFile();
                        files.set(item.path,{file,crc:await crc32(file,()=>cancelled)});
                    }
                    pairBytes+=storedEntryBytes(item.name,files.get(item.path).file.size);
                }
                if(pairBytes+22>PRINTER_ZIP_LIMIT)throw new Error(`A front/back pair exceeds the printer ZIP limit.`);
                if(zip.entries.length&&partBytes+pairBytes>PRINTER_ZIP_LIMIT)finishPart(index/2);
                partBytes+=pairBytes;
            }
            if(!files.has(entry.path)) {
                const source=await parent(directory,entry.path),file=await (await source.directory.getFileHandle(source.name)).getFile();
                files.set(entry.path,{file,crc:await crc32(file,()=>cancelled)});
            }

            check();const {file,crc}=files.get(entry.path);zip.add(entry.name,file,crc);
            self.postMessage({state:`running`,phase:`packaging`,done:index+1,total:entries.length,message:`Packaging ${entry.label}`});
        }

        finishPart(entries.length/2);check();
        const target=await parent(directory,path),folder=await target.directory.getDirectoryHandle(target.name,{create:true});
        saving.totalBytes=archives.reduce((sum,part)=>sum+part.blob.size,0);saveStarted=performance.now();reportSaving();
        heartbeat=setInterval(reportSaving,1000);
        const parts=[];let previousBytes=0;
        //Keep native Blob copying, with bounded writes for measurable progress
        //and cancellation instead of one opaque multi-gigabyte operation.
        const chunkSize=64*1024*1024;
        for(const [index,part] of archives.entries()){
            const filename=`part-${String(index+1).padStart(3,'0')}.zip`,archive=part.blob;
            if(archive.size>PRINTER_ZIP_LIMIT)throw new Error(`Printer ZIP limit exceeded.`);
            writer=await (await folder.getFileHandle(filename,{create:true})).createWritable();saving.saveStage=`writing`;
            for(let offset=0;offset<archive.size;offset+=chunkSize) {
                check();const chunk=archive.slice(offset,offset+chunkSize);
                check();await writer.write(chunk);check();saving.savedBytes=previousBytes+offset+chunk.size;
                if(performance.now()-lastReport>=250)reportSaving();
            }
            saving.saveStage=`finalizing`;reportSaving();await writer.close();writer=null;check();
            previousBytes+=archive.size;parts.push({filename,count:part.count,firstCard:part.firstCard,lastCard:part.lastCard,zipBytes:archive.size});
        }
        self.postMessage({state:`done`,done:entries.length,total:entries.length,bytes:saving.totalBytes,parts,...saving,
            saveStage:`complete`,saveElapsedSeconds:(performance.now()-saveStarted)/1000,saveEtaSeconds:0,message:`Paired ZIP saved`});
    }
    catch(error) {
        if(writer)await writer.abort().catch(abortError=>{error.message+=` ${abortError.message}`;});
        self.postMessage({state:cancelled?`cancelled`:`failed`,error:error.message,done:0,total:entries.length});
    }
    finally {clearInterval(heartbeat);}
};
self.onmessage=event=>{
    if(event.data.cancel){cancelled=true;return;}
    void build(event.data);
};
