import {$,$$,esc,state,api,attempt,toast,modal,closeModal,job,loading,empty,badge,date,nav,confirmAction} from './ui.js';
import {showDeck,importDeck} from './deck.js';
import {showTemplates} from './templates.js';
import {showOrders,chooseOrder,setupHelper} from './orders.js';
import {showSettings,showHelp} from './settings.js';
import {renderDecks} from './render.js';

export async function refreshLibrary(){
  state.decks=await api('/api/decks');state.templates=await api('/api/templates');
  $('#nav-count').textContent=state.decks.length||'';
  for(const id of [...state.selected])if(!state.decks.some(d=>d.id===id))state.selected.delete(id);
}
function selectTray(){
  const tray=$('#selection-tray'),ids=[...state.selected];
  if(!ids.length){tray.classList.add('hidden');return;}
  const count=state.decks.filter(d=>state.selected.has(d.id)).reduce((s,d)=>s+(d.summary?.cards||0),0);
  tray.classList.remove('hidden');tray.innerHTML=`<strong>${ids.length} deck${ids.length===1?'':'s'} · ${count} cards</strong><button class="button quiet small" id="clear-selection">Clear</button><button class="button small" id="render-selected">Generate images</button><button class="button primary small" id="order-selected">Review print order →</button>`;
  $('#clear-selection').onclick=()=>{state.selected.clear();showLibrary();};
  $('#render-selected').onclick=()=>attempt(async()=>{await renderDecks(ids,{onUpdate:async()=>{await refreshLibrary();if(state.route==='decks')showLibrary();}});});
  $('#order-selected').onclick=()=>attempt(()=>chooseOrder(ids));
}
let filter='all',query='';
function showLibrary(){
  const decks=state.decks.filter(d=>d.name.toLowerCase().includes(query.toLowerCase())&&(filter==='all'||(filter==='ready'?d.status==='ready':d.status!=='ready')));
  $('#main').innerHTML=`<div class="page-head"><div><span class="eyebrow">YOUR NEXT GAME STARTS HERE</span><h1>Deck library</h1><p>A home for your decks, your artwork, and the cards you’re ready to print.</p></div><div class="actions"><button class="button" id="new-empty">New blank deck</button><button class="button primary" id="import-deck">＋ Import deck</button></div></div>
  <section class="hero-strip"><div><span class="eyebrow">FROM DECKLIST TO TABLETOP</span><h2>Make the deck yours.<br>We’ll handle the print prep.</h2><p>Keep the art from your selected Scryfall printings, bring your own, or mix both. Start with approved templates or create a style of your own.</p></div><div class="steps-compact"><div class="step-mini"><b>1</b>Import a deck</div><span class="step-arrow">→</span><div class="step-mini"><b>2</b>Art & style</div><span class="step-arrow">→</span><div class="step-mini"><b>3</b>Render & print</div></div></section>
  <div class="toolbar"><div class="filter-pills"><button data-filter="all" class="${filter==='all'?'active':''}">All decks · ${state.decks.length}</button><button data-filter="ready" class="${filter==='ready'?'active':''}">Ready to print</button><button data-filter="work" class="${filter==='work'?'active':''}">In progress</button></div><label class="search"><input id="deck-search" type="search" aria-label="Search decks" placeholder="Find a deck…" value="${esc(query)}"></label></div>
  ${decks.length?`<div class="deck-grid">${decks.map(d=>{
    const cover=d.cover||'';return `<article class="deck-tile ${state.selected.has(d.id)?'selected':''}" data-deck="${d.id}"><div class="deck-cover"><a href="#deck/${d.id}" aria-label="Open ${esc(d.name)}">${cover?`<img src="${esc(cover)}" alt="" loading="lazy">`:`<span class="deck-monogram">${esc(d.name[0]?.toUpperCase()||'D')}</span>`}</a><label class="deck-select"><input type="checkbox" data-select="${d.id}" aria-label="Select ${esc(d.name)} for a print order" ${state.selected.has(d.id)?'checked':''}></label>${d.settings?.backAsset?`<img class="deck-back-thumb" src="/api/assets/${esc(d.settings.backAsset)}" alt="Deck back">`:''}</div><div class="deck-content"><a href="#deck/${d.id}"><h3 title="${esc(d.name)}">${esc(d.name)}</h3></a><div class="deck-meta"><span>${d.summary?.cards||0} cards</span><span>${d.summary?.rendered||0}/${d.summary?.faces||0} images</span><span>${date(d.updatedAt)}</span></div><div class="deck-footer">${badge(d.status)}<a class="tile-open" href="#deck/${d.id}">Open deck ↗</a></div></div></article>`;
  }).join('')}<button class="add-tile" id="add-tile"><span>＋</span>Start another deck<small>Paste a Scryfall link or decklist</small></button></div>`:empty(state.decks.length?'No decks match your search':'Your first deck belongs here',state.decks.length?'Try a different name or status filter.':'Import a Scryfall deck or paste a card list. Your selected printing, quantities, and double-faced cards stay together.',`<button class="button primary" id="empty-import">Import your first deck →</button>`)}
  <div class="subtitle-line section-gap">Select multiple decks to combine them into one explicitly paired print order. Nothing is purchased automatically.</div>`;
  for(const id of ['import-deck','add-tile','empty-import'])if($('#'+id))$('#'+id).onclick=()=>attempt(()=>importDeck());
  $('#new-empty').onclick=()=>attempt(async()=>{const d=await api('/api/decks/new',{});nav('deck/'+d.id+'/setup');});
  $$('[data-filter]').forEach(el=>el.onclick=()=>{filter=el.dataset.filter;showLibrary()});
  $('#deck-search').oninput=e=>{query=e.target.value;const pos=e.target.selectionStart;showLibrary();$('#deck-search').focus();try{$('#deck-search').setSelectionRange(pos,pos)}catch{}};
  $$('[data-select]').forEach(el=>el.onchange=()=>{el.checked?state.selected.add(el.dataset.select):state.selected.delete(el.dataset.select);el.closest('.deck-tile').classList.toggle('selected',el.checked);selectTray();});
  selectTray();
}
let routeCounter=0,lastHash=location.hash||'#decks';
export async function route(){
  if(state.dirty&&location.hash!==lastHash&&!window.confirm('Leave without saving your setup changes?')){history.replaceState(null,'',lastHash);return;}
  state.dirty=false;lastHash=location.hash||'#decks';const current=++routeCounter;const [name='decks',id,tab]=lastHash.slice(1).split('/');state.route=name;
  $('#selection-tray').classList.add('hidden');$$('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===(name==='deck'?'decks':name)));
  $('#breadcrumb').innerHTML=`Workspace <span>/</span> ${esc({decks:'Deck library',deck:'Deck studio',templates:'Templates',orders:'Print orders',settings:'Settings & backup',help:'Quick start & tools'}[name]||'Deck library')}`;
  $('#main').innerHTML=loading();
  try{
    await refreshLibrary();if(current!==routeCounter)return;
    if(name==='deck'&&id)await showDeck(id,tab||'cards');
    else if(name==='templates')await showTemplates();
    else if(name==='orders')await showOrders();
    else if(name==='settings')await showSettings();
    else if(name==='help')await showHelp();
    else{state.route='decks';showLibrary();}
  }catch(e){$('#main').innerHTML=`<div class="notice error">${esc(e.message)}</div><button class="button" id="retry-page">Retry</button>`;$('#retry-page').onclick=()=>route();}
}
async function boot(){
  try{
    const data=await api('/api/bootstrap');state.csrf=data.csrf;state.bootstrap=data;
    $('#global-import').onclick=()=>attempt(()=>importDeck());
    $('#helper-state').onclick=setupHelper;
    window.addEventListener('hashchange',route);
    window.addEventListener('message',e=>{
      if(e.source!==window||e.origin!==location.origin||e.data?.source!=='proxy-foundry-helper')return;
      if(e.data.type==='PF_WORKSPACE_PONG'){
        state.helperCapabilities=Array.isArray(e.data.capabilities)?e.data.capabilities:[];state.helper=true;$('#helper-state').classList.add('connected');$('#helper-state b').textContent='connected';
      }
      if(e.data.type==='PF_WORKSPACE_ERROR')toast(e.data.error||'The print helper could not open the order.',true);
    });
    const ping=()=>window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_PING'},location.origin);
    ping();setTimeout(ping,1000);setTimeout(()=>{if(!state.helper)$('#helper-state b').textContent='setup';},2200);
    document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(a&&state.dirty){e.preventDefault();nav(a.getAttribute('href').slice(1));}});
    await route();
  }catch(e){$('#main').innerHTML=`<div class="notice error">${esc(e.message)}\nKeep the launcher window open, then reload this page.</div>`;}
}
window.addEventListener('error',e=>{if(state.csrf)api('/api/client-error',{error:e.message+'\n'+(e.error?.stack||'')}).catch(()=>{});});
boot();
