export class RuntimeAssets {
    constructor({limit=64*1024*1024,fetchAsset=fetch.bind(globalThis),urls=URL}={}) {
        this.limit=limit;
        this.fetchAsset=fetchAsset;
        this.urls=urls;
        this.entries=new Map();
        this.pending=new Map();
        this.pinned=new Set();
        this.bytes=0;
        this.closed=false;
        this.controller=new AbortController();
    }
    //Only immutable workspace images and pinned runtime assets enter this cache.
    accepts = path => typeof path===`string` && (/^\/api\/assets\/[a-f0-9]{64}$/.test(path) || /^\/img\/(?!.*(?:\.\.|[?#]))[A-Za-z0-9_./-]+$/.test(path));
    get = async path => {
        if(this.closed)
            throw new Error(`Renderer asset cache is closed.`);

        const existing=this.entries.get(path);
        if(existing) {
            this.entries.delete(path);this.entries.set(path,existing);
            return existing.url;
        }

        if(this.pending.has(path))
            return this.pending.get(path);

        const job=this.load(path);
        this.pending.set(path,job);
        return job.finally(()=>this.pending.delete(path));
    };
    load = async path => {
        const response=await this.fetchAsset(path,{signal:this.controller.signal});
        if(!response.ok)
            throw new Error(`Renderer image could not load (${response.status}): ${path}`);

        const blob=await response.blob();
        if(this.closed)
            throw new Error(`Renderer asset loading was cancelled.`);

        const entry={url:this.urls.createObjectURL(blob),bytes:blob.size};
        this.entries.set(path,entry);this.bytes+=entry.bytes;
        this.prune();
        return entry.url;
    };
    acquire = async data => {
        const paths=new Set([data.artSource,data.setSymbolSource,data.watermarkSource]);
        for(const frame of data.frames||[]) {
            paths.add(frame.src);
            for(const mask of frame.masks||[]) {
                paths.add(mask.src);
            }
        }

        this.pinned=new Set([...paths].filter(this.accepts));
        await Promise.all([...this.pinned].map(this.get));
        const source=path=>this.entries.get(path)?.url||path;
        for(const name of [`artSource`,`setSymbolSource`,`watermarkSource`]) {
            if(data[name])data[name]=source(data[name]);
        }

        for(const frame of data.frames||[]) {
            frame.src=source(frame.src);
            for(const mask of frame.masks||[]) {
                mask.src=source(mask.src);
            }
        }

        this.prune();
    };
    prune = () => {
        for(const [path,entry] of this.entries) {
            if(this.bytes<=this.limit)break;
            if(this.pinned.has(path))continue;
            this.entries.delete(path);this.bytes-=entry.bytes;this.urls.revokeObjectURL(entry.url);
        }
    };
    release = () => {
        this.pinned.clear();this.prune();
    };
    dispose = () => {
        this.closed=true;this.controller.abort();
        for(const entry of this.entries.values()) {
            this.urls.revokeObjectURL(entry.url);
        }

        this.entries.clear();this.pinned.clear();this.bytes=0;
    };
}
