"use strict";

//Binary files stay in the selected browser/folder workspace, outside Python memory.
export class WorkspaceFiles {
    constructor(directory,downloadStaging=directory) {
        this.directory=directory;
        this.downloadStaging=downloadStaging;
        this.writers=new Map();
        this.inputBuffers=new Map();
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
        if(parts[0]===`tmp`&&parts[1]===`review-downloads`) {
            //Review exports are temporary browser files, never selected-folder order packages.
            directory=this.downloadStaging;parts.shift();
        }

        for(const part of parts.slice(0,-1)) {
            directory=await directory.getDirectoryHandle(part,{create});
        }

        return {directory,name:parts.at(-1)};
    }
    file = async path => {
        const {directory,name}=await this.parent(path);
        return (await directory.getFileHandle(name)).getFile();
    }
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

    //#region Filesystem requests
    execute = async (operation,path,query,body) => {
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
