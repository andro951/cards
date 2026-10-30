import {$,api,attempt,modal,closeModal,setModalBusy,job,asset,thumbnail,bytes,toast} from '/site/ui.js';

function node(tag,text='',className=''){
  const item=document.createElement(tag);
  item.textContent=text;
  item.className=className;
  return item;
}
function action(label,callback,className='button'){
  const button=node('button',label,className);
  button.type='button';
  button.onclick=()=>attempt(callback);
  return button;
}
function imageButton(id,label,callback,eager=false){
  const button=node('button','','card-image');button.type='button';button.title='Enlarge '+label;
  const image=node('img');image.alt=label;image.loading=eager?'eager':'lazy';image.decoding='async';
  const status=node('span','Loading image…');
  Object.assign(status.style,{position:'absolute',inset:'0',display:'grid',placeItems:'center',padding:'8px',fontSize:'12px'});
  let original=false,failed=false;
  const load=(full=false,retry=false)=>{
    original=full;failed=false;image.style.visibility='hidden';status.hidden=false;status.style.display='grid';
    status.textContent='Loading image…';button.title='Enlarge '+label;button.setAttribute('aria-busy','true');
    const url=full?asset(id):thumbnail(asset(id));
    image.src=url+(retry?'?retry='+Date.now():'');
  };
  image.onload=()=>{image.style.visibility='visible';status.hidden=true;status.style.display='none';button.setAttribute('aria-busy','false');};
  image.onerror=()=>{
    //A failed cached thumbnail must not hide a valid printable image.
    if(!original){load(true);return;}
    failed=true;button.setAttribute('aria-busy','false');button.title='Retry '+label;
    image.style.visibility='hidden';status.hidden=false;status.style.display='grid';
    status.textContent='Image unavailable. Click to retry.';
  };
  button.append(image,status);load();
  button.onclick=()=>{if(failed)load(false,true);else callback();};return button;
}
function maximize(host){
  host.style.cssText='width:calc(100vw - 20px);height:calc(100dvh - 20px);max-height:none';
  const overlay=host.closest('.modal-backdrop');overlay.style.padding='10px';
}
function lightbox(id,label){
  const overlay=node('dialog','','');
  overlay.setAttribute('aria-label',label);
  overlay.style.cssText='position:fixed;inset:0;z-index:100;background:#0b0c0ef5;display:flex;align-items:center;justify-content:center;padding:12px;margin:auto;width:100vw;height:100dvh;max-width:none;max-height:none;border:0';
  const image=node('img');image.src=asset(id);image.alt=label;
  image.style.cssText='max-width:100%;max-height:100%;object-fit:contain';
  const close=action('×',()=>overlay.close(),'button quiet icon');
  close.setAttribute('aria-label','Close image');
  close.style.cssText='position:absolute;right:22px;top:18px;font-size:28px;z-index:1';
  overlay.append(image,close);overlay.addEventListener('close',()=>overlay.remove());document.body.append(overlay);overlay.showModal();
}

export function showReview(initial,ids,saved,orderReady,openOrder){
  let plan=initial,query='';
  const host=modal(saved?'Saved order preview':'Review & Print','',{size:'large'});
  maximize(host);
  const body=$('.modal-body',host);
  const footer=node('footer','','modal-footer');host.append(footer);
  const unique=new Map();
  function cards(){
    unique.clear();
    for(const card of plan.cards){
      const key=[card.deckId,card.cardId,card.frontAsset,card.backAsset].join(':');
      if(!unique.has(key))unique.set(key,{...card,quantity:0});
      unique.get(key).quantity++;
    }
    return [...unique.values()];
  }
  async function accept(issue){
    const deck=await api('/api/decks/'+issue.deckId);
    await api('/api/decks/'+issue.deckId+'/cards/'+issue.cardId,{
      revision:deck.revision,faceId:issue.faceId,renderKey:issue.renderKey,acceptWarning:true
    });
    plan=await api('/api/orders/plan',{deckIds:ids});
    draw();
  }
  function focus(issue){
    const cover=node('dialog');cover.setAttribute('aria-label',issue.name);
    cover.style.cssText='position:fixed;inset:0;z-index:100;background:#101217;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:16px';
    cover.append(node('h2',issue.name));
    const image=node('img');image.src=asset(issue.frontAsset);image.alt=issue.name+' rendered card';
    image.style.cssText='max-width:min(85vw,650px);max-height:75vh;object-fit:contain';cover.append(image);
    cover.append(node('p',issue.warning,'notice'));
    const controls=node('div','','actions');
    let accepting=false;
    const close=action('×',()=>cover.close(),'button quiet icon');close.setAttribute('aria-label','Close review card');
    const approve=action('It Looks Fine',async()=>{
      accepting=true;close.disabled=true;approve.disabled=true;
      try{await accept(issue);cover.close();}
      finally{accepting=false;close.disabled=false;approve.disabled=false;}
    },'button primary');
    controls.append(close,approve);
    cover.addEventListener('cancel',event=>{if(accepting)event.preventDefault();});
    cover.addEventListener('close',()=>cover.remove());
    cover.append(controls);document.body.append(cover);cover.showModal();
  }
  function warningSection(){
    if(!plan.issues?.length)return null;
    const section=node('section','','panel');section.style.borderColor='var(--accent)';
    section.append(node('h2',`Needs Review · ${plan.issues.length}`));
    section.append(node('p','Open each card to inspect its current render. The print package is available after every warning is resolved.','muted'));
    const grid=node('div','','pair-grid');grid.style.marginTop='16px';
    for(const issue of plan.issues){
      const tile=node('article','','well');
      tile.append(imageButton(issue.frontAsset,issue.name,()=>focus(issue)));
      tile.append(node('b',issue.name));
      tile.append(node('p',issue.warning,'muted'));
      tile.append(action('Review card',()=>focus(issue),'button small'));
      grid.append(tile);
    }
    section.append(grid);return section;
  }
  function draw(){
    body.replaceChildren();footer.replaceChildren();
    const metrics=node('div','','order-metrics');
    for(const [value,label] of [[plan.count,'physical cards'],[plan.decks.length,'decks'],[bytes(plan.zipBytes||plan.bytes),'estimated ZIP']]){
      const metric=node('div','','metric');metric.append(node('b',String(value)),node('span',label));metrics.append(metric);
    }
    body.append(metrics);
    const warnings=warningSection();if(warnings)body.append(warnings);
    const defaultBacks=new Map();
    for(const deck of plan.decks)if(deck.backAsset){
      const names=defaultBacks.get(deck.backAsset)||[];names.push(deck.name);defaultBacks.set(deck.backAsset,names);
    }
    for(const [back,names] of defaultBacks){
      const backSection=node('section','','well section-gap');
      backSection.style.cssText='display:flex;align-items:center;gap:18px';
      const label=names.length===plan.decks.length?'Common back':'Default back · '+names.join(', ');
      const backPreview=imageButton(back,label,()=>lightbox(back,label),true);
      backPreview.style.cssText='width:100px;flex:none';
      backSection.append(backPreview,node('div',label,'muted'));
      body.append(backSection);
    }
    const header=node('div','','toolbar section-gap');
    header.append(node('h2','Front & Back'));
    const search=node('input');search.type='search';search.placeholder='Find a card';search.value=query;
    search.oninput=()=>{query=search.value;filterGrid();};header.append(search);body.append(header);
    const grid=node('div','','pair-grid');grid.id='browser-pair-grid';body.append(grid);
    function drawGrid(){
      grid.replaceChildren();
      for(const card of cards()){
        const tile=node('article','','well');
        tile.dataset.search=(card.name+' '+card.deckName).toLowerCase();
        const pair=node('div','','pair-images');
        pair.append(imageButton(card.frontAsset,card.name+' front',()=>lightbox(card.frontAsset,card.name+' front')));
        if(!defaultBacks.has(card.backAsset)){
          const reverse=node('div');reverse.append(node('small','Unique back'));
          reverse.append(imageButton(card.backAsset,card.name+' back',()=>lightbox(card.backAsset,card.name+' back'),true));
          pair.append(reverse);
        }
        tile.append(pair,node('b',`${card.quantity}× ${card.name}`),node('small',card.deckName));grid.append(tile);
      }
    }
    function filterGrid(){
      const text=query.toLowerCase();
      for(const tile of grid.children)tile.hidden=!tile.dataset.search.includes(text);
    }
    drawGrid();filterGrid();
    if(saved){
      const download=node('a','Save ZIP folder','button');download.href='/api/orders/'+plan.id+'/download';download.download='';footer.append(download);
      footer.append(action('Open in TCGPlaytest',()=>openOrder(plan.id),'button primary'));
    }else{
      const progress=node('div');progress.id='order-build-progress';progress.hidden=true;
      Object.assign(progress.style,{flex:'1 1 220px',minWidth:'0',gap:'6px',display:'none'});
      const progressText=node('span','Starting paired ZIP…');progressText.setAttribute('role','status');progressText.setAttribute('aria-live','polite');
      const bar=node('progress');bar.max=100;bar.setAttribute('aria-label','Paired ZIP build progress');
      Object.assign(bar.style,{width:'100%',height:'18px',accentColor:'#ed861e'});
      const saveText=node('span','2 · Save ZIP · Waiting for packaging');saveText.setAttribute('role','status');saveText.setAttribute('aria-live','polite');
      const saveBar=node('progress');saveBar.max=100;saveBar.value=0;saveBar.setAttribute('aria-label','Paired ZIP saving progress');
      Object.assign(saveBar.style,{width:'100%',height:'18px',accentColor:'#ed861e'});
      const detail=node('small');progress.append(progressText,bar,saveText,saveBar,detail);
      const duration=seconds=>{const value=Math.max(0,Math.ceil(seconds));return value<60?`${value}s`:`${Math.floor(value/60)}m ${value%60}s`;};
      const cancel=action('Cancel build',()=>{});cancel.hidden=true;cancel.style.display='none';
      const build=action('Build ZIP folder',async()=>{
        if(plan.issues?.length)throw new Error('Review each warning before building the ZIP.');
        build.disabled=true;setModalBusy(host,true);
        const controller=new AbortController();
        progress.hidden=false;progress.style.display='grid';progressText.textContent='1 · Packaging cards…';detail.textContent='';bar.removeAttribute('value');
        saveText.textContent='2 · Save ZIP · Waiting for packaging';saveBar.value=0;
        cancel.hidden=false;cancel.style.display='';cancel.disabled=false;
        cancel.onclick=()=>{controller.abort();cancel.disabled=true;progressText.textContent='Stopping ZIP build…';};
        let latest=null,received=0;
        const drawProgress=()=>{
          const job=latest;if(!job)return;
          if(controller.signal.aborted)return;
          const total=Number(job.total)||0,done=Number(job.done)||0;
          const saving=job.phase==='saving'||total&&done===total&&/sav|finaliz/i.test(job.message||'');
          const percent=total?Math.min(100,Math.floor(done/total*100)):0;
          if(total)bar.value=percent;
          progressText.textContent=total?`1 · ${percent}% · ${done} / ${total} cards packaged`:'1 · Packaging cards…';
          if(!saving){detail.textContent=job.message||'';return;}
          const saved=Number(job.savedBytes)||0,size=Number(job.totalBytes)||0;
          const finalized=job.saveStage==='complete'||job.state==='done';
          const savedPercent=size?Math.min(finalized?100:99,Math.floor(saved/size*100)):0;
          if(size)saveBar.value=savedPercent;else saveBar.removeAttribute('value');
          saveText.textContent=`2 · Saving ZIP${size?` · ${savedPercent}% · ${bytes(saved)} / ${bytes(size)}`:''}`;
          const elapsed=(Number(job.saveElapsedSeconds)||0)+(performance.now()-received)/1000;
          if(job.saveStage==='finalizing'||finalized){detail.textContent=`${finalized?'File saved · recording print order':'Finalizing file'} · ${duration(elapsed)} elapsed`;return;}
          const rate=Number(job.saveBytesPerSecond)||0,eta=job.saveEtaSeconds;
          detail.textContent=`${rate?`${bytes(rate)}/s · `:''}${Number.isFinite(eta)?`about ${duration(eta)} remaining`:'Calculating time remaining…'} · ${duration(elapsed)} elapsed`;
        };
        const update=job=>{latest=job;received=performance.now();drawProgress();};
        const ticker=setInterval(drawProgress,1000);
        try{
          const out=await job('/api/orders/build',{deckIds:[...ids]},{label:'Build paired order',signal:controller.signal,onProgress:update});
          bar.value=100;saveBar.value=100;progressText.textContent='100% · ZIP ready';
          setModalBusy(host,false);closeModal();orderReady(out);
        }catch(error){
          progressText.textContent=controller.signal.aborted?'ZIP build cancelled.': 'ZIP build failed.';
          saveText.textContent=controller.signal.aborted?'2 · Saving cancelled.':'2 · Save incomplete.';
          detail.textContent=error.message;throw error;
        }finally{clearInterval(ticker);setModalBusy(host,false);build.disabled=Boolean(plan.issues?.length);cancel.hidden=true;cancel.style.display='none';}
      },'button primary');
      build.disabled=Boolean(plan.issues?.length);footer.append(progress,cancel,build);
    }
  }
  draw();
}
