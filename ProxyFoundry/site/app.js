import {$,$$,esc,state,api,attempt,toast,modal,closeModal,job,loading,badge,humanStatus,date,thumbnail,nav,confirmAction,saveApiFile,showWorkspaceError} from './ui.js';
import {showDeck,importDeck} from './deck.js';
import {showTemplates} from './templates.js';
import {showOrders,chooseOrder,setupHelper} from './orders.js';
import {showSettings,showHelp} from './settings.js';
import {renderDecks} from './render.js';
import {visibleDecks,resumeDeletions} from './deletion.js';

export async function refreshLibrary({templates=true}={}){
  state.decks=visibleDecks(await api('/api/decks'));if(templates)state.templates=await api('/api/templates');
  $('#nav-count').textContent=state.decks.length||'';
  for(const id of [...state.selected])if(!state.decks.some(d=>d.id===id))state.selected.delete(id);
}
function selectTray(){
  const tray=$('#selection-tray'),ids=[...state.selected];
  if(!ids.length){tray.classList.add('hidden');return;}
  const count=state.decks.filter(d=>state.selected.has(d.id)).reduce((s,d)=>s+(d.summary?.cards||0),0);
  tray.classList.remove('hidden');tray.innerHTML=`<strong>${ids.length} deck${ids.length===1?'s':''} · ${count} cards</strong><button class="button quiet small" id="clear-selection">Clear</button><button class="button small" id="render-selected">Generate images</button><button class="button primary small" id="order-selected">Review & Print</button>`;
  $('#clear-selection').onclick=()=>{state.selected.clear();filterLibrary();selectTray();};
  $('#render-selected').onclick=()=>attempt(async()=>{await renderDecks(ids);});
  $('#order-selected').onclick=()=>attempt(()=>chooseOrder(ids));
}
let filter='all',query='';
function showLibrary(){
  const decks=state.decks;
  $('#main').innerHTML=`<div class="page-head"><div><span class="eyebrow">YOUR NEXT GAME STARTS HERE</span><h1>Deck library</h1><p>A home for your decks, your artwork, and the cards you’re ready to print.</p></div><div class="actions"><button class="button" id="new-empty">New blank deck</button><button class="button primary" id="import-deck">＋ Import deck</button></div></div>
  <section class="hero-strip"><div><span class="eyebrow">FROM DECKLIST TO TABLETOP</span><h2>Make the deck yours.<br>We’ll handle the print prep.</h2><p>Keep the art from your selected Scryfall printings, bring your own, or mix both. Start with approved templates or create a style of your own.</p></div><div class="steps-compact"><div class="step-mini"><b>1</b>Import a deck</div><span class="step-arrow">→</span><div class="step-mini"><b>2</b>Art & style</div><span class="step-arrow">→</span><div class="step-mini"><b>3</b>Render & print</div></div></section>
  <div class="toolbar"><div class="filter-pills"><button data-filter="all" class="${filter==='all'?'active':''}">All decks · ${state.decks.length}</button><button data-filter="ready" class="${filter==='ready'?'active':''}">Ready to print</button><button data-filter="work" class="${filter==='work'?'active':''}">In progress</button></div><label class="search"><input id="deck-search" type="search" aria-label="Search decks" placeholder="Find a deck…" value="${esc(query)}"></label></div>
  ${decks.length?`<div class="deck-grid">${decks.map(d=>{
    const cover=d.cover||'';return `<article class="deck-tile ${state.selected.has(d.id)?'selected':''}" data-deck="${d.id}"><div class="deck-cover"><a href="#deck/${d.id}" aria-label="Open ${esc(d.name)}">${cover?`<img src="${esc(cover)}" alt="" loading="lazy">`:`<span class="deck-monogram">${esc(d.name[0]?.toUpperCase()||'D')}</span>`}</a><label class="deck-select"><input type="checkbox" data-select="${d.id}" aria-label="Select ${esc(d.name)} for a print order" ${state.selected.has(d.id)?'checked':''}></label>${d.settings?.backAsset?`<img class="deck-back-thumb" src="/api/assets/${esc(d.settings.backAsset)}" alt="Deck back">`:''}</div><div class="deck-content"><a href="#deck/${d.id}"><h3 title="${esc(d.name)}">${esc(d.name)}</h3></a><div class="deck-meta"><span>${d.summary?.cards||0} cards</span><span>${d.summary?.rendered||0}/${d.summary?.faces||0} images</span><span>${date(d.updatedAt)}</span></div><div class="deck-footer">${badge(d.status)}<a class="tile-open" href="#deck/${d.id}">Open deck ↗</a></div></div></article>`;
  }).join('')}<button class="add-tile" id="add-tile"><span>＋</span>Start another deck<small>Paste a Scryfall link or decklist</small></button></div>`:'<div class="empty-state"></div>'}
  <div class="subtitle-line section-gap">Select multiple decks to combine them into one explicitly paired print order. Nothing is purchased automatically.</div>`;
  for(const id of ['import-deck','add-tile'])if($('#'+id))$('#'+id).onclick=()=>attempt(()=>importDeck());
  $('#new-empty').onclick=()=>attempt(async()=>{const d=await api('/api/decks/new',{});nav('deck/'+d.id+'/setup');});
  $$('[data-filter]').forEach(el=>el.onclick=()=>{filter=el.dataset.filter;filterLibrary()});
  $('#deck-search').oninput=e=>{query=e.target.value;filterLibrary();};
  $$('[data-select]').forEach(el=>el.onchange=()=>{el.checked?state.selected.add(el.dataset.select):state.selected.delete(el.dataset.select);el.closest('.deck-tile').classList.toggle('selected',el.checked);filterLibrary();selectTray();});
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
  const visible=matchingDecks(),allVisible=visible.length>0&&visible.every(deck=>state.selected.has(deck.id));
  selectAll.id='select-visible-decks';selectAll.textContent=allVisible?'Deselect All':'Select All';selectAll.disabled=!visible.length;
  selectAll.onclick=()=>{const visible=matchingDecks(),all=visible.length>0&&visible.every(deck=>state.selected.has(deck.id));for(const deck of visible)all?state.selected.delete(deck.id):state.selected.add(deck.id);filterLibrary();selectTray();};
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
  filterLibrary();selectTray();
  state.generationView={route:'decks',refresh:refreshLibraryProgress};
}
function matchingDecks(){
  const text=query.toLowerCase();
  return state.decks.filter(deck=>deck.name.toLowerCase().includes(text)&&(filter==='all'||(filter==='ready'?deck.status==='ready':deck.status!=='ready')));
}
function filterLibrary(){
  const main=$('#main'),visible=matchingDecks(),ids=new Set(visible.map(deck=>deck.id));
  for(const tile of $$('.deck-tile',main)){
    tile.hidden=!ids.has(tile.dataset.deck);tile.classList.toggle('selected',state.selected.has(tile.dataset.deck));
    const check=$('[data-select]',tile);if(check)check.checked=state.selected.has(tile.dataset.deck);
  }
  for(const button of $$('[data-filter]',main)){
    button.classList.toggle('active',button.dataset.filter===filter);
  }
  const select=$('#select-visible-decks');
  if(select){select.disabled=!visible.length;select.textContent=visible.length&&visible.every(deck=>state.selected.has(deck.id))?'Deselect All':'Select All';}
  let empty=$('.empty-state',main);
  if(!empty){empty=document.createElement('div');empty.className='empty-state';empty.style.padding='42px 20px';main.append(empty);}
  if(!empty.firstElementChild){const message=document.createElement('p');message.style.margin='0 auto';empty.append(message);}
  empty.firstElementChild.textContent=state.decks.length?'No decks match your search.':'No decks yet. Add a deck to get started.';empty.hidden=visible.length>0;
}
export async function refreshLibraryProgress(){
  //Image progress does not change templates or the collection's input controls.
  await refreshLibrary({templates:false});
  if(state.route!=='decks'||!$('#deck-search'))return;
  const decks=new Map(state.decks.map(deck=>[deck.id,deck]));
  for(const tile of $$('.deck-tile')){
    const deck=decks.get(tile.dataset.deck);if(!deck)continue;
    const meta=$$('.deck-meta span',tile);
    if(meta[0])meta[0].textContent=`${deck.summary?.cards||0} cards`;
    if(meta[1])meta[1].textContent=`${deck.summary?.rendered||0}/${deck.summary?.faces||0} images`;
    if(meta[2])meta[2].textContent=date(deck.updatedAt);
    const status=$('.badge',tile);if(status){status.className='badge '+deck.status;status.textContent=humanStatus(deck.status);}
    const link=$('.deck-cover a',tile),src=thumbnail(deck.cover||'');
    let image=$('img',link);
    if(src&&!image){image=document.createElement('img');image.loading='lazy';image.alt='';link.replaceChildren(image);}
    if(image&&image.getAttribute('src')!==src)image.src=src;
  }
  filterLibrary();selectTray();
}
function mountNavigation(){
  $('.sidebar').hidden=true;$('.sidebar').style.display='none';
  $('.skip').style.left='10px';
  const shell=$('.workspace-shell');shell.style.marginLeft='0';shell.style.width='100%';
  const tray=$('#selection-tray');tray.style.left='50%';tray.style.maxWidth='calc(100vw - 24px)';
  const bar=$('.topbar');bar.replaceChildren();
  const brand=document.createElement('a');brand.href='#decks';brand.setAttribute('aria-label','Bulk Proxy Forge home');
  brand.style.display='flex';brand.style.alignItems='center';brand.style.gap='10px';brand.style.fontWeight='750';
  const logo=document.createElement('img');logo.src='/site/logo.png';logo.alt='Bulk Proxy Forge';logo.style.width='clamp(120px, 15vw, 180px)';logo.style.height='auto';
  brand.append(logo);bar.append(brand);
  const links=document.createElement('nav');links.setAttribute('aria-label','Main navigation');
  links.style.display='flex';links.style.gap='clamp(3px, .55vw, 8px)';links.style.marginLeft='auto';
  const icons={
    decks:'<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 3h8v8H2zM14 3h8v8h-8zM2 14h8v8H2zM14 14h8v8h-8z"/><path d="M4 1h8v8M16 1h8v8M4 12h8v8M16 12h8v8"/></svg>',
    templates:'<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="5" y="1.5" width="14" height="21" rx="1.7"/><path d="M7 5h10M7 16h10M7 19h10"/></svg>',
    settings:'<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><path d="M10 2h4l.5 2.2 1.7.7 1.9-1.2 2.8 2.8-1.2 1.9.7 1.7L22 10v4l-2.2.5-.7 1.7 1.2 1.9-2.8 2.8-1.9-1.2-1.7.7L14 22h-4l-.5-2.2-1.7-.7-1.9 1.2-2.8-2.8 1.2-1.9-.7-1.7L2 14v-4l2.2-.5.7-1.7-1.2-1.9 2.8-2.8 1.9 1.2 1.7-.7z"/></svg>',
  };
  const items=[['decks','Deck Library','#decks'],['templates','Templates','#templates'],
               ['settings','Settings','#settings'],['discord','Discord','https://discord.gg/au2rCSbG2B']];
  for(const [key,title,href] of items){
    const link=document.createElement('a');link.href=href;link.title=title;link.setAttribute('aria-label',title);
    link.dataset.nav=key;link.className='button quiet icon';link.style.fontSize='21px';
    const iconSize='clamp(34px, 2.8vw, 40px)';link.style.width=iconSize;link.style.height=iconSize;link.style.minWidth='0';link.style.minHeight='0';link.style.padding='0';link.style.flex='none';
    if(key==='discord'){
      const image=document.createElement('img');image.src='/site/discord.png';image.alt='';image.style.width='22px';image.style.height='22px';image.style.objectFit='contain';image.style.display='block';
      link.append(image);link.target='_blank';link.rel='noopener noreferrer';
    }
    else link.innerHTML=icons[key];
    links.append(link);
  }
  bar.append(links);
}
let routeCounter=0,lastHash=location.hash||'#decks';
export async function route(){
  if(state.dirty&&location.hash!==lastHash&&!window.confirm('Leave without saving your setup changes?')){history.replaceState(null,'',lastHash);return;}
  state.generationView=null;state.dirty=false;lastHash=location.hash||'#decks';const current=++routeCounter;const [name='decks',id,tab]=lastHash.slice(1).split('/');state.route=name;
  state.routeEpoch=current;state.deckTab=tab||'cards';state.routeDeck=id||null;
  $('#selection-tray').classList.add('hidden');
  for(const link of $$('[data-nav]')){
    const selected=link.dataset.nav===(name==='deck'?'decks':name);
    link.classList.toggle('active',selected);
    if(selected)link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
    link.style.background=selected?'linear-gradient(#48250f,#2b180d)':'';
    link.style.borderColor=selected?'var(--accent)':'';
    link.style.color=selected?'var(--accent2)':'';
    link.style.boxShadow=selected?'0 0 12px #f47a2038, inset 0 0 0 1px #7a431f':'';
  }
  document.title=`${{decks:'Deck Library',deck:'Deck',templates:'Templates',orders:'Print Orders',settings:'Settings'}[name]||'Bulk Proxy Forge'} · Bulk Proxy Forge`;
  if(name==='decks'&&state.immediateLibrary){
    state.immediateLibrary=false;showLibrary();$('#nav-count').textContent=state.decks.length||'';return;
  }
  $('#main').innerHTML=loading();
  try{
    if(name!=='orders')await refreshLibrary();if(current!==routeCounter)return;
    if(name==='deck'&&id)await showDeck(id,tab||'cards');
    else if(name==='templates')await (state.bootstrap?.browser?(await import('/web/templates-browser.js')).showTemplates():showTemplates());
    else if(name==='orders')await showOrders(id);
    else if(name==='settings')await (state.bootstrap?.browser?(await import('/web/settings-browser.js')).showSettings():showSettings());
    else if(name==='help')await showHelp();
    else{state.route='decks';showLibrary();}
  }catch(e){if(current===routeCounter)showWorkspaceError(e,()=>route());}
}
async function boot(){
  try{
    const data=await api('/api/bootstrap');state.csrf=data.csrf;state.bootstrap=data;
    mountNavigation();
    resumeDeletions();
    window.addEventListener('pf-library-deletion',()=>{state.immediateLibrary=false;showLibrary();$('#nav-count').textContent=state.decks.length||'';});
    window.addEventListener('pf-deletion-failed',()=>{if(state.route==='decks')void route();});
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
    window.dispatchEvent(new Event('pf-ui-ready'));
  }catch(e){showWorkspaceError(e,()=>location.reload());window.dispatchEvent(new CustomEvent('pf-ui-error',{detail:e.message}));}
}
window.addEventListener('error',e=>{if(state.csrf)api('/api/client-error',{error:e.message+'\n'+(e.error?.stack||'')}).catch(()=>{});});
boot();
