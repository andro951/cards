/* Adapter for the genuine CardConjurer loadCard/cardCanvas path. No replacement renderer. */
(() => {
  'use strict';
  const S=window.__PF_RUNTIME,post=S.post,sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const pendingScripts=new Set();
  const timeout=(promise,ms,label)=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(label+' timed out after '+Math.round(ms/1000)+' seconds.')),ms);Promise.resolve(promise).then(x=>{clearTimeout(timer);resolve(x)},e=>{clearTimeout(timer);reject(e)});});
  async function waitFor(fn,ms,label){const start=Date.now();while(Date.now()-start<ms){if(fn())return;await sleep(50)}throw new Error(label+' did not initialize.');}
  // Replace only script orchestration, not the native frame, text or canvas logic.
  const loadedScripts=new Map();
  window.loadScript=function(path){
    if(!/^\/js\/[A-Za-z0-9_./-]+\.js$/.test(path)||path.split('/').includes('..'))return Promise.reject(new Error('Untrusted CardConjurer script: '+path));
    if(loadedScripts.has(path))return loadedScripts.get(path);
    const job=timeout(new Promise((resolve,reject)=>{const el=document.createElement('script');el.src=path;el.onload=resolve;el.onerror=()=>reject(new Error('CardConjurer script failed: '+path));document.head.append(el);}),30000,path);
    pendingScripts.add(job);job.finally(()=>{pendingScripts.delete(job);loadedScripts.delete(path);}).catch(()=>{});loadedScripts.set(path,job);return job;
  };
  const nativeTextBuffer=window.drawTextBuffer;
  window.drawTextBuffer=function(...args){if(S.active&&S.phase!=='render')return;return nativeTextBuffer?.apply(this,args);};
  async function scriptsSettled(){while(pendingScripts.size)await Promise.all([...pendingScripts]);}
  function usedSymbols(data){
    const symbols=new Set();
    for(const obj of [...Object.values(data.text||{}),...Object.values(data.bottomInfo||{})]){
      const text=String(obj?.text||'');
      const tokens=[...text.matchAll(/\{([^{}]+)\}/g)].map(m=>m[1].toLowerCase().replaceAll('/',''));
      if(text.includes('{flavor}')||text.includes('{divider}'))tokens.push(data.version==='cartoony'?'cflavor':'bar');
      if(text.includes('{planechase}'))tokens.push('chaos');
      for(const token of tokens){
        let sym=window.getManaSymbol?.((obj.manaPrefix||'')+token)||window.getManaSymbol?.(token)||window.getManaSymbol?.(token.split('').reverse().join(''));
        if(!sym)continue;symbols.add(sym);
        if(sym.backs)for(let i=0;i<sym.backs;i++){const back=window.getManaSymbol('back'+i+sym.back);if(back)symbols.add(back);}
      }
    }
    return [...symbols];
  }
  function imagesFor(data,symbols){
    const out=[['art',window.art],['set symbol',window.setSymbol],['watermark',window.watermark]];
    (window.card?.frames||[]).forEach((f,i)=>{out.push(['frame '+i,f.image]);(f.masks||[]).forEach((m,j)=>out.push(['frame '+i+' mask '+j,m.image]));});
    symbols.forEach(s=>out.push(['symbol '+s.name,s.image]));
    return out;
  }
  async function readyImages(images){
    await Promise.all(images.map(async([label,img])=>{
      if(!img)throw new Error('CardConjurer did not construct '+label+'.');
      S.requireImage(img);
      if(!img.src)throw new Error('Missing source for '+label+'.');
      if(img.complete&&img.naturalWidth>0)return;
      await timeout(new Promise((resolve,reject)=>{
        const cleanup=()=>{img.removeEventListener('load',onload);img.removeEventListener('error',onerror)};
        const onload=()=>{cleanup();resolve()};const onerror=()=>{cleanup();reject(new Error(label+' could not load: '+img.src.slice(0,200)))};
        img.addEventListener('load',onload,{once:true});img.addEventListener('error',onerror,{once:true});
        if(img.complete){if(img.naturalWidth>0)onload();else onerror();}
      }),45000,label);
    }));
  }
  async function preload(data){
    const paths=new Set([data.artSource,data.setSymbolSource,data.watermarkSource,'/img/black.png','/img/blank.png','/img/frames/cornerCutout.png']);
    for(const f of data.frames||[]){paths.add(f.src);for(const m of f.masks||[])paths.add(m.src);}
    const imgs=[...paths].filter(Boolean).map(path=>{const img=new Image();img.crossOrigin='anonymous';img.src=path;return [String(path).slice(0,130),img];});
    await readyImages(imgs);
  }
  async function fontsReady(data){
    const families=new Set(['belerenb','belerenbsc','mplantin','mplantini','gothammedium']);
    for(const obj of [...Object.values(data.text||{}),...Object.values(data.bottomInfo||{})]){
      if(obj.font)families.add(obj.font);
      for(const m of String(obj.text||'').matchAll(/\{font([^{}]+)\}/g))if(!/^(size|color)/.test(m[1]))families.add(m[1]);
    }
    await timeout(Promise.all([...families].map(async f=>{const list=await document.fonts.load('16px "'+String(f).replace(/["\\]/g,'')+'"');if(!list.length)throw new Error('No CardConjurer font definition for '+f+'.');})),30000,'CardConjurer fonts');
    await timeout(document.fonts.ready,30000,'Font decoding');
  }
  async function render(request){
    if(S.active)throw new Error('Another face is still rendering.');
    S.active=true;S.clearErrors();S.phase='assets';const data=structuredClone(request.data);const storageKey='__pf_'+request.key;
    try{
      post('progress',{key:request.key,message:'Checking art, frames, masks and fonts…'});
      await preload(data);await fontsReady(data);
      // Structural scripts run through native loadCard only after it assigns the new card.
      if(window.writingText)clearTimeout(window.writingText);
      let symbols=usedSymbols(data);for(const sym of symbols)S.requireImage(sym.image);
      await readyImages(symbols.map(s=>['symbol '+s.name,s.image]));
      S.phase='load';localStorage.setItem(storageKey,JSON.stringify(data));
      post('progress',{key:request.key,message:'CardConjurer is loading the saved face…'});
      await window.loadCard(storageKey);await scriptsSettled();
      symbols=usedSymbols(window.card);for(const sym of symbols)S.requireImage(sym.image);
      await readyImages(imagesFor(window.card,symbols));await fontsReady(window.card);
      // Stop the native 500ms debounce and perform its own final redraw, in order.
      S.phase='render';if(window.writingText)clearTimeout(window.writingText);
      await window.drawText();await window.bottomInfoEdited();await window.watermarkEdited();window.drawFrames();window.drawCard();
      await sleep(550);
      if(window.writingText)clearTimeout(window.writingText);
      await window.drawText();await window.bottomInfoEdited();window.drawFrames();window.drawCard();
      const errors=S.errors.filter(x=>x.phase!=='bootstrap');
      if(errors.length)throw new Error(errors[0].message);
      const canvas=window.cardCanvas;
      const width=Math.round(data.width*(1+2*(data.marginX||0))),height=Math.round(data.height*(1+2*(data.marginY||0)));
      if(!(canvas instanceof HTMLCanvasElement)||canvas.width!==width||canvas.height!==height)throw new Error('Native canvas dimensions do not match the saved template.');
      const blob=await timeout(new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('PNG export returned no image.')),'image/png')),20000,'PNG export');
      post('rendered',{key:request.key,blob,width,height,renderer:'CardConjurer native cardCanvas'});
    }finally{localStorage.removeItem(storageKey);S.active=false;S.phase='idle';}
  }
  let initialized=false;
  const ready=async()=>{
    await waitFor(()=>typeof window.loadCard==='function'&&window.cardCanvas&&window.availableFrames?.[window.selectedFrameIndex]&&window.card?.text,30000,'Native CardConjurer frame-picker bootstrap');
    await scriptsSettled();await sleep(600);
    if(document.querySelector('#enableCollectorInfo'))document.querySelector('#enableCollectorInfo').checked=true;
    if(document.querySelector('#show-guidelines'))document.querySelector('#show-guidelines').checked=false;
    S.clearErrors();initialized=true;post('ready');
  };
  window.addEventListener('message',e=>{
    if(e.source!==parent||e.origin!==(window.__PF_PARENT_ORIGIN||location.origin)||e.data?.source!=='pf-app')return;
    const msg=e.data;
    if(msg.type==='ping'){if(initialized)post('ready');return;}
    if(msg.type==='render'){
      if(!initialized){post('failed',{key:msg.key,error:'Native renderer is not initialized.'});return;}
      render(msg).catch(err=>post('failed',{key:msg.key,error:err.message,errors:S.errors}));
    }
  });
  ready().catch(e=>post('failed',{error:e.message,errors:S.errors}));
})();
