import {$,$$,esc,state,api,attempt,toast,modal,closeModal,job,loading,badge,date,nav,confirmAction,saveApiFile} from './ui.js';
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
  tray.classList.remove('hidden');tray.innerHTML=`<strong>${ids.length} deck${ids.length===1?'s':''} · ${count} cards</strong><button class="button quiet small" id="clear-selection">Clear</button><button class="button small" id="render-selected">Generate images</button><button class="button primary small" id="order-selected">Review & Print</button>`;
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
  }).join('')}<button class="add-tile" id="add-tile"><span>＋</span>Start another deck<small>Paste a Scryfall link or decklist</small></button></div>`:'<div class="empty-state"></div>'}
  <div class="subtitle-line section-gap">Select multiple decks to combine them into one explicitly paired print order. Nothing is purchased automatically.</div>`;
  for(const id of ['import-deck','add-tile'])if($('#'+id))$('#'+id).onclick=()=>attempt(()=>importDeck());
  $('#new-empty').onclick=()=>attempt(async()=>{const d=await api('/api/decks/new',{});nav('deck/'+d.id+'/setup');});
  $$('[data-filter]').forEach(el=>el.onclick=()=>{filter=el.dataset.filter;showLibrary()});
  $('#deck-search').oninput=e=>{query=e.target.value;const pos=e.target.selectionStart;showLibrary();$('#deck-search').focus();try{$('#deck-search').setSelectionRange(pos,pos)}catch{}};
  $$('[data-select]').forEach(el=>el.onchange=()=>{el.checked?state.selected.add(el.dataset.select):state.selected.delete(el.dataset.select);el.closest('.deck-tile').classList.toggle('selected',el.checked);selectTray();});
  $('#new-empty').remove();
  $('.hero-strip')?.remove();
  $('.page-head .eyebrow')?.remove();
  $('.page-head p')?.remove();
  $('.subtitle-line')?.remove();
  $('.add-tile')?.remove();
  const emptyState=$('.empty-state');
  if(emptyState){const message=document.createElement('p');message.textContent=state.decks.length?'No decks match your search.':'No decks yet. Add a deck to get started.';message.style.margin='0 auto';emptyState.style.padding='42px 20px';emptyState.replaceChildren(message);}
  const action=$('#import-deck');if(action)action.textContent='＋ Add New Deck';
  const all=$('[data-filter="all"]');if(all)all.textContent='All Decks';
  const work=$('[data-filter="work"]');if(work)work.textContent='Needs Preparation';
  const selectAll=document.createElement('button');selectAll.type='button';selectAll.className='button quiet small';
  const allVisible=decks.length>0&&decks.every(deck=>state.selected.has(deck.id));
  selectAll.textContent=allVisible?'Deselect All':'Select All';selectAll.disabled=!decks.length;
  selectAll.onclick=()=>{for(const deck of decks)allVisible?state.selected.delete(deck.id):state.selected.add(deck.id);showLibrary();};
  $('#deck-search').style.paddingLeft='40px';
  const deckActions=document.createElement('div');deckActions.setAttribute('role','group');deckActions.setAttribute('aria-label','Deck library actions');
  deckActions.style.display='flex';deckActions.style.alignItems='center';deckActions.style.justifyContent='flex-end';deckActions.style.flexWrap='wrap';deckActions.style.gap='10px';deckActions.style.flex='1 1 520px';
  const search=$('.search');search.style.flex='1 1 220px';search.style.minWidth='180px';
  deckActions.append(search,selectAll);$('.toolbar')?.append(deckActions);
  const savedOrders=document.createElement('button');savedOrders.type='button';savedOrders.className='button quiet small';savedOrders.textContent='Saved print orders';
  savedOrders.onclick=()=>nav('orders');deckActions.append(savedOrders);
  for(const tile of $$('.deck-tile')){
    $('.tile-open',tile)?.remove();
    tile.style.cursor='pointer';
    tile.onclick=event=>{if(event.target.closest('.deck-select'))return;const ident=tile.dataset.deck;nav('deck/'+ident);};
  }
  selectTray();
}
function mountNavigation(){
  $('.sidebar').hidden=true;$('.sidebar').style.display='none';
  const shell=$('.workspace-shell');shell.style.marginLeft='0';shell.style.width='100%';
  const tray=$('#selection-tray');tray.style.left='50%';tray.style.maxWidth='calc(100vw - 24px)';
  const bar=$('.topbar');bar.replaceChildren();
  const brand=document.createElement('a');brand.href='#decks';brand.setAttribute('aria-label','Bulk Proxy Forge home');
  brand.style.display='flex';brand.style.alignItems='center';brand.style.gap='10px';brand.style.fontWeight='750';
  const logo=document.createElement('img');logo.src='/site/logo.png';logo.alt='Bulk Proxy Forge';logo.style.width='clamp(120px, 15vw, 180px)';logo.style.height='auto';
  brand.append(logo);bar.append(brand);
  const links=document.createElement('nav');links.setAttribute('aria-label','Main navigation');
  links.style.display='flex';links.style.gap='8px';links.style.marginLeft='auto';
  const icons={
    decks:'<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 3h8v8H2zM14 3h8v8h-8zM2 14h8v8H2zM14 14h8v8h-8z"/><path d="M4 1h8v8M16 1h8v8M4 12h8v8M16 12h8v8"/></svg>',
    templates:'<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="5" y="1.5" width="14" height="21" rx="1.7"/><path d="M7 5h10M7 16h10M7 19h10"/></svg>',
    settings:'<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><path d="M10 2h4l.5 2.2 1.7.7 1.9-1.2 2.8 2.8-1.2 1.9.7 1.7L22 10v4l-2.2.5-.7 1.7 1.2 1.9-2.8 2.8-1.9-1.2-1.7.7L14 22h-4l-.5-2.2-1.7-.7-1.9 1.2-2.8-2.8 1.2-1.9-.7-1.7L2 14v-4l2.2-.5.7-1.7-1.2-1.9 2.8-2.8 1.9 1.2 1.7-.7z"/></svg>',
    discord:'<img src="/site/discord.svg" alt="" width="22" height="22" style="filter:invert(1)">'
  };
  const items=[['decks','Deck Library','#decks'],['templates','Templates','#templates'],
               ['settings','Settings','#settings'],['discord','Discord','https://discord.com/']];
  for(const [key,title,href] of items){
    const link=document.createElement('a');link.href=href;link.title=title;link.setAttribute('aria-label',title);
    link.innerHTML=icons[key];link.dataset.nav=key;link.className='button quiet icon';link.style.fontSize='21px';
    if(key==='discord'){link.target='_blank';link.rel='noopener noreferrer';}
    links.append(link);
  }
  bar.append(links);
}
let routeCounter=0,lastHash=location.hash||'#decks';
export async function route(){
  if(state.dirty&&location.hash!==lastHash&&!window.confirm('Leave without saving your setup changes?')){history.replaceState(null,'',lastHash);return;}
  state.dirty=false;lastHash=location.hash||'#decks';const current=++routeCounter;const [name='decks',id,tab]=lastHash.slice(1).split('/');state.route=name;
  $('#selection-tray').classList.add('hidden');$$('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===(name==='deck'?'decks':name)));
  document.title=`${{decks:'Deck Library',deck:'Deck',templates:'Templates',orders:'Print Orders',settings:'Settings'}[name]||'Bulk Proxy Forge'} · Bulk Proxy Forge`;
  $('#main').innerHTML=loading();
  try{
    await refreshLibrary();if(current!==routeCounter)return;
    if(name==='deck'&&id)await showDeck(id,tab||'cards');
    else if(name==='templates')await (state.bootstrap?.browser?(await import('/web/templates-browser.js')).showTemplates():showTemplates());
    else if(name==='orders')await showOrders();
    else if(name==='settings')await (state.bootstrap?.browser?(await import('/web/settings-browser.js')).showSettings():showSettings());
    else if(name==='help')await showHelp();
    else{state.route='decks';showLibrary();}
  }catch(e){$('#main').innerHTML=`<div class="notice error">${esc(e.message)}</div><button class="button" id="retry-page">Retry</button>`;$('#retry-page').onclick=()=>route();}
}
async function boot(){
  try{
    const data=await api('/api/bootstrap');state.csrf=data.csrf;state.bootstrap=data;
    mountNavigation();
    window.addEventListener('hashchange',route);
    window.addEventListener('message',e=>{
      if(e.source!==window||e.origin!==location.origin||e.data?.source!=='proxy-foundry-helper')return;
      if(e.data.type==='PF_WORKSPACE_PONG'){
        state.helperCapabilities=Array.isArray(e.data.capabilities)?e.data.capabilities:[];state.helper=true;
      }
      if(e.data.type==='PF_WORKSPACE_ERROR')toast(e.data.error||'The print helper could not open the order.',true);
    });
    const ping=()=>window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_PING'},location.origin);
    ping();setTimeout(ping,1000);
    document.addEventListener('click',event=>{
      if(!state.bootstrap?.browser)return;
      const link=event.target.closest('a[download][href^="/api/"]');
      if(!link)return;
      event.preventDefault();
      const name=link.getAttribute('download')||
        (link.href.includes('/helper/')?'BulkProxyForge_Print_Helper.zip':'BulkProxyForge_Order.zip');
      attempt(()=>saveApiFile(link.getAttribute('href'),name));
    });
    document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(a&&state.dirty){e.preventDefault();nav(a.getAttribute('href').slice(1));}});
    await route();
  }catch(e){$('#main').innerHTML=`<div class="notice error">${esc(e.message)}\nReload this page to reopen your workspace.</div>`;}
}
window.addEventListener('error',e=>{if(state.csrf)api('/api/client-error',{error:e.message+'\n'+(e.error?.stack||'')}).catch(()=>{});});
boot();
