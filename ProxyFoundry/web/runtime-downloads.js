import {WorkspaceFiles} from './workspace-files.js';

//Network waits live outside the serialized Python queue; completed files use its normal cache.
export class RuntimeDownloads {
    constructor(directory,{files=new WorkspaceFiles(directory),limit=6}={}) {
        this.files=files;this.limit=limit;this.active=0;
        this.pending=new Map();this.queue=[];this.controller=new AbortController();
    }
    load = urls => Promise.all(urls.map(this.get));
    get = url => {
        if(this.pending.has(url))
            return this.pending.get(url);

        const result=new Promise(resolve=>this.queue.push({url,resolve}));
        this.pending.set(url,result);this.pump();
        return result;
    };
    pump = () => {
        while(this.active<this.limit&&this.queue.length) {
            const task=this.queue.shift();this.active++;
            const body=new TextEncoder().encode(JSON.stringify([task.url]));
            this.files.prefetch(body,this.controller.signal).then(rows=>task.resolve({url:task.url,...rows[0]}),error=>task.resolve({url:task.url,error:error.message})).finally(()=>{this.active--;this.pump();});
        }
    };
    acknowledge = rows => {
        for(const row of rows) {
            this.pending.delete(row.url);
        }
    };
    cancel = () => {
        this.controller.abort();this.controller=new AbortController();
        for(const task of this.queue.splice(0)) {
            task.resolve({url:task.url,error:`Runtime download cancelled.`});
        }

        this.pending.clear();
    };
}