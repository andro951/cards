/* Dependency instrumentation only. All card drawing is done by upstream CardConjurer. */
(() => {
  'use strict';
  const NativeImage=window.Image;
  const srcDescriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
  const deferred=new Map(), errors=[];
  const state=window.__PF_RUNTIME={deferred,errors,active:false,required:new Set(),phase:'bootstrap'};
  const post=(type,data={})=>parent.postMessage({...data,source:'pf-native-runtime',type},location.origin);
  state.post=post;
  const localSource=value=>{
    const s=String(value||'');
    if(/^https?:/i.test(s))return '/runtime/remote?url='+encodeURIComponent(s);
    return s;
  };
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
