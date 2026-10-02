import {$,$$,esc,state,api,attempt,toast,modal,closeModal,errorBox,confirmAction,job,bytes,date,badge,empty,loading,thumbnail,nav} from './ui.js';
import {renderDecks} from './render.js';
export function setupHelper(){
  const host=modal('Connect the browser helper','');
  const body=$('.modal-body',host);
  const add=(parent,tag,value,className='')=>{
    const element=document.createElement(tag);element.textContent=value;
    if(className)element.className=className;
    parent.append(element);return element;
  };
  add(body,'p','Set up automatic deck-site imports and print handoff once.','muted');
  const download=add(body,'div','','well');
  add(download,'h3','1 · Download and extract');
  const link=add(download,'a','Download browser helper','button primary');link.href='/api/helper/download';link.download='';
  const install=add(body,'div','','well section-gap');
  add(install,'h3','2 · Load in Edge or Chrome');
  add(install,'p','Open edge://extensions or chrome://extensions, enable Developer mode, choose Load unpacked, and select the extracted extension folder.');
  const reload=add(body,'div','','well section-gap');
  add(reload,'h3','3 · Reload Bulk Proxy Forge');
  add(reload,'p','Archidekt and MTGGoldfish links can then import on your computer, and Print Cards can open your order in TCGPlaytest.');
  add(body,'div','The helper never checks out or enters payment details. You review the printer preview and complete checkout yourself.','notice info');
  const footer=add(host,'footer','','modal-footer');
  const recheck=add(footer,'button','Check connection','button');recheck.id='recheck-helper';recheck.type='button';
  const done=add(footer,'button','Done','button primary');done.id='close-helper';done.type='button';
  $('#close-helper').onclick=closeModal;
  $('#recheck-helper').onclick=()=>{window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_PING'},location.origin);setTimeout(()=>toast(state.helper?'Print helper is connected.':'Not connected yet. Load the extension, then reload this page.',!state.helper),700);};
}
export async function showOrders(deckId=null){
  const epoch=state.routeEpoch;
  const all=await api('/api/orders');
  if(epoch!==state.routeEpoch)return;
  const orders=deckId?all.filter(order=>order.decks.some(deck=>deck.id===deckId)):all;
  $('#main').innerHTML=`<div class="page-head"><div><span class="eyebrow">BUILT FOR THE TABLETOP</span><h1>Print orders</h1><p>Combine any number of decks. Each physical card gets an explicit front/back pair.</p></div><button class="button primary" id="new-order">＋ Create print order</button></div><section class="hero-strip"><div><h2>One order. Every back in the right place.</h2><p>Order packages are saved snapshots. Editing a deck later won’t change a ZIP you already built. The printer opens in a new tab when you’re ready.</p></div><div class="order-icon" aria-hidden="true">▱</div></section>${orders.length?`<section class="panel order-list">${orders.map(o=>`<div class="order-row"><div class="order-title"><h3>${o.count} cards · ${o.decks.length} deck${o.decks.length===1?'':'s'}</h3><p>${o.decks.map(d=>esc(d.name)).join(' · ')}</p><small>${date(o.createdAt)} · ${bytes(o.zipBytes)} · paired filenames</small></div><div class="actions"><a class="button small" href="${esc(o.download)}" download>Download ZIP</a><button class="button primary small" data-open-order="${o.id}">Open in TCGPlaytest ↗</button><button class="button quiet small" data-review-order="${o.id}">Review</button></div></div>`).join('')}</section>`:empty('Your first print order is a few clicks away','Generate your deck images, select the decks you want, and check the paired preview before you package them.',`<button class="button primary" id="empty-order">Choose decks</button>`)}`;
  if(state.bootstrap?.browser){
    $('.page-head .eyebrow')?.remove();$('.page-head p')?.remove();$('.hero-strip')?.remove();
    for(const button of $$('[data-open-order]'))button.textContent='Print Cards';
  }
  const heading=$('.page-head');
  const actions=document.createElement('div');actions.className='actions';
  const library=document.createElement('a');library.href='#decks';library.className='button quiet';library.textContent='Deck Library';
  actions.append(library,$('#new-order'));heading.append(actions);
  if(deckId){
    const filter=document.createElement('div');filter.className='notice info';
    const name=all.flatMap(order=>order.decks).find(deck=>deck.id===deckId)?.name||'this deck';
    const text=document.createElement('span');text.textContent='Print orders using '+name+' · ';
    const clear=document.createElement('a');clear.href='#orders';clear.className='button quiet small';clear.textContent='Show all print orders';filter.append(text,clear);heading.after(filter);
    if(!orders.length){$('.empty-state')?.remove();const message=document.createElement('p');message.textContent='No print orders use this deck.';filter.after(message);}
  }
  if(state.bootstrap?.browser){
    for(const row of $$('.order-row')){
      const id=$('[data-review-order]',row).dataset.reviewOrder;
      const button=document.createElement('button');button.className='button quiet small';button.textContent='Delete print order';button.dataset.deleteOrder=id;
      button.onclick=()=>attempt(async()=>{
        if(!await confirmAction('Delete print order?','Its saved ZIP and preview will be removed. Decks will be kept.','Delete print order',true))return;
        button.disabled=true;button.textContent='Deleting…';
        try{await api('/api/orders/'+id+'/delete',{});row.remove();toast('Print order deleted.');await showOrders(deckId);}
        catch(error){button.disabled=false;button.textContent='Delete print order';throw error;}
      });$('.actions',row).append(button);
    }
  }
  for(const id of ['new-order','empty-order'])if($('#'+id))$('#'+id).onclick=()=>attempt(()=>chooseOrder());
  $$('[data-open-order]').forEach(b=>b.onclick=()=>attempt(()=>openOrder(b.dataset.openOrder)));
  $$('[data-review-order]').forEach(b=>b.onclick=()=>attempt(async()=>{const o=await api('/api/orders/'+b.dataset.reviewOrder);reviewPlan(o,o.decks.map(d=>d.id),true);}));
}
export async function chooseOrder(preselected=[]){
  if(state.dirty)throw new Error('Save your current deck setup before building an order.');
  const decks=await api('/api/decks');const selected=new Set(preselected.filter(id=>decks.some(d=>d.id===id)));
  const host=modal('Choose decks for this order',`<p class="muted">Select one deck or combine several. Quantities are preserved; double-faced cards use their actual reverse.</p>${decks.length?`<div class="order-decks">${decks.map(d=>`<label class="order-deck-row"><input type="checkbox" data-order-deck="${d.id}" ${selected.has(d.id)?'checked':''}><div class="order-deck-info"><b>${esc(d.name)}</b><small>${d.summary.cards} cards · ${d.summary.rendered}/${d.summary.faces} faces rendered</small></div>${badge(d.status)}</label>`).join('')}</div>`:empty('No decks yet','Import a deck and generate its images before creating a print order.')}<div id="order-selection-message" class="notice info"></div>`,{size:'large',footer:`<span class="footer-hint" id="order-count"></span>${state.bootstrap?.browser?'':'<button class="button" id="order-generate">Generate selected images</button>'}<button class="button primary" id="order-plan">Review</button>`});
  function update(){
    const chosen=decks.filter(d=>selected.has(d.id)),count=chosen.reduce((n,d)=>n+d.summary.cards,0),needs=chosen.filter(d=>d.status!=='ready');
    $('#order-count').textContent=`${chosen.length} decks · ${count} physical cards`;$('#order-plan').disabled=!chosen.length||!!needs.length;if($('#order-generate'))$('#order-generate').disabled=!chosen.length;
    $('#order-selection-message').textContent=needs.length?`${needs.length} selected deck${needs.length===1?' needs':'s need'} images. Open the deck and generate images first.`:chosen.length?'Review both sides and resolve any crop warnings before printing.':'Choose the decks you’d like to print.';
  }
  $$('[data-order-deck]',host).forEach(el=>el.onchange=()=>{el.checked?selected.add(el.dataset.orderDeck):selected.delete(el.dataset.orderDeck);update();});update();
  if($('#order-generate'))$('#order-generate').onclick=()=>attempt(async()=>{const ids=[...selected];closeModal();await renderDecks(ids);await chooseOrder(ids);});
  $('#order-plan').onclick=async()=>{try{$('#order-plan').disabled=true;const ids=[...selected];const plan=await api('/api/orders/plan',{deckIds:ids});closeModal();reviewPlan(plan,ids);}catch(e){errorBox($('.modal-body',host),e.message);update();}};
}
function reviewPlan(plan,ids,saved=false){
  if(state.bootstrap?.browser){
    import('/web/review-browser.js').then(module=>module.showReview(plan,ids,saved,orderReady,openOrder)).catch(error=>toast(error.message,true));
    return;
  }
  // Collapse repeated quantities for preview only. The ZIP still contains every copy.
  const unique=new Map();for(const c of plan.cards){const key=[c.deckId,c.cardId,c.frontAsset,c.backAsset].join(':');if(!unique.has(key))unique.set(key,{...c,quantity:0});unique.get(key).quantity++;}
  const cards=[...unique.values()];let query='',page=0;const pageSize=36;
  const host=modal(saved?'Saved order preview':'Review your paired order',`<div class="order-metrics"><div class="metric"><b>${plan.count}</b><span>physical cards</span></div><div class="metric"><b>${plan.decks.length}</b><span>selected decks</span></div><div class="metric"><b>${bytes(plan.zipBytes||plan.bytes)}</b><span>estimated package</span></div></div><div class="notice success">Front and back filenames are paired explicitly. TCGPlaytest does not need to infer an image order.</div>${plan.warnings?.length?`<details class="notice" open><summary>${plan.warnings.length} artwork or layout warnings</summary><ul>${plan.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></details>${!saved?'<label class="check-line"><input type="checkbox" id="ack-order-warnings"><span>I reviewed these warnings and accept the current crop/layout.<small>No artwork is automatically altered to hide a warning.</small></span></label>':''}`:''}<div class="toolbar"><label class="search"><input id="order-search" type="search" placeholder="Find a card in this order…" aria-label="Find a card in order"></label><span class="subtitle-line">Front ↔ Back · one tile per unique pair</span></div><div id="pair-grid"></div><div class="actions section-gap" id="pair-pages"></div>`,{size:'large',footer:saved?`<a class="button" href="/api/orders/${plan.id}/download" download>Download saved ZIP</a><button class="button primary" id="open-saved-order">Open in TCGPlaytest ↗</button>`:'<span class="footer-hint">Nothing is purchased automatically.</span><button class="button primary" id="build-order">Build paired ZIP</button>'});
  function grid(){
    const filtered=cards.filter(c=>(c.name+' '+c.deckName).toLowerCase().includes(query.toLowerCase()));const max=Math.max(0,Math.ceil(filtered.length/pageSize)-1);page=Math.min(page,max);
    $('#pair-grid').innerHTML=`<div class="pair-grid">${filtered.slice(page*pageSize,(page+1)*pageSize).map(c=>`<article class="well"><div class="pair-images"><a href="/api/assets/${esc(c.frontAsset)}" target="_blank" rel="noopener"><img loading="lazy" decoding="async" src="${esc(thumbnail('/api/assets/'+c.frontAsset))}" alt="${esc(c.name)} front"></a><a href="/api/assets/${esc(c.backAsset)}" target="_blank" rel="noopener"><img loading="lazy" decoding="async" src="${esc(thumbnail('/api/assets/'+c.backAsset))}" alt="${esc(c.name)} back"></a></div><div class="pair-title">${c.quantity}× ${esc(c.name)}</div><div class="pair-subtitle">${esc(c.deckName)}</div></article>`).join('')}</div>`;
    $('#pair-pages').innerHTML=`<button class="button small" id="pairs-prev" ${page===0?'disabled':''}>Previous</button><span class="subtitle-line">Page ${page+1} / ${max+1} · ${filtered.length} unique pairs</span><button class="button small" id="pairs-next" ${page>=max?'disabled':''}>Next</button>`;
    $('#pairs-prev').onclick=()=>{page--;grid();};$('#pairs-next').onclick=()=>{page++;grid();};
  }
  grid();$('#order-search').oninput=e=>{query=e.target.value;page=0;grid();};
  if(saved){$('#open-saved-order').onclick=()=>attempt(()=>openOrder(plan.id));return;}
  function enableBuild(){$('#build-order').disabled=!!plan.warnings?.length&&!$('#ack-order-warnings')?.checked;}
  if($('#ack-order-warnings'))$('#ack-order-warnings').onchange=enableBuild;enableBuild();
  $('#build-order').onclick=async()=>{
    try{
      const acknowledge=!!$('#ack-order-warnings')?.checked;
      if(plan.warnings?.length&&!acknowledge)throw new Error('Review and acknowledge the warnings first.');
      const payload={deckIds:[...ids],acknowledge};
      $('#build-order').disabled=true;closeModal();
      const out=await job('/api/orders/build',payload,{label:'Build paired order'});
      orderReady(out);
    }catch(e){toast(e.message,true);}
  };
}
function orderReady(order){
  if(state.bootstrap?.browser){
    const host=modal('Your print package is ready',`<div class="empty-state"><span class="success-check">✓</span><h2>${order.count} cards ready to print</h2><p>${order.decks.map(d=>esc(d.name)).join(' · ')}</p><button class="button primary" id="print-cards">Print Cards <small style="display:block;font-weight:500">Open in TCGPlaytest</small></button></div>`,{footer:'<button class="button quiet" id="save-order-later">Save for Later</button>'});
    $('#print-cards',host).onclick=()=>attempt(()=>state.helper?openOrder(order.id):choosePrintPath(order));
    $('#save-order-later',host).onclick=()=>{closeModal();nav('orders');toast('Your print package is saved in this browser.');};
    return;
  }
  const host=modal('Your print package is ready',`<div class="empty-state"><span class="success-check">✓</span><h2>${order.count} cards, correctly paired.</h2><p>${order.decks.map(d=>esc(d.name)).join(' · ')}</p><div class="actions"><a class="button" id="download-order" href="${esc(order.download)}" download>Save images ZIP · ${bytes(order.zipBytes)}</a><button class="button primary" id="send-order">Open in TCGPlaytest ↗</button></div></div><div class="notice info">Proxy Foundry stays open. In the printer tab, choose Add or Replace if cards are already present, then review the print preview before checkout.</div>${order.zipBytes>1024**3?'<div class="notice">The helper will send this order as multiple ZIP batches, each at most 1 GB, into the same TCGPlaytest design. Original image quality is unchanged.</div>':''}`,{footer:'<button class="button quiet" id="view-orders">View saved orders</button>'});
  $('#send-order').onclick=()=>attempt(()=>openOrder(order.id));
  $('#view-orders').onclick=()=>{closeModal();nav('orders');};
}
function choosePrintPath(order){
  const host=modal('Print Cards',`<div class="well"><h3>Print once · no setup</h3><p>Download your card ZIP, then upload it on TCGPlaytest.</p><a class="button primary" id="manual-zip" href="${esc(order.download)}" download>1 · Download card ZIP</a><button class="button" id="manual-printer">2 · Open TCGPlaytest ↗</button><p class="muted">On the printer page, choose <b>Upload Deck ZIP</b> and select the ZIP you downloaded.</p><img src="/site/tcg-upload-guide.png" alt="TCGPlaytest design page showing the Upload Deck ZIP control" style="width:min(100%,330px);border-radius:9px;border:1px solid #59677a"></div><div class="well section-gap"><h3>Printing again later?</h3><p>Install the optional helper once to send future orders automatically.</p><button class="button" id="install-print-helper">Set up one-click printing</button></div>`,{size:'large'});
  $('#manual-printer',host).onclick=()=>window.open('https://www.tcgplaytest.com/?view=design','_blank','noopener');
  $('#install-print-helper',host).onclick=setupHelper;
}
async function openOrder(id){
  if(!state.helper){
    const order=await api('/api/orders/'+id);
    if(state.bootstrap?.browser){choosePrintPath(order);return;}
    setupHelper();return;
  }
  const order=await api('/api/orders/'+id);
  if(order.zipBytes>1024**3&&!state.helperCapabilities?.includes('paired-zip-batches'))throw new Error('Large orders need Print Helper 1.1.0. Reload the updated extension in edge://extensions or chrome://extensions, then reload this page. No uninstall is needed.');
  const transfer=await api('/api/orders/'+id+'/transfer',{});
  if(state.bootstrap?.browser)transfer.browser=true;
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{window.removeEventListener('message',listener);reject(new Error('The helper did not respond. Reconnect the helper and reopen the saved order.'));},40000);
    function listener(e){if(e.source!==window||e.origin!==location.origin||e.data?.source!=='proxy-foundry-helper')return;if(!['PF_WORKSPACE_OPENED','PF_WORKSPACE_ERROR'].includes(e.data.type))return;clearTimeout(timer);window.removeEventListener('message',listener);e.data.type==='PF_WORKSPACE_OPENED'?resolve():reject(new Error(e.data.error));}
    window.addEventListener('message',listener);window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_OPEN',transfer},location.origin);
  });
  toast('TCGPlaytest opened in a new tab. Keep this page open until the upload finishes.');
}
