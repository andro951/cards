"use strict";

export class BrowserRenderSave {
    constructor(directory,api){
        this.directory=directory;this.api=api;this.pending=0;this.lastCommit=performance.now();
    }
    static async open(api,directory=window.__pfWorkspaceDirectory){
        if(!directory)throw new Error(`The workspace is not connected. Reload before generating images.`);
        const saver=new BrowserRenderSave(directory,api);
        saver.assets=await directory.getDirectoryHandle(`assets`,{create:true});
        const temporary=await directory.getDirectoryHandle(`tmp`,{create:true});
        saver.journal=await temporary.getDirectoryHandle(`render-pending`,{create:true});
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
        const bitmap=await createImageBitmap(blob);
        const valid=bitmap.width===width&&bitmap.height===height;bitmap.close();
        if(!valid)throw new Error(`The rendered PNG could not be validated.`);
        const hash=[...new Uint8Array(await crypto.subtle.digest(`SHA-256`,bytes))].map(value=>value.toString(16).padStart(2,`0`)).join(``);
        const folder=await this.assets.getDirectoryHandle(hash.slice(0,2),{create:true});
        await this.write(folder,hash,blob);
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