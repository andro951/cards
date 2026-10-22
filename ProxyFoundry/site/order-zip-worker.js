import {StoredZip,crc32} from './stored-zip.js';

let cancelled=false;
const check=()=>{if(cancelled)throw new Error(`Order packaging cancelled.`);};
const parent=async(root,path)=>{
    const parts=path.split(`/`);let directory=root;
    for(const name of parts.slice(0,-1)) {directory=await directory.getDirectoryHandle(name);}
    return {directory,name:parts.at(-1)};
};
const build=async({directory,path,entries})=>{
    let writer;
    try {
        const zip=new StoredZip(),files=new Map();
        for(let index=0;index<entries.length;index++) {
            check();const entry=entries[index];
            if(!files.has(entry.path)) {
                const source=await parent(directory,entry.path),file=await (await source.directory.getFileHandle(source.name)).getFile();
                files.set(entry.path,{file,crc:await crc32(file,()=>cancelled)});
            }

            check();const {file,crc}=files.get(entry.path);zip.add(entry.name,file,crc);
            self.postMessage({state:`running`,done:index+1,total:entries.length,message:`Packaging ${entry.label}`});
        }

        check();const archive=zip.finish(),target=await parent(directory,path);
        writer=await (await target.directory.getFileHandle(target.name,{create:true})).createWritable();
        self.postMessage({state:`running`,done:entries.length,total:entries.length,message:`Saving paired ZIP…`});
        await writer.write(archive);check();await writer.close();writer=null;
        self.postMessage({state:`done`,done:entries.length,total:entries.length,bytes:archive.size,message:`Paired ZIP saved`});
    }
    catch(error) {
        if(writer)await writer.abort().catch(abortError=>{error.message+=` ${abortError.message}`;});
        self.postMessage({state:cancelled?`cancelled`:`failed`,error:error.message,done:0,total:entries.length});
    }
};
self.onmessage=event=>{
    if(event.data.cancel){cancelled=true;return;}
    void build(event.data);
};