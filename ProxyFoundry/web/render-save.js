"use strict";

export class BrowserRenderSave {
    constructor(directory,api,generation=null){
        this.directory=directory;this.api=api;this.pending=0;this.lastCommit=performance.now();
        this.generation=generation;this.rows=[];this.folders=new Map();this.writes=new Map();
    }
    static async open(api,directory=window.__pfWorkspaceDirectory,generation=null){
        if(!directory)throw new Error(`The workspace is not connected. Reload before generating images.`);
        const saver=new BrowserRenderSave(directory,api,generation);
        saver.assets=await directory.getDirectoryHandle(`assets`,{create:true});
        if(!generation) {
            const temporary=await directory.getDirectoryHandle(`tmp`,{create:true});
            saver.journal=await temporary.getDirectoryHandle(`render-pending`,{create:true});
        }

        return saver;
    }
    write = async (directory,name,data) => {
        const handle=await directory.getFileHandle(name,{create:true});
        const stream=await handle.createWritable();
        //pipeTo aborts the destination on failure; only close publishes the complete file.
        await (data instanceof Blob?data:new Blob([data])).stream().pipeTo(stream);
    };
    save = async (target,output) => {
        const {blob,width,height}=output;
        if(!(blob instanceof Blob)||!blob.size||blob.size>64*1024*1024||width*height>48000000)
            throw new Error(`The renderer returned an invalid PNG.`);
        const bytes=await blob.arrayBuffer();
        if(bytes.byteLength<33)throw new Error(`The renderer returned an incomplete PNG.`);
        const header=new DataView(bytes);
        if(header.getUint32(0)!==0x89504e47||header.getUint32(4)!==0x0d0a1a0a||header.getUint32(16)!==width||header.getUint32(20)!==height)
            throw new Error(`The rendered PNG dimensions do not match the card.`);
        if(this.generation) {
            //Native canvas just encoded this PNG. Check its end marker without decoding it again.
            if(bytes.byteLength<45||header.getUint32(bytes.byteLength-12)!==0||header.getUint32(bytes.byteLength-8)!==0x49454e44)
                throw new Error(`The renderer returned an incomplete PNG.`);
        }
        else {
            const bitmap=await createImageBitmap(blob);
            const valid=bitmap.width===width&&bitmap.height===height;bitmap.close();
            if(!valid)
                throw new Error(`The rendered PNG could not be validated.`);
        }

        const hash=[...new Uint8Array(await crypto.subtle.digest(`SHA-256`,bytes))].map(value=>value.toString(16).padStart(2,`0`)).join(``);
        const prefix=hash.slice(0,2);
        if(!this.folders.has(prefix))
            this.folders.set(prefix,this.assets.getDirectoryHandle(prefix,{create:true}));

        const folder=await this.folders.get(prefix);
        if(!this.writes.has(hash)) {
            const written=this.write(folder,hash,blob).catch(error=>{this.writes.delete(hash);throw error;});
            this.writes.set(hash,written);
        }

        await this.writes.get(hash);
        if(this.generation) {
            this.rows.push({...target,hash,width,height,bytes:blob.size});
            return;
        }

        //A durable receipt precedes grouped metadata. Startup replays uncommitted receipts.
        await this.write(this.journal,`${crypto.randomUUID()}.json`,JSON.stringify({...target,hash,width,height,bytes:blob.size}));
        this.pending++;
        if(this.pending>=10||performance.now()-this.lastCommit>=2000)await this.flush();
    };
    flush = async () => {
        if(!this.pending)return;
        await this.api(`/api/render-saves/commit`,{});
        this.pending=0;this.lastCommit=performance.now();
    };
}
