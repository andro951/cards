"use strict";

//Synchronous Python filesystem calls cross to async browser storage, one bounded chunk at a time.
export function mountWorkspaceFiles(FS,owner) {
    let input=null;
    const call=(operation,path,values={},body=null)=>{
        //Pyodide may expose signed byte views; compare byte values before reusing an input.
        if(operation===`write`&&input&&body?.length===input.bytes.length) {
            let same=true;
            for(let index=0;index<body.length;index++) {
                if((body[index]&255)!==input.bytes[index]){same=false;break;}
            }

            if(same){values={...values,buffer:input.id};body=null;}
        }

        const query=new URLSearchParams({owner,operation,path,...values});
        const request=new XMLHttpRequest();
        request.open(body?`POST`:`GET`,`/workspace-io?${query}`,false);
        request.responseType=`arraybuffer`;
        request.send(body);
        if(request.status!==200) {
            let code=29;
            if(request.status===404)
                code=44;
            if(request.status===409)
                code=55;
            if(request.status===507)
                code=51;
            if(request.status===403)
                code=2;

            throw new FS.ErrnoError(code);
        }

        const bytes=new Uint8Array(request.response);
        return operation===`read`?bytes:JSON.parse(new TextDecoder().decode(bytes));
    };
    const pathOf=node=>{
        const parts=[];
        while(node.parent!==node) {
            parts.unshift(node.name);node=node.parent;
        }

        return [node.workspacePath,...parts].join(`/`);
    };
    const writers=new Map();
    const flushNode=node=>{
        for(const stream of writers.get(node)||[]) {flush(stream);}
    };
    const flush=stream=>{
        if(!stream.pending)
            return;

        try{call(`write`,pathOf(stream.node),{offset:stream.pendingOffset},stream.pending);}
        finally{stream.node.cachedInfo=null;stream.pending=null;}
    };
    const nodeOperations={
        getattr(node) {
            //One writer owns these nodes; all filesystem mutations invalidate cached attributes.
            const info=node.cachedInfo||call(`stat`,pathOf(node));node.cachedInfo=info;
            const time=new Date(info.modified);
            return {dev:1,ino:node.id,mode:node.mode,nlink:1,uid:0,gid:0,rdev:0,
                size:Math.max(info.size,node.pendingSize||0),atime:time,mtime:time,ctime:time,blksize:4096,blocks:Math.ceil(info.size/4096)};
        },
        setattr(node,attributes) {
            flushNode(node);node.cachedInfo=null;
            if(attributes.mode!==undefined)
                node.mode=attributes.mode;
            if(attributes.size!==undefined) {
                call(`truncate`,pathOf(node),{size:attributes.size});node.pendingSize=attributes.size;
            }
        },
        lookup(parent,name) {
            const path=pathOf(parent)+`/`+name;
            const info=call(`stat`,path);
            const node=makeNode(parent,name,(info.directory?16384:32768)|511);node.cachedInfo=info;return node;
        },
        mknod(parent,name,mode) {
            call(FS.isDir(mode)?`mkdir`:`create`,pathOf(parent)+`/`+name);
            return makeNode(parent,name,mode);
        },
        rename(node,parent,name) {
            flushNode(node);
            call(`rename`,pathOf(node),{destination:pathOf(parent)+`/`+name});
            node.parent=parent;node.name=name;node.cachedInfo=null;
        },
        unlink(parent,name) {call(`remove`,pathOf(parent)+`/`+name);},
        rmdir(parent,name) {call(`remove`,pathOf(parent)+`/`+name);},
        readdir(node) {return [`.`,`..`,...call(`list`,pathOf(node))];},
        readlink() {throw new FS.ErrnoError(28);}
    };
    const streamOperations={
        read(stream,buffer,offset,length,position) {
            flushNode(stream.node);
            const bytes=call(`read`,pathOf(stream.node),{offset:position,length});
            buffer.set(bytes,offset>>>0);
            return bytes.length;
        },
        write(stream,buffer,offset,length,position) {
            offset=offset>>>0;
            if(!writers.has(stream.node))writers.set(stream.node,new Set());
            writers.get(stream.node).add(stream);
            //Batch tiny ZIP writes without retaining the archive in Python's filesystem.
            if(stream.pending&&stream.pendingOffset+stream.pending.length===position&&stream.pending.length+length<=65536) {
                const combined=new Uint8Array(stream.pending.length+length);
                combined.set(stream.pending);combined.set(buffer.subarray(offset,offset+length),stream.pending.length);stream.pending=combined;
            }
            else {
                flush(stream);stream.pending=buffer.slice(offset,offset+length);stream.pendingOffset=position;
            }

            stream.node.pendingSize=Math.max(stream.node.pendingSize||0,position+length);
            if(stream.pending.length>=65536)
                flush(stream);

            return length;
        },
        llseek(stream,offset,whence) {
            if(whence===1)
                offset+=stream.position;
            if(whence===2)
                offset+=nodeOperations.getattr(stream.node).size;
            if(offset<0)
                throw new FS.ErrnoError(28);

            return offset;
        },
        fsync(stream) {flush(stream);call(`close`,pathOf(stream.node));return 0;},
        close(stream) {
            try{flush(stream);call(`close`,pathOf(stream.node));}
            finally{
                stream.pending=null;stream.node.pendingSize=0;stream.node.cachedInfo=null;
                writers.get(stream.node)?.delete(stream);
                if(!writers.get(stream.node)?.size)writers.delete(stream.node);
            }
        }
    };
    const makeNode=(parent,name,mode)=>{
        const node=FS.createNode(parent,name,mode,0);
        node.node_ops=nodeOperations;node.stream_ops=streamOperations;
        return node;
    };
    const filesystem={mount(mount) {
        const root=makeNode(null,`/`,16895);root.workspacePath=mount.opts.path;return root;
    }};
    for(const name of [`assets`,`renders`,`runtime`,`orders`,`logs`,`backups`,`tmp`]) {
        const path=`/workspace/${name}`;
        FS.mkdirTree(path);call(`mkdir`,name);FS.mount(filesystem,{path:name},path);
    }

    return {
        setInput:(id,bytes)=>{input=bytes.length>=65536?{id,bytes}:null;},
        clearInput:()=>{input=null;},
        copyFile:(source,destination)=>call(`copy`,source,{destination})
    };
}
