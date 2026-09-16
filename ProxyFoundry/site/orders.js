import {$,$$,esc,state,api,attempt,toast,modal,closeModal,errorBox,confirmAction,job,bytes,date,badge,empty,loading,nav} from './ui.js';
import {renderDecks} from './render.js';
export function setupHelper(){
  const host=modal('Connect the print helper',`<span class="eyebrow">ONE-TIME BROWSER SETUP</span><p class="muted">The app handles importing, templates, rendering and ZIP downloads by itself. The small helper is only needed to fill TCGPlaytest’s editor automatically.</p><div class="well"><h3>1 · Download and extract the helper</h3><p>Keep the extracted <code>extension</code> folder somewhere permanent.</p><a class="button primary" href="/api/helper/download" download>Download print helper</a></div><div class="well section-gap"><h3>2 · Load the extension in Edge or Chrome</h3><p>Open <code>edge://extensions</code> or <code>chrome://extensions</code>, enable <b>Developer mode</b>, click <b>Load unpacked</b>, and select the extracted <code>extension</code> folder.</p><p>Remove the old test helper first. This version does not need “Allow access to file URLs.”</p></div><div class="well section-gap"><h3>3 · Reload this page</h3><p>The top-right status will say <b>connected</b>. Build an order and choose <b>Open in TCGPlaytest</b>. Proxy Foundry stays open.</p></div><div class="notice info">The helper never places an order, enters payment details or checks out. You review the printer’s preview and complete checkout yourself. Downloading the paired ZIP is always available without the helper.</div>`,{footer:'<button class="button" id="recheck-helper">Check connection</button><button class="button primary" id="close-helper">Done</button>'});
  $('#close-helper').onclick=closeModal;
  $('#recheck-helper').onclick=()=>{window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_PING'},location.origin);setTimeout(()=>toast(state.helper?'Print helper is connected.':'Not connected yet. Load the extension, then reload this page.',!state.helper),700);};
}
export async function showOrders(){
  const orders=await api('/api/orders');
  $('#main').innerHTML=`<div class="page-head"><div><span class="eyebrow">BUILT FOR THE TABLETOP</span><h1>Print orders</h1><p>Combine any number of decks. Each physical card gets an explicit front/back pair.</p></div><button class="button primary" id="new-order">＋ Create print order</button></div><section class="hero-strip"><div><h2>One order. Every back in the right place.</h2><p>Order packages are saved snapshots. Editing a deck later won’t change a ZIP you already built. The printer opens in a new tab when you’re ready.</p></div><div class="order-icon" aria-hidden="true">▱</div></section>${orders.length?`<section class="panel order-list">${orders.map(o=>`<div class="order-row"><div class="order-title"><h3>${o.count} cards · ${o.decks.length} deck${o.decks.length===1?'':'s'}</h3><p>${o.decks.map(d=>esc(d.name)).join(' · ')}</p><small>${date(o.createdAt)} · ${bytes(o.zipBytes)} · paired filenames</small></div><div class="actions"><a class="button small" href="${esc(o.download)}" download>Download ZIP</a><button class="button primary small" data-open-order="${o.id}">Open in TCGPlaytest ↗</button><button class="button quiet small" data-review-order="${o.id}">Review</button></div></div>`).join('')}</section>`:empty('Your first print order is a few clicks away','Generate your deck images, select the decks you want, and check the paired preview before you package them.',`<button class="button primary" id="empty-order">Choose decks</button>`)}`;
  for(const id of ['new-order','empty-order'])if($('#'+id))$('#'+id).onclick=()=>attempt(()=>chooseOrder());
  $$('[data-open-order]').forEach(b=>b.onclick=()=>attempt(()=>openOrder(b.dataset.openOrder)));
  $$('[data-review-order]').forEach(b=>b.onclick=()=>attempt(async()=>{const o=await api('/api/orders/'+b.dataset.reviewOrder);reviewPlan(o,o.decks.map(d=>d.id),true);}));
}
export async function chooseOrder(preselected=[]){
  if(state.dirty)throw new Error('Save your current deck setup before building an order.');
  const decks=await api('/api/decks');const selected=new Set(preselected.filter(id=>decks.some(d=>d.id===id)));
  const host=modal('Choose decks for this order',`<p class="muted">Select one deck or combine several. Quantities are preserved; double-faced cards use their actual reverse.</p>${decks.length?`<div class="order-decks">${decks.map(d=>`<label class="order-deck-row"><input type="checkbox" data-order-deck="${d.id}" ${selected.has(d.id)?'checked':''}><div class="order-deck-info"><b>${esc(d.name)}</b><small>${d.summary.cards} cards · ${d.summary.rendered}/${d.summary.faces} faces rendered</small></div>${badge(d.status)}</label>`).join('')}</div>`:empty('No decks yet','Import a deck and generate its images before creating a print order.')}<div id="order-selection-message" class="notice info"></div>`,{size:'large',footer:'<span class="footer-hint" id="order-count"></span><button class="button" id="order-generate">Generate selected images</button><button class="button primary" id="order-plan">Review paired order →</button>'});
  function update(){
    const chosen=decks.filter(d=>selected.has(d.id)),count=chosen.reduce((n,d)=>n+d.summary.cards,0),needs=chosen.filter(d=>d.status!=='ready');
    $('#order-count').textContent=`${chosen.length} decks · ${count} physical cards`;$('#order-plan').disabled=!chosen.length||!!needs.length;$('#order-generate').disabled=!chosen.length||state.busy;
    $('#order-selection-message').textContent=needs.length?`${needs.length} selected deck${needs.length===1?' needs':'s need'} generation or review. Generate images first, then fix any per-card errors.`:chosen.length?'All selected images are rendered. Next, review both sides and any crop warnings.':'Choose the decks you’d like to print.';
  }
  $$('[data-order-deck]',host).forEach(el=>el.onchange=()=>{el.checked?selected.add(el.dataset.orderDeck):selected.delete(el.dataset.orderDeck);update();});update();
  $('#order-generate').onclick=()=>attempt(async()=>{const ids=[...selected];closeModal();await renderDecks(ids);await chooseOrder(ids);});
  $('#order-plan').onclick=async()=>{try{$('#order-plan').disabled=true;const ids=[...selected];const plan=await api('/api/orders/plan',{deckIds:ids});closeModal();reviewPlan(plan,ids);}catch(e){errorBox($('.modal-body',host),e.message);update();}};
}
function reviewPlan(plan,ids,saved=false){
  // Collapse repeated quantities for preview only. The ZIP still contains every copy.
  const unique=new Map();for(const c of plan.cards){const key=[c.deckId,c.cardId,c.frontAsset,c.backAsset].join(':');if(!unique.has(key))unique.set(key,{...c,quantity:0});unique.get(key).quantity++;}
  const cards=[...unique.values()];let query='',page=0;const pageSize=36;
  const host=modal(saved?'Saved order preview':'Review your paired order',`<div class="order-metrics"><div class="metric"><b>${plan.count}</b><span>physical cards</span></div><div class="metric"><b>${plan.decks.length}</b><span>selected decks</span></div><div class="metric"><b>${bytes(plan.zipBytes||plan.bytes)}</b><span>estimated package</span></div></div><div class="notice success">Front and back filenames are paired explicitly. TCGPlaytest does not need to infer an image order.</div>${plan.warnings?.length?`<details class="notice" open><summary>${plan.warnings.length} artwork or layout warnings</summary><ul>${plan.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></details>${!saved?'<label class="check-line"><input type="checkbox" id="ack-order-warnings"><span>I reviewed these warnings and accept the current crop/layout.<small>No artwork is automatically altered to hide a warning.</small></span></label>':''}`:''}<div class="toolbar"><label class="search"><input id="order-search" type="search" placeholder="Find a card in this order…" aria-label="Find a card in order"></label><span class="subtitle-line">Front ↔ Back · one tile per unique pair</span></div><div id="pair-grid"></div><div class="actions section-gap" id="pair-pages"></div>`,{size:'large',footer:saved?`<a class="button" href="/api/orders/${plan.id}/download" download>Download saved ZIP</a><button class="button primary" id="open-saved-order">Open in TCGPlaytest ↗</button>`:'<span class="footer-hint">Nothing is purchased automatically.</span><button class="button primary" id="build-order">Build paired ZIP</button>'});
  function grid(){
    const filtered=cards.filter(c=>(c.name+' '+c.deckName).toLowerCase().includes(query.toLowerCase()));const max=Math.max(0,Math.ceil(filtered.length/pageSize)-1);page=Math.min(page,max);
    $('#pair-grid').innerHTML=`<div class="pair-grid">${filtered.slice(page*pageSize,(page+1)*pageSize).map(c=>`<article class="well"><div class="pair-images"><a href="/api/assets/${esc(c.frontAsset)}" target="_blank" rel="noopener"><img loading="lazy" src="/api/assets/${esc(c.frontAsset)}" alt="${esc(c.name)} front"></a><a href="/api/assets/${esc(c.backAsset)}" target="_blank" rel="noopener"><img loading="lazy" src="/api/assets/${esc(c.backAsset)}" alt="${esc(c.name)} back"></a></div><div class="pair-title">${c.quantity}× ${esc(c.name)}</div><div class="pair-subtitle">${esc(c.deckName)}</div></article>`).join('')}</div>`;
    $('#pair-pages').innerHTML=`<button class="button small" id="pairs-prev" ${page===0?'disabled':''}>Previous</button><span class="subtitle-line">Page ${page+1} / ${max+1} · ${filtered.length} unique pairs</span><button class="button small" id="pairs-next" ${page>=max?'disabled':''}>Next</button>`;
    $('#pairs-prev').onclick=()=>{page--;grid();};$('#pairs-next').onclick=()=>{page++;grid();};
  }
  grid();$('#order-search').oninput=e=>{query=e.target.value;page=0;grid();};
  if(saved){$('#open-saved-order').onclick=()=>attempt(()=>openOrder(plan.id));return;}
  function enableBuild(){$('#build-order').disabled=!!plan.warnings?.length&&!$('#ack-order-warnings')?.checked;}
  if($('#ack-order-warnings'))$('#ack-order-warnings').onchange=enableBuild;enableBuild();
  $('#build-order').onclick=async()=>{
    try{
      if(state.busy)throw new Error('Wait for the current task before building an order.');
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
  const host=modal('Your print package is ready',`<div class="empty-state"><span class="success-check">✓</span><h2>${order.count} cards, correctly paired.</h2><p>${order.decks.map(d=>esc(d.name)).join(' · ')}</p><div class="actions"><a class="button" id="download-order" href="${esc(order.download)}" download>Save images ZIP · ${bytes(order.zipBytes)}</a><button class="button primary" id="send-order">Open in TCGPlaytest ↗</button></div></div><div class="notice info">Proxy Foundry stays open. In the printer tab, choose Add or Replace if cards are already present, then review the print preview before checkout.</div>${order.zipBytes>1024**3?'<div class="notice">The helper will send this order as multiple ZIP batches, each at most 1 GB, into the same TCGPlaytest design. Original image quality is unchanged.</div>':''}`,{footer:'<button class="button quiet" id="view-orders">View saved orders</button>'});
  $('#send-order').onclick=()=>attempt(()=>openOrder(order.id));
  $('#view-orders').onclick=()=>{closeModal();nav('orders');};
}
async function openOrder(id){
  if(!state.helper){setupHelper();return;}
  const order=await api('/api/orders/'+id);
  if(order.zipBytes>1024**3&&!state.helperCapabilities?.includes('paired-zip-batches'))throw new Error('Large orders need Print Helper 1.1.0. Reload the updated extension in edge://extensions or chrome://extensions, then reload this page. No uninstall is needed.');
  const transfer=await api('/api/orders/'+id+'/transfer',{});
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{window.removeEventListener('message',listener);reject(new Error('The helper did not respond. Reconnect the helper and reopen the saved order.'));},40000);
    function listener(e){if(e.source!==window||e.origin!==location.origin||e.data?.source!=='proxy-foundry-helper')return;if(!['PF_WORKSPACE_OPENED','PF_WORKSPACE_ERROR'].includes(e.data.type))return;clearTimeout(timer);window.removeEventListener('message',listener);e.data.type==='PF_WORKSPACE_OPENED'?resolve():reject(new Error(e.data.error));}
    window.addEventListener('message',listener);window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_OPEN',transfer},location.origin);
  });
  toast('TCGPlaytest opened in a new tab. Keep the local launcher running until the upload finishes.');
}
