/* Dependency instrumentation only. All card drawing is done by upstream CardConjurer. */
(() => {
  'use strict';
  window.__PF_PARENT_ORIGIN=document.querySelector('meta[name="pf-parent-origin"]')?.content||location.origin;
  // Large custom templates need not fit the browser's localStorage quota.
  // Native loadCard still calls its original Storage interface; only our ephemeral
  // per-face keys are held in memory and released after export.
  const temporaryCards=new Map(), storage=window.localStorage;
  const get=Storage.prototype.getItem, set=Storage.prototype.setItem, remove=Storage.prototype.removeItem;
  Storage.prototype.getItem=function(k){return this===storage&&String(k).startsWith('__pf_')?(temporaryCards.get(String(k))??null):get.call(this,k);};
  Storage.prototype.setItem=function(k,v){if(this===storage&&String(k).startsWith('__pf_'))temporaryCards.set(String(k),String(v));else set.call(this,k,v);};
  Storage.prototype.removeItem=function(k){if(this===storage&&String(k).startsWith('__pf_'))temporaryCards.delete(String(k));else remove.call(this,k);};
  const NativeImage=window.Image;
  const srcDescriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
  const deferred=new Map(), errors=[];
  const state=window.__PF_RUNTIME={deferred,errors,active:false,required:new Set(),phase:'bootstrap'};
  const post=(type,data={})=>parent.postMessage({...data,source:'pf-native-runtime',type},window.__PF_PARENT_ORIGIN||location.origin);
  state.post=post;
  const localSource=value=>{
    const s=String(value||'');
    if(/^https?:/i.test(s)){
      const url=new URL(s);
      if(url.origin===location.origin)return url.pathname+url.search;
      return '/runtime/remote?url='+encodeURIComponent(s);
    }
    return s;
  };
  state.resolveSource=localSource;
  window.Image=function(...args){
    const image=new NativeImage(...args);
    Object.defineProperty(image,'src',{configurable:true,get(){return srcDescriptor.get.call(this)},set(value){
      const s=String(value||'');
      if(s.startsWith('/img/manaSymbols/')&&!state.required.has(s)){
        deferred.set(image,s);return;
      }
      deferred.delete(image);srcDescriptor.set.call(image,localSource(s));
    }});
    return image;
  };
  window.Image.prototype=NativeImage.prototype;
  state.requireImage=image=>{
    const path=deferred.get(image);
    if(path){state.required.add(path);image.src=path;}
  };
  state.clearErrors=()=>{errors.length=0;};
  window.addEventListener('error',e=>{
    const resource=e.target!==window?(e.target.src||e.target.href||''):null;
    if(resource&&/Thumb\.png/i.test(resource))return;
    errors.push({phase:state.phase,message:resource?'Failed resource: '+resource:e.message,stack:e.error?.stack||null});
    if(errors.length>50)errors.shift();
  },true);
  window.addEventListener('unhandledrejection',e=>{
    errors.push({phase:state.phase,message:e.reason?.message||String(e.reason),stack:e.reason?.stack||null});
    if(errors.length>50)errors.shift();
  });
  // Use the same explicit preferences as the successful v4 harness.
  try{
    localStorage.setItem('autoLoadFrameVersion','false');localStorage.setItem('autoFrame','false');
    localStorage.setItem('enableCollectorInfo','true');localStorage.setItem('enableNewCollectorStyle','false');
    localStorage.setItem('lockSetSymbolCode','');localStorage.setItem('lockSetSymbolURL','');
    localStorage.setItem('cardKeys','[]');
  }catch(e){errors.push({phase:'bootstrap',message:'Native storage unavailable: '+e.message});}
})();
