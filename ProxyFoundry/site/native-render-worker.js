//Minimal native control adapter. CardConjurer remains responsible for every pixel.
(() => {
    const basePath='';
    const nativeFetch=fetch.bind(self);
    const owner=new URLSearchParams(location.search).get(`owner`)||``;
    const route=path=>{
        if(/^(?:blob:|data:)/.test(path))return path;
        const url=new URL(path,location.origin+basePath+`/`);
        if(url.origin===location.origin&&!url.pathname.startsWith(basePath+`/`))url.pathname=basePath+url.pathname;
        if(url.origin===location.origin)url.searchParams.set(`owner`,owner);
        return url.href;
    };
    self.fetch=(path,options)=>nativeFetch(typeof path===`string`?route(path):path,options);
    self.window=self;
    self.__PF_WORKER_CORE=true;
    self.parent={postMessage:message=>self.postMessage(message)};
    self.CanvasRenderingContext2D=OffscreenCanvasRenderingContext2D;
    self.HTMLCanvasElement=OffscreenCanvas;
    self.XMLSerializer=class {
        serializeToString(node){return node.xml;}
    };
    self.XMLHttpRequest=class {
        open(method,path){this.method=method;this.path=path;}
        overrideMimeType(){}
        send(){
            self.fetch(this.path).then(async response=>{
                this.status=response.status;this.readyState=4;
                this.responseXML={documentElement:{xml:await response.text()}};
                this.onload?.call(this);
            }).catch(error=>{this.onerror?.(error);self.__PF_RUNTIME?.errors.push({phase:self.__PF_RUNTIME.phase,message:error.message,stack:error.stack});});
        }
    };
    class MemoryStorage {
        entries=new Map();
        getItem(key){return this.entries.get(String(key))??null;}
        setItem(key,value){this.entries.set(String(key),String(value));}
        removeItem(key){this.entries.delete(String(key));}
    }
    self.Storage=MemoryStorage;
    self.localStorage=new MemoryStorage();
    const svgRequests=new Map();let svgSequence=0;
    const decodeWithHost=(blob,geometry=null)=>{
        return new Promise((resolve,reject)=>{
            const id=++svgSequence;svgRequests.set(id,{resolve,reject});
            self.postMessage({type:`decode-svg`,id,blob,geometry});
        });
    };
    const decodeImage=blob=>blob.type===`image/svg+xml`?decodeWithHost(blob):createImageBitmap(blob).catch(()=>decodeWithHost(blob));
    const decoded=new Map();
    const pruneDecoded=()=>{
        let bytes=[...decoded.values()].reduce((total,entry)=>total+(entry.bitmap?.width||0)*(entry.bitmap?.height||0)*4,0);
        for(const [source,entry] of decoded){
            if(bytes<=64*1024*1024)break;
            if(entry.users.size||!entry.bitmap)continue;
            bytes-=entry.bitmap.width*entry.bitmap.height*4;entry.bitmap.close();decoded.delete(source);
        }
    };
    self.addEventListener(`message`,event=>{
        if(event.data?.type!==`decoded-svg`)return;
        const request=svgRequests.get(event.data.id);if(!request)return;
        svgRequests.delete(event.data.id);
        if(event.data.error)request.reject(new Error(event.data.error));else request.resolve(event.data.bitmap);
    });
    class WorkerImage extends EventTarget {
        generation=0;
        complete=false;
        width=0; height=0; naturalWidth=0; naturalHeight=0;
        get src(){return this.source||``;}
        set src(value){
            this.dispose();
            const generation=++this.generation;
            this.source=String(value);this.complete=false;
            //Frame-picker thumbnails have no role in card output.
            if(/Thumb\.png(?:\?|$)/i.test(this.source))return;
            const source=this.source;
            let entry=decoded.get(this.source);
            if(!entry){
                entry={users:new Set()};decoded.set(this.source,entry);
                entry.promise=self.fetch(this.source).then(response=>{
                    if(!response.ok)throw new Error(`Image request failed: ${response.status} ${source}`);
                    return response.blob();
                }).then(async blob=>{entry.blob=blob;entry.bitmap=await decodeImage(blob);return entry.bitmap;});
                entry.promise.catch(()=>decoded.delete(source));
            }
            entry.users.add(this);this.entry=entry;
            entry.promise.then(bitmap=>{
                if(generation!==this.generation)return;
                this.bitmap=bitmap;this.blob=entry.blob;
                this.width=this.naturalWidth=bitmap.width;this.height=this.naturalHeight=bitmap.height;this.complete=true;
                const event=new Event(`load`);this.dispatchEvent(event);this.onload?.call(this,event);
            }).catch(error=>{
                if(generation!==this.generation)return;
                this.complete=true;this.naturalWidth=this.naturalHeight=0;
                const event=new Event(`error`);this.dispatchEvent(event);this.onerror?.call(this,event);
                self.__PF_RUNTIME?.errors.push({phase:self.__PF_RUNTIME.phase,message:error.message,stack:error.stack});
            });
        }
        dispose = () => {this.entry?.users.delete(this);this.entry=null;this.bitmap=null;};
        setAttribute = (name,value) => {this[name]=value;};
        getAttribute = name => this[name]??null;
    }
    self.Image=self.HTMLImageElement=WorkerImage;
    const vectorDraws=new Map();
    self.__PF_RELEASE_IMAGES=()=>{
        pruneDecoded();
        let bytes=[...vectorDraws.values()].reduce((total,entry)=>total+(entry.bitmap?.width||0)*(entry.bitmap?.height||0)*4,0);
        for(const [key,entry] of vectorDraws){
            if(bytes<=64*1024*1024&&vectorDraws.size<=256)break;
            bytes-=(entry.bitmap?.width||0)*(entry.bitmap?.height||0)*4;
            entry.bitmap?.close();vectorDraws.delete(key);
        }
    };
    self.__PF_PREPARE_VECTORS=async()=>{
        await Promise.all([...vectorDraws.values()].filter(entry=>!entry.bitmap).map(async entry=>{
            entry.bitmap=await decodeWithHost(entry.image.blob,entry.arguments);
        }));
    };
    const drawImage=OffscreenCanvasRenderingContext2D.prototype.drawImage;
    OffscreenCanvasRenderingContext2D.prototype.drawImage=function(image,...arguments){
        if(image instanceof WorkerImage){
            if(!image.bitmap)return;
            if(image.blob?.type===`image/svg+xml`&&arguments.length===4&&arguments[2]>0&&arguments[3]>0){
                const key=image.src+JSON.stringify(arguments);let entry=vectorDraws.get(key);
                if(!entry){entry={image,arguments};vectorDraws.set(key,entry);}
                if(entry.bitmap)return drawImage.call(this,entry.bitmap,Math.floor(arguments[0]),Math.floor(arguments[1]));
            }
            image=image.bitmap;
        }
        return drawImage.call(this,image,...arguments);
    };
    const elements=new Map();
    const controls=new Set();
    const decode=value=>String(value).replaceAll(`&quot;`,`"`).replaceAll(`&amp;`,`&`).replaceAll(`&lt;`,`<`).replaceAll(`&gt;`,`>`).replaceAll(`&#39;`,`'`);
    class Control extends EventTarget {
        constructor(tag=`div`,attributes={}){
            super();this.tagName=tag.toUpperCase();this.attributes={...attributes};
            controls.add(this);
            this.children=[];this.style={setProperty:()=>{}};this.value=attributes.value||``;this.checked=`checked` in attributes;
            this.classes=new Set((attributes.class||``).split(/\s+/));
            this.classMethods={add:(...names)=>names.forEach(name=>this.classes.add(name)),remove:(...names)=>names.forEach(name=>this.classes.delete(name)),contains:name=>this.classes.has(name),toggle:name=>this.classes.has(name)?this.classes.delete(name):this.classes.add(name)};
            if(attributes.id)elements.set(attributes.id,this);
        }
        get id(){return this.attributes.id||``;}
        get value(){return this.inputValue||``;}
        set value(value){this.inputValue=String(value??``);}
        get classList(){return this.classMethods;}
        set classList(value){this.classes=new Set(String(value).split(/\s+/));}
        set id(value){this.attributes.id=value;elements.set(value,this);}
        get firstChild(){return this.children[0]||null;}
        get lastChild(){return this.children.at(-1)||null;}
        get childNodes(){return this.children;}
        get innerHTML(){return this.markup||``;}
        set innerHTML(value){
            this.markup=String(value??``);
            const release=element=>{for(const child of element.children||[])release(child);element.dispose?.();controls.delete(element);if(elements.get(element.id)===element)elements.delete(element.id);};
            for(const child of this.children)release(child);
            this.children=[];
            const stack=[this];
            for(const match of this.markup.matchAll(/<\/?([a-zA-Z][\w-]*)([^>]*)>/g)){
                if(match[0].startsWith(`</`)){if(stack.length>1)stack.pop();continue;}
                const attributes={};
                for(const attribute of match[2].matchAll(/([\w-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attributes[attribute[1]]=decode(attribute[2]??attribute[3]??attribute[4]??``);
                const child=new Control(match[1],attributes);stack.at(-1).appendChild(child);
                if(![`input`,`img`,`br`,`hr`,`meta`,`link`].includes(match[1].toLowerCase())&&!match[0].endsWith(`/>`))stack.push(child);
            }
        }
        appendChild = child => {
            child.parentElement=child.parentNode=this;this.children.push(child);
            if(this.tagName===`SELECT`&&this.children.length===1)this.value=child.value;
            if(child.tagName===`SCRIPT`){
                Promise.resolve().then(()=>importScripts(route(child.src||child.attributes.src))).then(()=>child.onload?.()).catch(error=>{child.onerror?.(error);self.__PF_RUNTIME?.errors.push({phase:self.__PF_RUNTIME.phase,message:error.message,stack:error.stack});});
            }
            return child;
        };
        append = (...children) => children.forEach(this.appendChild);
        prepend = child => {child.parentElement=child.parentNode=this;this.children.unshift(child);};
        remove = () => {if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(child=>child!==this);};
        setAttribute = (name,value) => {this.attributes[name]=String(value);if(name===`src`)this.src=value;if(name===`id`)this.id=value;};
        getAttribute = name => this.attributes[name]??null;
        querySelector = query => query.startsWith(`#`)?elements.get(query.slice(1))||null:this.children.find(child=>child.tagName.toLowerCase()===query)||null;
        querySelectorAll = query => query.startsWith(`#`)?[this.querySelector(query)].filter(Boolean):[];
        click = () => {
            const event={target:this,currentTarget:this,stopPropagation:()=>{},preventDefault:()=>{}};
            if(this.onclick)this.onclick(event);
            else{
                const handler=this.attributes.onclick?.match(/^([\w]+)\(event\)/)?.[1];
                if(handler&&typeof self[handler]===`function`)self[handler](event);
            }
        };
        closest = () => this;
        focus = () => {};
    }
    const create=tag=>{
        if(tag===`canvas`){
            const canvas=new OffscreenCanvas(300,150);
            canvas.cloneNode=()=>{const copy=create(`canvas`);copy.width=canvas.width;copy.height=canvas.height;return copy;};
            return canvas;
        }
        if(tag===`img`)return new WorkerImage();
        return new Control(tag);
    };
    const head=new Control(`head`);
    const select=query=>{
        if(query.startsWith(`#`))return elements.get(query.slice(1))||null;
        if(query.startsWith(`.`))return [...controls].find(control=>query.slice(1).split(`.`).every(name=>control.classes.has(name)))||null;
        return [...controls].find(control=>control.tagName.toLowerCase()===query)||null;
    };
    self.document={head,body:new Control(`body`),documentElement:new Control(`html`),fonts:self.fonts,
        createElement:create,createDocumentFragment:()=>new Control(),getElementById:id=>elements.get(id)||null,
        querySelector:select,
        querySelectorAll:query=>query===`head`?[head]:query.startsWith(`#`)?[elements.get(query.slice(1))].filter(Boolean):[],
        addEventListener:()=>{},removeEventListener:()=>{}
    };
    const restore=data=>{
        const element=create(data.tag);
        if(element instanceof Control){for(const [key,value] of Object.entries(data.attributes))element.setAttribute(key,value);element.value=data.value;element.checked=data.checked;}
        element.style={};
        for(const child of data.children||[])element.appendChild?.(restore(child));
        if(data.attributes.id)elements.set(data.attributes.id,element);
        return element;
    };
    self.addEventListener(`message`,async event=>{
        if(event.data?.type!==`initialize`)return;
        try{
            document.body=restore(event.data.controls);
            const css=await (await self.fetch(`/runtime/fonts.css`)).text();
            for(const match of css.matchAll(/@font-face\s*\{([^}]+)\}/g)){
                const family=match[1].match(/font-family\s*:\s*([^;]+)/i)?.[1].trim().replace(/^['"]|['"]$/g,``);
                const source=match[1].match(/url\(['"]?([^)'"]+)/i)?.[1];
                if(!family||!source)throw new Error(`Native font definition is incomplete.`);
                const descriptors={};
                for(const key of ['style','weight','stretch']){
                    const value=match[1].match(new RegExp(`font-${key}\\s*:\\s*([^;]+)`,`i`))?.[1].trim();
                    if(value)descriptors[key]=value;
                }
                const font=new FontFace(family,`url("${route(source)}")`,descriptors);self.fonts.add(font);
            }
            importScripts(route('/site/runtime-hooks.js'),route(`/js/main-1.js`),route(`/js/creator-23.js`),route('/site/runtime-bridge.js'));
        }catch(error){self.postMessage({source:`pf-native-runtime`,type:`failed`,error:error.stack||error.message});}
    });
})();
