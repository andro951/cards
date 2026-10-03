import {startMetadata,ensureMetadata} from './metadata.js';
import {deleteDeck} from './deletion.js';
import {mountBackPicker} from './backs.js';
import {$,$$,esc,state,api,attempt,toast,modal,closeModal,errorBox,job,loading,empty,badge,asset,thumbnail,humanStatus,nav,confirmAction,uploadImage,downloadPost,downloadBlob,saveApiFile,requireDeckAvailable} from './ui.js';
import {renderSetup,templateOptions,pickFile,rarities} from './setup.js';
import {renderDecks,renderCard} from './render.js';
import {ensureArtworkReady} from './artwork-review.js';
import {chooseOrder,setupHelper} from './orders.js';
import {creditFields,bindCreditFields,ensureCustomArtCredits} from './credits.js';
const views=new Map();
let activeCardsView=null;
window.addEventListener('hashchange',()=>{activeCardsView=null;});
async function prepareDeckSource(source){
  const text=source.trim();
  if(/^https:\/\/(?:www\.)?(?:archidekt\.com\/decks\/|mtggoldfish\.com\/deck\/)/i.test(text)){
    const adapters=await import('./deck-adapters.mjs');
    const expected=adapters.identifyDeck(text);
    if(!state.helperCapabilities?.includes('deck-import'))
      throw new Error('Automatic Archidekt and MTGGoldfish imports need the optional browser helper. You can also download the deck export from that site and upload it here.');
    const requestId=crypto.randomUUID();
    const reply=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{window.removeEventListener('message',receive);reject(new Error('The browser helper did not respond. Reload the helper and this page, or upload the deck export.'));},45000);
      function receive(event){
        if(event.source!==window||event.origin!==location.origin||event.data?.source!=='proxy-foundry-helper'||event.data.type!=='PF_DECK_IMPORT_REPLY'||event.data.requestId!==requestId)return;
        clearTimeout(timer);window.removeEventListener('message',receive);resolve(event.data);
      }
      window.addEventListener('message',receive);
      window.postMessage({source:'proxy-foundry-workspace',type:'PF_DECK_IMPORT_REQUEST',requestId,url:text},location.origin);
    });
    if(!reply.ok)throw new Error(reply.error||'The browser helper could not fetch this deck.');
    if(reply.deck?.site!==expected.site||reply.deck?.id!==expected.id)throw new Error('The browser helper returned a different deck.');
    const deck=expected.site==='archidekt'?adapters.parseArchidekt(JSON.parse(reply.deck.body)):adapters.parseGoldfish(reply.deck.body,reply.deck.title);
    return JSON.stringify(deck);
  }
  if(text.startsWith('{')){
    const data=JSON.parse(text);
    if(Array.isArray(data.cards)&&Array.isArray(data.categories)){
      const adapters=await import('./deck-adapters.mjs');
      return JSON.stringify(adapters.parseArchidekt(data));
    }
  }
  if(/^Sideboard\s*:?$/im.test(text)&&!/^Deck\s*:?$/im.test(text)){
    const adapters=await import('./deck-adapters.mjs');
    return JSON.stringify(adapters.parseGoldfish(text));
  }
  return text;
}
function preparationStatus(title,message){
  const main=$('#main');
  main.replaceChildren();
  const panel=document.createElement('section');panel.className='empty-state';panel.setAttribute('role','status');
  const heading=document.createElement('h1');heading.textContent=title;
  const detail=document.createElement('p');detail.textContent=message;
  panel.append(heading,detail);main.append(panel);
  return detail;
}
function preparationComplete(deck){
  if(state.route!=='deck'||state.activeDeck?.id!==deck.id||$('.modal')||state.dirty||document.activeElement?.matches('input,textarea,[contenteditable=true]')){
    const notice=document.createElement('div');notice.className='toast';notice.setAttribute('role','status');
    const message=document.createElement('span');message.textContent=deck.name+' is ready to review and print.';
    const view=document.createElement('button');view.textContent='View deck';view.onclick=()=>{notice.remove();nav('deck/'+deck.id+'/cards');};
    const dismiss=document.createElement('button');dismiss.textContent='×';dismiss.setAttribute('aria-label','Dismiss deck ready notification');dismiss.onclick=()=>notice.remove();
    notice.append(message,view,dismiss);$('#toast-host').append(notice);return;
  }
  const host=modal('Your deck is ready','',{size:'small',footer:'<button class="button primary" id="view-ready-deck">View deck</button>',
    onClose:()=>true});
  const body=$('.modal-body',host);
  const message=document.createElement('p');message.textContent=`All images for ${deck.name} are finished. Your deck is ready to review and print.`;body.append(message);
  $('#view-ready-deck').onclick=()=>{closeModal();nav('deck/'+deck.id+'/cards');};
}
function chooseLook(manifest,includeOutside=true){
  let choosing=false;
  const host=modal('Choose Look','',{size:'large'});
  const body=$('.modal-body',host);
  const choices=document.createElement('div');choices.style.display='grid';choices.style.gridTemplateColumns='repeat(auto-fit,minmax(220px,1fr))';choices.style.gap='16px';choices.style.marginTop='20px';body.append(choices);
  const looks=[
    ['normal','Normal Look','Use the card’s normal MTG artwork and frames.','/site/command_tower.png'],
    ['custom','Customize Look','Choose artwork, frames, set symbols, card backs, and more.','/site/command_tower_custom.png']
  ];
  for(const [value,title,description,imageUrl] of looks){
    const option=document.createElement('button');option.type='button';option.className='choice';option.setAttribute('aria-label',title);
    option.style.alignItems='center';option.style.textAlign='center';option.style.whiteSpace='normal';option.style.padding='20px';
    const image=document.createElement('img');image.src=imageUrl;image.alt=`Command Tower example for ${title}`;image.style.width='min(100%, 220px)';image.style.aspectRatio='5 / 7';image.style.objectFit='contain';
    const heading=document.createElement('b');heading.textContent=title;heading.style.fontSize='16px';
    const detail=document.createElement('span');detail.textContent=description;detail.style.fontSize='12px';
    option.append(image,heading,detail);choices.append(option);
    option.onclick=async()=>{
      if(choosing)return;
      choosing=true;
      closeModal();
      const status=preparationStatus('Opening your deck',
        value==='normal'?'We’re preparing your deck, then generating its images with the normal artwork and frames. We’ll tell you when it’s ready.':'Opening Art & Setup. Card details will load in the background while you choose your options.');
      const epoch=state.routeEpoch;
      let deck=null;
      try{
        deck=await job('/api/decks/import',{manifest,includeOutside,settings:value==='normal'?{source:{mode:'scryfall',fallback:false},artist:'',symbols:{},backAsset:null,backDesign:{mode:'default'},cardData:[],dataJsonSource:null,disableAutofit:false,flavorPolicy:'auto',showFlavorText:true,acceptCropWarnings:false,acceptLayoutWarnings:false,allCardsTokens:false,tokenOptions:{},templateRules:Object.fromEntries(['standard','legendary','land','legendary-land','basic-land'].map(group=>[group,'normal']))}:{}},{label:'Import deck'});
        if(epoch===state.routeEpoch)nav('deck/'+deck.id+(value==='normal'?'/cards':'/setup'));
        else toast(deck.name+' was imported. Open it from Deck Library when you’re ready.');
        if(value==='normal')await generate(deck);
      }catch(error){
        if(epoch!==state.routeEpoch){toast(error.message,true);return;}
        status.textContent='We could not finish preparing this deck.';
        const notice=document.createElement('div');notice.className='notice error';notice.setAttribute('role','alert');notice.textContent=error.message;status.after(notice);
        const next=document.createElement('button');next.type='button';next.className='button primary';
        next.textContent=deck?'Open deck':'Try another deck';
        next.onclick=()=>deck?nav('deck/'+deck.id+'/cards'):addNewDeck();
        notice.after(next);
      }
    };
  }
}
function addNewDeck(){
  const host=modal('Add New Deck','',{footer:'<button class="button primary" id="do-import" disabled>Add deck</button>'});
  const body=$('.modal-body',host),addButton=$('#do-import');
  const intro=document.createElement('p');intro.className='muted';intro.textContent="Give us your deck link from a website like Scryfall, MTGGoldfish, or Archidekt, and we'll get the full deck for you.";body.append(intro);
  const linkField=document.createElement('div');linkField.className='field';
  const link=document.createElement('input');link.type='url';link.placeholder='https://scryfall.com/@you/decks/…';link.autocomplete='url';link.setAttribute('aria-label','Deck link');
  linkField.append(link);body.append(linkField);
  const helperNotice=document.createElement('div');helperNotice.className='notice info hidden';
  const helperText=document.createElement('p');helperText.textContent='This deck site needs the browser helper to import its link on your computer.';
  const helperButton=document.createElement('button');helperButton.type='button';helperButton.className='button small';helperButton.textContent='Set up browser helper';helperButton.style.marginTop='10px';
  helperButton.onclick=()=>setupHelper();helperNotice.append(helperText,helperButton);body.append(helperNotice);
  const advanced=document.createElement('details');advanced.style.marginTop='22px';
  const summary=document.createElement('summary');summary.textContent='Other import methods';advanced.append(summary);
  const textLabel=document.createElement('label');textLabel.className='field';
  const textTitle=document.createElement('span');textTitle.textContent='Card list or JSON export';
  const sourceText=document.createElement('textarea');sourceText.rows=5;sourceText.placeholder='1 Sol Ring\n12 Forest';
  textLabel.append(textTitle,sourceText);advanced.append(textLabel);
  const fileLabel=document.createElement('label');fileLabel.className='field';
  const fileTitle=document.createElement('span');fileTitle.textContent='Upload JSON or text file';
  const file=document.createElement('input');file.type='file';file.accept='.json,.txt';
  fileLabel.append(fileTitle,file);advanced.append(fileLabel);
  const outsideLabel=document.createElement('label');outsideLabel.className='check-line';
  const outside=document.createElement('input');outside.type='checkbox';outside.checked=true;outside.id='import-outside';
  const outsideText=document.createElement('span');outsideText.textContent='Include Outside the Game cards';
  outsideLabel.append(outside,outsideText);advanced.append(outsideLabel);body.append(advanced);
  const updateButton=()=>{addButton.disabled=!(link.value.trim()||sourceText.value.trim());addButton.style.filter=addButton.disabled?'grayscale(1)':'';helperNotice.classList.add('hidden');};
  link.oninput=()=>{sourceText.value='';file.value='';updateButton();};
  sourceText.oninput=()=>{link.value='';file.value='';updateButton();};
  file.onchange=()=>attempt(async()=>{if(!file.files[0])return;if(file.files[0].size>20*1024**2)throw new Error('Choose a deck export under 20 MB.');sourceText.value=await file.files[0].text();link.value='';updateButton();});
  addButton.onclick=async()=>{
    let source=link.value.trim()||sourceText.value.trim();
    if(link.value.trim()&&!/^https:\/\/(?:www\.)?(?:scryfall\.com\/@[^/]+\/decks\/|archidekt\.com\/decks\/|mtggoldfish\.com\/deck\/)/i.test(source)){
      errorBox(body,'Use a public Scryfall, Archidekt, or MTGGoldfish deck link.');return;
    }
    if(/^https:\/\/(?:www\.)?(?:archidekt\.com\/decks\/|mtggoldfish\.com\/deck\/)/i.test(source)&&!state.helperCapabilities?.includes('deck-import')){
      helperNotice.classList.remove('hidden');return;
    }
    if(source.startsWith('{')){
      try{JSON.parse(source);}catch{errorBox(body,'The JSON export is not valid.');return;}
    }
    const includeOutside=outside.checked;addButton.disabled=true;addButton.textContent='Reading deck list…';
    try{
      const prepared=await prepareDeckSource(source);
      const manifest=await job('/api/decks/manifest',{source:prepared,includeOutside},{label:'Read deck list'});
      if(!host.isConnected)return;
      closeModal();chooseLook(manifest,includeOutside);
    }catch(error){if(host.isConnected)errorBox(body,error.message);}
    finally{addButton.textContent='Add deck';if(addButton.isConnected)updateButton();}
  };
  updateButton();
}
export async function importDeck(existing=null){
  if(!existing)return addNewDeck();
  requireDeckAvailable(existing.id);
  const host=modal(existing?'Add cards to '+existing.name:'Bring your next deck to the table',`<span class="eyebrow">START WITH THE CARDS YOU ALREADY CHOSE</span><p class="muted" style="margin-bottom:22px">Paste a public Scryfall deck link, a card list, or upload the deck’s JSON export. Exact printing identifiers keep your chosen artwork intact.</p>${existing?'':`<label class="field"><span>Deck name <small>optional</small></span><input id="import-name" placeholder="Use the name from Scryfall" maxlength="200"></label>`}<label class="field"><span>${existing?'Cards to add':'Deck link or decklist'}</span><textarea id="import-source" rows="7" placeholder="https://scryfall.com/@you/decks/…&#10;&#10;or&#10;1 Sol Ring (CMM) 396&#10;12 Forest"></textarea></label><label class="field"><span>Or upload a deck export</span><input type="file" id="import-file" accept=".json,.txt"><small>JSON is best for keeping each selected printing. Plain names use Scryfall’s named-card result; you can change the printing afterward.</small></label><label class="check-line"><input type="checkbox" id="import-outside" checked><span>Include “Outside the Game” cards<small>Sideboard and maybeboard remain excluded, matching Card Tools.</small></span></label>${existing?'':`<div class="notice info">Next: choose artwork, reuse or customize templates, add four rarity symbols and a deck back. You can use existing templates or create/upload your own.</div>`}`,{footer:`<span class="footer-hint">Nothing is sent to a printer during import.</span><button class="button primary" id="do-import">${existing?'Add cards':'Import deck →'}</button>`});
  $('#import-file').onchange=()=>attempt(async()=>{const f=$('#import-file').files[0];if(!f)return;if(f.size>20*1024**2)throw new Error('Choose a deck export under 20 MB.');$('#import-source').value=await f.text();});
  $('#do-import').onclick=async()=>{
    let source=$('#import-source').value.trim();if(!source){errorBox($('.modal-body',host),'Paste a deck link or card list first.');return;}
    $('#do-import').disabled=true;
    try{
      source=await prepareDeckSource(source);
      const payload={source,includeOutside:$('#import-outside').checked,...(existing?{revision:existing.revision}:{name:$('#import-name').value.trim()})};
      closeModal();
      const d=await job(existing?'/api/decks/'+existing.id+'/add':'/api/decks/import',payload,{label:existing?'Add cards':'Import deck'});
      state.dirty=false;
      if(existing){await showDeck(d.id,'cards');toast('Cards added. Generate images to prepare the new entries.');}
      else nav('deck/'+d.id+'/setup');
    }catch(e){if($('#do-import')){$('#do-import').disabled=false;errorBox($('.modal-body',host),e.message);}else toast(e.message,true);}
  };
}
function preview(c,f){
  if(c.metadataSource&&!f.compiled&&!f.lastRender)return '';
  return f.compiled?.render?.url||f.lastRender?.render?.url||(f.compiled?.artId?asset(f.compiled.artId):null)||f.selectedArtUrl||(c.scryfall.card_faces?.[f.index]?.image_uris?.art_crop)||c.scryfall.image_uris?.art_crop||'';
}
function backPreview(c,d){
  if(c.backOverride)return asset(c.backOverride);
  if(c.meldBackAsset)return asset(c.meldBackAsset);
  if(c.faces.length===2)return preview(c,c.faces[1]);
  return asset(d.settings.backAsset);
}
const hasPhysicalReverse=c=>c.faces.length===2||Boolean(c.meldBackAsset||c.scryfall?._meld_result);
const physicalReverseName=c=>c.faces.length===2?c.faces[1].name:(c.scryfall?._meld_result?.name||'Meld reverse');

export async function showDeck(id,tab='cards'){
  const epoch=state.routeEpoch;
  if(tab==='review')tab='cards';
  const oldScroll=$('.card-grid')?.scrollTop||0;
  let d=await api('/api/decks/'+id);if(epoch!==state.routeEpoch)return;activeCardsView=null;state.activeDeck=d;state.deckTab=tab;
  let v=views.get(id);if(!v){v={query:'',filter:'all'};views.set(id,v);}
  let summary=d.summary,dirty=d.status==='draft';
  $('#main').innerHTML=`<a class="back-to-library" href="#decks">← All decks</a><div class="page-head"><div><span class="eyebrow">DECK STUDIO</span><h1>${esc(d.name)}</h1><div class="actions" style="margin-top:12px">${badge(d.status)}<span class="count-label">${summary.cards} cards · ${summary.faces} faces · ${summary.rendered} rendered</span></div><div class="deck-progress"><span class="complete"><b>✓</b>Import</span><span class="${dirty?'current':'complete'}"><b>${dirty?'2':'✓'}</b>Art & style</span><span class="${d.status==='ready'?'complete':!dirty?'current':''}"><b>${d.status==='ready'?'✓':'3'}</b>Generate images</span><span><b>4</b>Review & print</span></div></div><div class="actions"><button class="button" id="deck-menu">More ▾</button><button class="button" id="add-cards">＋ Add cards</button><button class="button primary" id="generate-deck">Generate images</button></div></div>
    <div class="tabs"><button data-tab="cards" class="${tab==='cards'?'active':''}">Cards <span>${summary.cards}</span></button><button data-tab="setup" class="${tab==='setup'?'active':''}">Art & setup</button><button data-tab="review" class="${tab==='review'?'active':''}">Review <span>${summary.warnings+summary.errors||''}</span></button></div>${d.upgradeRequired?`<div class="notice info">This deck was prepared with an older render pipeline. Generate images will force a fresh render of every face. Running pipeline: ${esc(state.bootstrap.pipelineVersion||'unknown')}.</div>`:''}<div id="deck-body"></div>`;
  $$('[data-tab]').forEach(b=>b.onclick=()=>nav('deck/'+id+'/'+b.dataset.tab));
  $('.back-to-library')?.remove();
  const deckTitle=$('.page-head h1');
  deckTitle.title='Click to rename deck';deckTitle.tabIndex=0;deckTitle.style.cursor='text';
  deckTitle.onclick=()=>{
    const input=document.createElement('input');input.type='text';input.maxLength=200;input.value=d.name;
    input.style.cssText='font:inherit;max-width:100%;min-width:300px';deckTitle.replaceWith(input);input.focus();input.select();
    let done=false;
    const finish=async(save)=>{if(done)return;done=true;
      if(save&&input.value.trim()&&input.value.trim()!==d.name){
        try{await api('/api/decks/'+id+'/save',{revision:d.revision,name:input.value.trim()});await showDeck(id,tab);}
        catch(error){toast(error.message,true);await showDeck(id,tab);}
      }else await showDeck(id,tab);
    };
    input.onkeydown=event=>{if(event.key==='Enter')finish(true);if(event.key==='Escape')finish(false);};
    input.onblur=()=>finish(true);
  };
  deckTitle.onkeydown=event=>{if(event.key==='Enter')deckTitle.click();};
  $('.page-head .eyebrow')?.remove();
  $('#add-cards')?.remove();
  $('[data-tab="review"]')?.remove();
  const reviewButton=document.createElement('button');reviewButton.className='button';reviewButton.textContent='Review & Print';
  reviewButton.onclick=()=>attempt(()=>chooseOrder([id]));$('#generate-deck').before(reviewButton);
  $('#generate-deck').onclick=()=>attempt(()=>generate(d));
  $('#deck-menu').onclick=()=>deckMenu(d);
  if(tab==='setup'){
    const setup=renderSetup($('#deck-body'),d,async(updated,generateNow)=>{
      if(generateNow){history.replaceState(null,'','#deck/'+id);await showDeck(id,'cards');await generate(updated,true);}
      else await showDeck(id,'setup');
    });$('#generate-deck').onclick=()=>attempt(setup.generate);
    if(d.pendingImport)void startMetadata(d).catch(error=>console.info('Card details task stopped',error.message));
    return;
  }
  if(tab==='review'){
    const issues=d.cards.flatMap(c=>c.faces.flatMap(f=>{
      const out=[];if(f.error)out.push({c,f,error:true,text:f.error});
      if(f.compiled?.crop?.warning){const crop=f.compiled.crop;out.push({c,f,text:`Artwork cropped: ${(crop.cropX*100).toFixed(1)}% of width, ${(crop.cropY*100).toFixed(1)}% of height. More than 20% is outside the selected art window.`});}
      if(f.compiled?.flags?.length)out.push({c,f,text:'Card Tools requests layout review: '+JSON.stringify(f.compiled.flags)});
      return out;
    }));
    $('#deck-body').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>Check before you print</h2><p>Crop warnings are not automatically “fixed.” You choose whether to use different art, change the template, or accept the crop.</p></div><button class="button primary" id="review-order">Review print order →</button></div>${dirty?'<div class="notice">This deck has unprepared changes. Generate images to get current warnings and previews.</div>':''}${issues.length?issues.map((x,i)=>`<div class="notice ${x.error?'error':''}"><b>${esc(x.f.name)}</b>\n${esc(x.text)}<div style="margin-top:8px"><button class="button small" data-issue="${i}">Open card</button></div></div>`).join(''):'<div class="notice success">No current layout or crop warnings. Still review both sides in the final order preview.</div>'}</section>`;
    $$('[data-issue]').forEach(b=>b.onclick=()=>attempt(()=>inspect(d,issues[+b.dataset.issue].c,issues[+b.dataset.issue].f.index||0)));
    $('#review-order').onclick=()=>attempt(()=>chooseOrder([id]));return;
  }
  function cardsGrid(){
    const cards=d.cards;
    $('#deck-body').innerHTML=`${dirty?'<div class="notice info">You have saved changes to prepare. Generate images will rebuild only the affected faces and reuse unchanged PNGs.</div>':''}<div class="toolbar"><div class="filter-pills"><button data-card-filter="all" class="${v.filter==='all'?'active':''}">All cards</button><button data-card-filter="unrendered" class="${v.filter==='unrendered'?'active':''}">Not rendered</button><button data-card-filter="attention" class="${v.filter==='attention'?'active':''}">Needs review</button></div><label class="search"><input id="card-search" type="search" aria-label="Find a card" placeholder="Find a card…" value="${esc(v.query)}"></label><button class="button small" id="quick-order">Review order ↗</button></div>${cards.length?`<div class="card-grid">${cards.map(c=>{
      const f=c.faces[0],front=thumbnail(preview(c,f)),back=thumbnail(backPreview(c,d)),done=!!f.compiled?.render;
    const warning=c.faces.some(x=>x.error||(((x.compiled?.crop?.warning||x.compiled?.flags?.length)&&x.acceptedWarningKey!==x.compiled?.renderKey)));
    return `<article class="card-item"><button class="card-image" data-card="${c.id}" aria-label="Edit ${esc(c.name)}"><span class="quantity-pill">${c.quantity}×</span><span class="card-name-pill" title="${esc(c.name)}">${esc(c.name)}</span>${warning?'<span class="warn-pill">!</span>':''}${front?`<img src="${esc(front)}" data-hover-front="${esc(front)}" ${back?`data-hover-back="${esc(back)}"`:''} class="${done||f.lastRender?.render?.url?'':'art-only'}" loading="lazy" alt="${esc(c.name)}">`:'<span class="card-empty-symbol">▱</span>'}${!done?`<span class="image-label">${f.error?'Needs attention':f.lastRender?.render?.url?'Previous render · changes pending':'Art preview · not rendered'}</span>`:dirty?'<span class="image-label">Previous render · changes pending</span>':''}</button></article>`;
    }).join('')}</div>`:empty(d.cards.length?'No cards match':'This deck is waiting for cards',d.cards.length?'Try a different search or review filter.':'Add a card list or a Scryfall export to get started.',`<button class="button primary" id="empty-add">＋ Add cards</button>`)}<div class="subtitle-line">Hover a card to see its back. Click it to edit its artist, art, printing, quantity or template. Real double-faced cards hover to their actual reverse face.</div>`;
    $$('[data-card]').forEach(b=>b.onclick=()=>attempt(()=>inspect(d,d.cards.find(c=>c.id===b.dataset.card),0)));
    $$('[data-hover-front]').forEach(img=>{const card=img.closest('[data-card]');if(!card)return;card.onmouseenter=()=>{img.src=img.dataset.hoverBack||img.dataset.hoverFront;};card.onmouseleave=()=>{img.src=img.dataset.hoverFront;};});
    $$('[data-card-filter]').forEach(b=>b.onclick=()=>{v.filter=b.dataset.cardFilter;filterCards();});
    const attention=$('[data-card-filter="attention"]');
    if(attention)attention.textContent=`Needs Review${summary.warnings+summary.errors?` · ${summary.warnings+summary.errors}`:''}`;
    $('.card-grid')?.style.setProperty('max-height','none');
    $('.card-grid')?.style.setProperty('overflow','visible');
    $('#quick-order')?.remove();
    $('.subtitle-line', $('#deck-body'))?.remove();
    $('#card-search').oninput=e=>{v.query=e.target.value;filterCards();};
    if($('#empty-add'))$('#empty-add').onclick=()=>attempt(()=>importDeck(d));
  }
  const body=$('#deck-body');
  function filterCards(){
    const query=v.query.toLowerCase(),cards=new Map(d.cards.map(card=>[card.id,card]));
    let visible=0;
    for(const button of $$('[data-card]',body)){
      const card=cards.get(button.dataset.card);
      const matches=card&&card.name.toLowerCase().includes(query)
        &&(v.filter!=='unrendered'||card.faces.some(face=>!face.compiled?.render))
        &&(v.filter!=='attention'||card.faces.some(face=>face.error||((face.compiled?.crop?.warning||face.compiled?.flags?.length)&&face.acceptedWarningKey!==face.compiled?.renderKey)));
      button.closest('.card-item').hidden=!matches;
      if(matches)visible++;
    }
    for(const button of $$('[data-card-filter]',body)){
      button.classList.toggle('active',button.dataset.cardFilter===v.filter);
    }
    let empty=body.querySelector('[data-no-card-matches]');
    if(!empty&&d.cards.length){
      empty=document.createElement('div');empty.className='empty-state';empty.dataset.noCardMatches='';
      const heading=document.createElement('h2');heading.textContent='No cards match';
      const detail=document.createElement('p');detail.textContent='Try a different search or review filter.';
      empty.append(heading,detail);body.append(empty);
    }
    if(empty)empty.hidden=visible>0;
  }
  const refresh=updated=>{
    if(!body.isConnected||epoch!==state.routeEpoch||state.dirty)return;
    d=updated;state.activeDeck=d;summary=d.summary;dirty=d.status==='draft';
    const count=$('.count-label');if(count)count.textContent=`${summary.cards} cards · ${summary.faces} faces · ${summary.rendered} rendered`;
    const badge=$('.page-head .badge');if(badge){badge.className='badge '+d.status;badge.textContent=humanStatus(d.status);}
    const attention=$('[data-card-filter="attention"]',body);if(attention)attention.textContent=`Needs Review${summary.warnings+summary.errors?` · ${summary.warnings+summary.errors}`:''}`;
    const steps=$$('.deck-progress>span');
    if(steps[1])steps[1].className=dirty?'current':'complete';
    if(steps[2])steps[2].className=d.status==='ready'?'complete':!dirty?'current':'';
    if(steps[1]?.firstElementChild)steps[1].firstElementChild.textContent=dirty?'2':'✓';
    if(steps[2]?.firstElementChild)steps[2].firstElementChild.textContent=d.status==='ready'?'✓':'3';
    if(!dirty)body.querySelector(':scope>.notice.info')?.remove();
    const cards=new Map(d.cards.map(card=>[card.id,card]));
    for(const button of $$('[data-card]',body)){
      const card=cards.get(button.dataset.card);if(!card)continue;
      const face=card.faces[0],front=thumbnail(preview(card,face)),back=thumbnail(backPreview(card,d)),done=!!face.compiled?.render;
      let image=$('img',button);
      if(front&&!image){
        image=document.createElement('img');image.loading='lazy';image.alt=card.name;
        $('.card-empty-symbol',button)?.remove();button.append(image);
        button.onmouseenter=()=>{image.src=image.dataset.hoverBack||image.dataset.hoverFront;};
        button.onmouseleave=()=>{image.src=image.dataset.hoverFront;};
      }
      if(image){
        const previous=image.dataset.hoverFront;
        image.dataset.hoverFront=front;image.dataset.hoverBack=back||'';
        if(previous!==front||!image.getAttribute('src'))image.src=front;
        image.classList.toggle('art-only',!done&&!face.lastRender?.render?.url);
      }
      let label=$('.image-label',button);
      if(!label&&(!done||dirty)){label=document.createElement('span');label.className='image-label';button.append(label);}
      if(label){label.hidden=done&&!dirty;label.textContent=face.error?'Needs attention':face.lastRender?.render?.url||done?'Previous render · changes pending':'Art preview · not rendered';}
      const warning=card.faces.some(face=>face.error||((face.compiled?.crop?.warning||face.compiled?.flags?.length)&&face.acceptedWarningKey!==face.compiled?.renderKey));
      let mark=$('.warn-pill',button);
      if(warning&&!mark){mark=document.createElement('span');mark.className='warn-pill';mark.textContent='!';button.append(mark);}
      if(mark)mark.hidden=!warning;
    }
    filterCards();
  };
  activeCardsView={id,refresh};
  state.generationView={route:'deck',id,refresh:()=>refreshDeckProgress(id)};
  cardsGrid();filterCards();if($('.card-grid'))$('.card-grid').scrollTop=oldScroll;
  if(d.pendingImport)void startMetadata(d).catch(error=>console.info('Card details task stopped',error.message));
}
export async function refreshDeckProgress(id){
  if(state.route!=='deck'||state.activeDeck?.id!==id||state.deckTab!=='cards'||state.dirty)return;
  const view=activeCardsView,epoch=state.routeEpoch;
  if(view?.id!==id)return;
  const updated=await api('/api/decks/'+id);
  if(epoch===state.routeEpoch&&activeCardsView===view)view.refresh(updated);
}
async function generate(d,artChecked=false){
  if(state.setupActions?.root.isConnected&&state.setupActions.deckId===d.id)return state.setupActions.generate();
  d=await ensureMetadata(d.id);
  if(!rarities.every(r=>d.settings.symbols?.[r])){nav('deck/'+d.id+'/setup');throw new Error('Set up your four rarity symbols first.');}
  if(!artChecked&&!await ensureArtworkReady(d.id))return;
  d=await api('/api/decks/'+d.id);
  d=await ensureCustomArtCredits(d);if(!d)return;
  await renderDecks([d.id],{notify:false,artChecked:true});
  const finished=await api('/api/decks/'+d.id);
  if(state.route==='deck'&&state.activeDeck?.id===d.id&&state.deckTab==='setup'&&!state.dirty&&!$('.modal'))await showDeck(d.id,'setup');
  if(finished.status==='ready')preparationComplete(finished);
}
function deckMenu(d){
  const permanent=true;
  modal('Deck actions',`<div class="stack"><button class="button" id="duplicate-deck">Duplicate deck</button><button class="button" id="deck-image-zip">Download paired images ZIP</button><button class="button" id="download-cc">Export CardConjurer save</button><button class="button" id="download-originals">Download original printing images</button><button class="button" id="download-cropped-art">Download Cropped Art</button><button class="button" id="download-review-images">Download review Images</button><button class="button" id="use-as-defaults">Use this deck’s style as my default</button><button class="button danger" id="trash-deck">${permanent?'Delete deck permanently':'Move deck to Trash'}</button></div><p class="muted" style="margin-top:16px;font-size:12px">${permanent?'Permanent deletion cannot be undone. Shared artwork and render caches are retained.':'Exports use prepared card data. Review images place the selected Scryfall printing beside your rendered card with a 1 px gap. Only actual double-faced reverse faces are included.'}</p>`,{size:'small'});
  const add=document.createElement('button');add.className='button';add.textContent='＋ Add Cards';add.onclick=()=>attempt(()=>importDeck(d));
  $('.stack',$('#modal-host')).prepend(add);
  const saveStyle=$('#use-as-defaults');saveStyle.textContent='Create reusable style';
  saveStyle.onclick=()=>{
    const host=modal('Create reusable style','',{footer:'<button class="button primary" id="save-style-preset">Create style</button>'});
    const label=document.createElement('label');label.className='field';
    const title=document.createElement('span');title.textContent='Style name';
    const input=document.createElement('input');input.maxLength=200;input.placeholder='My deck style';
    label.append(title,input);$('.modal-body',host).append(label);input.focus();
    $('#save-style-preset').onclick=()=>attempt(async()=>{
      const name=input.value.trim();if(!name){errorBox($('.modal-body',host),'Name this style first.');return;}
      await api('/api/style-presets/from-deck',{deckId:d.id,name});closeModal();toast('Style saved. Manage it in Settings.');
    });
  };
  $('.modal-body p.muted')?.remove();
  $('#duplicate-deck').onclick=()=>attempt(async()=>{const copy=await api('/api/decks/'+d.id+'/duplicate',{});closeModal();nav('deck/'+copy.id);});
  $('#deck-image-zip').onclick=()=>attempt(async()=>{closeModal();await chooseOrder([d.id]);});
  $('#download-cc').onclick=()=>attempt(()=>downloadPost('/api/cardconjurer/export',{deckIds:[d.id]},d.name+'.cardconjurer'));
  $('#download-originals').onclick=()=>attempt(async()=>{closeModal();const out=await job('/api/decks/'+d.id+'/originals',{}, {label:'Original printing images'});if(state.bootstrap?.browser)await saveApiFile(out.download,out.filename||'BulkProxyForge_Originals.zip',out.bytes);else location.href=out.download;});
  $('#download-cropped-art').onclick=()=>attempt(async()=>{closeModal();const out=await job('/api/decks/'+d.id+'/cropped-art',{}, {label:'Cropped art'});if(state.bootstrap?.browser)await saveApiFile(out.download,out.filename||'BulkProxyForge_Cropped_Art.zip',out.bytes);else location.href=out.download;});
  $('#download-review-images').onclick=()=>attempt(async()=>{
    closeModal();
    let current=await api('/api/decks/'+d.id);
    const needsGeneration=!!current.upgradeRequired||current.status==='draft'||Number(current.summary?.rendered||0)<Number(current.summary?.faces||0);
    if(needsGeneration)throw new Error('Generate images before downloading review images.');
    const out=await job('/api/decks/'+d.id+'/review-images',{}, {label:'Review images'});
    if(state.bootstrap?.browser)await saveApiFile(out.download,out.filename||'BulkProxyForge_Review_Images.zip',out.bytes);else location.href=out.download;
  });
  $('#trash-deck').onclick=()=>{if(state.bootstrap?.browser)return attempt(()=>deleteDeck(d));return attempt(async()=>{closeModal();const title=permanent?'Delete this deck permanently?':'Move this deck to Trash?',detail=permanent?d.name+' will be deleted immediately and cannot be restored. Shared artwork and render caches are kept.':d.name+' and its saved setup can be restored later.',label=permanent?'Delete permanently':'Move to Trash';if(!await confirmAction(title,detail,label,true))return;await api('/api/decks/'+d.id+'/delete',{revision:d.revision});state.selected.delete(d.id);nav('decks');toast(permanent?'Deck permanently deleted.':'Deck moved to Trash.');});};
}
async function inspectMeldReverse(deck,card){
  let d=await api('/api/decks/'+deck.id);let c=d.cards.find(x=>x.id===card.id);if(!c)throw new Error('This card was removed in another tab.');
  if(!c.scryfall?._meld_result){closeModal();return inspect(d,c,0);}
  let backOverride=c.backOverride,backDesignOverride=c.backDesignOverride||null;
  const result=c.scryfall._meld_result,src=backPreview(c,d),name=physicalReverseName(c);
  modal(name,`<div class="inspector"><div class="inspector-preview">${src?`<img src="${esc(src)}" id="inspector-image" alt="${esc(name)}">`:'<div class="card-image">Generate this card to build the physical meld reverse preview.</div>'}<button class="button quiet wide" id="inspect-flip">Edit front face ↻</button><div class="subtitle-line">Physical meld reverse</div></div><div><h3>Card details</h3><div class="notice info">This is this card’s printed half of <b>${esc(result.name||'the meld result')}</b>. It is paired with the other meld card. A custom back override replaces only this physical card’s reverse; it does not change the other meld half.</div><div class="field"><span>Back override <small>optional, applies to this card only</small></span><div class="actions"><button class="button small" id="face-back">Upload full back</button><button class="button small" id="face-back-designer">Default / icon back</button><button class="button quiet small" id="clear-face-back">Use actual meld reverse</button></div><small id="face-back-state">${backOverride?'Individual back selected':c.meldBackAsset?'Using actual meld reverse':'Generate this card to create the actual meld reverse'}</small><div id="face-back-picker" class="hidden"></div></div></div></div>`,{size:'large',footer:`<span class="footer-hint">The meld reverse is a physical back, not a separately generated CardConjurer face.</span><button class="button quiet" id="cancel-card">Cancel</button><button class="button primary" id="save-card">Done</button>`});
  const setBackState=text=>{const el=$('#face-back-state');if(el)el.textContent=text;};
  $('#cancel-card').onclick=closeModal;
  $('#inspect-flip').onclick=()=>{closeModal();attempt(()=>inspect(d,c,0));};
  $('#face-back').onclick=()=>attempt(async()=>{const file=await pickFile();if(!file)return;backOverride=(await uploadImage(file,{back:true})).id;backDesignOverride={mode:'custom'};$('#face-back-picker').classList.add('hidden');setBackState('Custom back: '+file.name);if($('#inspector-image'))$('#inspector-image').src=asset(backOverride);});
  $('#clear-face-back').onclick=()=>{backOverride=null;backDesignOverride=null;$('#face-back-picker').classList.add('hidden');setBackState(c.meldBackAsset?'Actual meld reverse will be used':'Generate this card to create the actual meld reverse');if($('#inspector-image')&&c.meldBackAsset)$('#inspector-image').src=asset(c.meldBackAsset);};
  $('#face-back-designer').onclick=()=>{
    const target=$('#face-back-picker');target.classList.remove('hidden');
    mountBackPicker(target,{backAsset:backOverride||null,backDesign:backDesignOverride},choice=>{
      backOverride=choice.backAsset;backDesignOverride=choice.backDesign;
      setBackState('Individual '+(choice.backDesign.mode==='icon'?'icon back':choice.backDesign.mode==='default'?'forge back':'custom back')+' selected; save to apply.');
      if($('#inspector-image')&&backOverride)$('#inspector-image').src=asset(backOverride);
    },{onBusy:busy=>$('#save-card').disabled=busy});
  };
  $('#save-card').onclick=()=>attempt(async()=>{
    $('#save-card').disabled=true;
    try{
      d=await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,backOverride:backOverride||null,backDesignOverride});
      closeModal();await showDeck(d.id,'cards');toast('Meld reverse saved.');
    }finally{if($('#save-card'))$('#save-card').disabled=false;}
  });
}

async function inspect(deck,card,index=0){
  let d=await api('/api/decks/'+deck.id);let c=d.cards.find(x=>x.id===card.id);if(!c)throw new Error('This card was removed in another tab.');
  let f=c.faces[index]||c.faces[0],fit={...(f.fit||{})},artOverride=f.artOverride,backOverride=c.backOverride,backDesignOverride=c.backDesignOverride||null;
  const comp=f.compiled,group=f.group||comp?.group||'standard',sfFace=c.scryfall.card_faces?.[f.index]||c.scryfall,legendary=String(sfFace.type_line||c.scryfall.type_line||'').includes('Legendary');
  const data=comp?.data||{};
  const typeLine=String(sfFace.type_line||c.scryfall.type_line||'');
  const faceColors=Array.isArray(sfFace.colors)?sfFace.colors:(Array.isArray(c.scryfall.colors)?c.scryfall.colors:[]);
  const colorlessCreature=/\bCreature\b/.test(typeLine)&&faceColors.length===0;
  const fiveSevenArt=['land','legendary-land','basic-land','planeswalker','station'].includes(group)||colorlessCreature;
  const artShapeHint=fiveSevenArt?'<small>Recommended source shape: <b>5:7</b>.</small>':'';
  const renderNotice=()=>{
    const parts=[];
    if(f.error)parts.push(`<div class="notice error">${esc(f.error)}</div>`);
    return parts.join('');
  };
  const host=modal(f.name,`<div class="inspector"><div class="inspector-preview">${preview(c,f)?`<img src="${esc(preview(c,f))}" id="inspector-image" alt="${esc(f.name)}">`:'<div class="card-image">No artwork yet</div>'}${hasPhysicalReverse(c)?`<button class="button quiet wide" id="inspect-flip">Edit ${index===0?'reverse':'front'} face ↻</button>`:''}<div class="subtitle-line" id="inspector-status">${esc(comp?.render?'CardConjurer render':f.lastRender?.render?'Previous render; generate images to apply your changes.':'Artwork preview; generate this card for the full card image.')}</div><div id="inspector-notices">${renderNotice()}</div></div><div><h3>Card details</h3><div class="field-row"><label class="field"><span>Quantity</span><input id="card-qty" type="number" min="1" max="9999" step="1" value="${c.quantity}"></label><div class="field"><span>Artwork</span><button class="button" id="choose-printing">Select Art</button></div></div>${creditFields(d,c,f)}<label class="field"><span>Template for this face</span><select id="face-template"><option value="">Use deck rule</option>${templateOptions(group,legendary,f.templateOverride||'auto')}</select><small>Layout: ${esc(state.bootstrap.groups[group]||group)}. Incompatible choices are hidden.</small></label>
  <div class="field"><span>Custom artwork override</span><div class="actions"><button class="button small" id="face-art">Upload art</button><button class="button quiet small" id="clear-face-art">Use deck artwork source</button></div><small id="face-art-state">${artOverride?'Individual custom artwork selected':esc(comp?.artOrigin||'Using deck source')}</small>${artShapeHint}</div>
  <div class="field"><span>Back override <small>optional, applies to this card only</small></span><div class="actions"><button class="button small" id="face-back">Upload full back</button><button class="button small" id="face-back-designer">Default / icon back</button><button class="button quiet small" id="clear-face-back">${hasPhysicalReverse(c)?'Use actual reverse':'Use deck back'}</button></div><small id="face-back-state">${backOverride?'Individual back selected':hasPhysicalReverse(c)?'Paired with '+esc(physicalReverseName(c)):'Using deck default back'}</small><div id="face-back-picker" class="hidden"></div></div>
  <details><summary>Artwork positioning & text overrides</summary><p class="muted" style="font-size:11px;margin-bottom:13px">The default is Card Tools’ existing fit. Changing these values affects only this face.</p><div class="field-row"><label class="field"><span>Horizontal position (pixels)</span><input id="fit-x" type="number" step="1" value="${Math.round((data.artX||0)*(data.width||2010))}"></label><label class="field"><span>Vertical position (pixels)</span><input id="fit-y" type="number" step="1" value="${Math.round((data.artY||0)*(data.height||2814))}"></label></div><div class="field-row"><label class="field"><span>Art scale (%)</span><input id="fit-zoom" type="number" min=".01" step=".1" value="${((data.artZoom||1)*100).toFixed(2)}"></label><label class="field"><span>Rotation (degrees)</span><input id="fit-rotation" type="number" step="1" value="${data.artRotate||0}"></label></div><button class="button quiet small" id="reset-fit">Reset to automatic fitting</button><label class="field section-gap"><span>Nickname / reskin name <small>optional</small></span><input id="nickname-override" value="${esc(f.semanticOverrides?.nickname??c.scryfall.flavor_name??'')}" placeholder="Use Scryfall flavor name, if any"><small>When nonblank, automatically uses the Godzilla-style alternate-name treatment while the real card name stays underneath.</small></label><label class="field"><span>Rules text override</span><textarea id="rules-override" rows="4" placeholder="Use current Scryfall Oracle text">${esc(f.semanticOverrides?.oracle_text??'')}</textarea><small>Leave blank to use the fetched Oracle text. The original Scryfall record remains cached unchanged.</small></label><label class="field"><span>Flavor text override</span><textarea id="flavor-override" rows="3" placeholder="Use the deck’s flavor policy">${esc(f.semanticOverrides?.flavor_text??'')}</textarea></label><label class="check-line"><input type="checkbox" id="remove-flavor" ${f.semanticOverrides?.flavor_text===''?'checked':''}><span>Remove flavor text from this face</span></label><label class="field"><span>Rarity / set-symbol override</span><select id="rarity-override"><option value="">Use selected printing (${esc(c.scryfall.rarity||'common')})</option>${rarities.map(r=>`<option value="${r}" ${f.semanticOverrides?.rarity===r?'selected':''}>${r}</option>`).join('')}</select></label></details><div class="inspector-actions"><button class="button danger-quiet small" id="remove-card">Remove card</button><button class="button quiet small" id="copy-token">Make copy token</button></div></div></div>`,{size:'large',footer:`<span class="footer-hint">Changes are saved to this deck only.</span><button class="button quiet" id="cancel-card">Cancel</button><button class="button quiet" id="download-review-image">Download review image</button><button class="button" id="generate-card">Generate this card</button><button class="button primary" id="save-card">Done</button>`});
  let selectedSide=index===1?'back':'front';
  const large=$('#inspector-image',host);
  let setSide=()=>{};
  if(large){
    const sideChoices=document.createElement('div');sideChoices.className='actions';sideChoices.style.cssText='justify-content:center;margin:10px 0';
    const sideButtons={};
    for(const [side,label] of [['front','Front'],['back','Back']]){
      const button=document.createElement('button');button.type='button';button.className='button quiet small';button.setAttribute('aria-label','Show '+label.toLowerCase()+' side');
      button.style.cssText='display:flex;flex-direction:column;align-items:center;gap:4px;padding:5px';
      const picture=document.createElement('img');picture.style.cssText='width:52px;height:73px;object-fit:contain';picture.alt='';
      button.append(picture,document.createTextNode(label));button.onclick=()=>setSide(side);
      sideButtons[side]={button,picture};sideChoices.append(button);
    }
    large.after(sideChoices);
    setSide=side=>{
      selectedSide=side;
      const front=preview(c,c.faces[0]),back=backPreview(c,d);
      sideButtons.front.picture.src=front||'';sideButtons.back.picture.src=back||'';
      large.src=(side==='back'?back:front)||'';large.alt=c.name+' '+side;
      for(const [key,item] of Object.entries(sideButtons)){
        item.button.classList.toggle('primary',side===key);
        item.button.style.borderColor=side===key?'#f28b32':'';
      }
    };
    setSide(selectedSide);
  }
  const quantityInput=$('#card-qty',host),quantityRow=document.createElement('div');quantityRow.className='actions';
  const decrease=document.createElement('button'),increase=document.createElement('button');
  decrease.type=increase.type='button';decrease.className=increase.className='button small';decrease.textContent='−';increase.textContent='+';
  decrease.setAttribute('aria-label','Decrease quantity');increase.setAttribute('aria-label','Increase quantity');
  quantityInput.style.width='68px';quantityInput.before(quantityRow);quantityRow.append(decrease,quantityInput,increase);
  const updateQuantity=()=>{decrease.disabled=Number(quantityInput.value)<=1;increase.disabled=Number(quantityInput.value)>=9999;};
  decrease.onclick=()=>{quantityInput.value=Math.max(1,Number(quantityInput.value||1)-1);updateQuantity();};
  increase.onclick=()=>{quantityInput.value=Math.min(9999,Number(quantityInput.value||1)+1);updateQuantity();};
  quantityInput.oninput=updateQuantity;updateQuantity();
  const templateSelect=$('#face-template',host);templateSelect.closest('label').remove();
  const templateLabel=document.createElement('label');templateLabel.className='field';
  const templateTitle=document.createElement('span');templateTitle.textContent='Template for this face';
  templateLabel.append(templateTitle,templateSelect);
  $('#fit-x',host).closest('details').append(templateLabel);
  const rulesPicker=document.createElement('button');rulesPicker.type='button';rulesPicker.id='select-rules-text';rulesPicker.className='button small';rulesPicker.textContent='Choose official rules text';
  $('#rules-override',host).before(rulesPicker);
  const flavorPicker=document.createElement('button');flavorPicker.type='button';flavorPicker.id='select-flavor-text';flavorPicker.className='button small';flavorPicker.textContent='Choose official flavor text';
  $('#flavor-override',host).before(flavorPicker);
  const creditControls=bindCreditFields(host,d,c,f,()=>artOverride,()=>f);
  $('#face-template').value=f.templateOverride||'';
  const syncCurrent=updated=>{d=updated;c=d.cards.find(x=>x.id===card.id);if(!c)throw new Error('This card was removed.');f=c.faces.find(x=>x.id===f.id)||c.faces[index]||c.faces[0];};
  const renderWarning=()=>{
    let panel=$('#inspector-warning',host);
    if(!panel){panel=document.createElement('div');panel.id='inspector-warning';panel.className='notice';panel.style.cssText='border:2px solid #ef8b29;margin-bottom:16px';$('.modal-body',host).prepend(panel);}
    panel.replaceChildren();
    const current=f.compiled||{};
    const crop=Boolean(current.crop?.warning),layout=Boolean(current.flags?.length);
    if(!current.render||(!crop&&!layout)||f.acceptedWarningKey===current.renderKey){panel.remove();return;}
    const title=document.createElement('strong');title.textContent=crop?'Part of this artwork is outside the frame and will not appear on the printed card. Does the art still look okay?':'This card layout needs a visual check. Does it look okay?';
    const actions=document.createElement('div');actions.className='actions';actions.style.marginTop='10px';
    const accept=document.createElement('button');accept.type='button';accept.className='button primary small';accept.textContent='It Looks Fine';
    accept.onclick=()=>attempt(async()=>{
      syncCurrent(await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,faceId:f.id,renderKey:current.renderKey,acceptWarning:true}));
      refreshInspector();await showDeck(d.id,'cards');toast('This rendered face is accepted for printing.');
    });
    const fix=document.createElement('button');fix.type='button';fix.className='button small';fix.textContent='Fix Art';
    fix.onclick=()=>{
      const details=$('#fit-x',host).closest('details');details.open=true;
      $('#face-art',host).scrollIntoView({block:'center'});$('#face-art',host).focus();
    };
    actions.append(accept,fix);panel.append(title,actions);
  };
  const refreshInspector=()=>{
    setSide(selectedSide);
    if($('#inspector-status'))$('#inspector-status').textContent=f.compiled?.render?'CardConjurer render':f.lastRender?.render?'Previous render; generate images to apply your changes.':'Artwork preview; generate this card for the full card image.';
    if($('#inspector-notices'))$('#inspector-notices').innerHTML=renderNotice();
    renderWarning();
  };
  renderWarning();
  const largeImage=$('#inspector-image',host);
  if(largeImage){largeImage.style.cursor='zoom-in';largeImage.onclick=()=>{
    const overlay=document.createElement('div');overlay.style.cssText='position:fixed;inset:0;z-index:10001;background:#0b0c0ef5;display:flex;align-items:center;justify-content:center;padding:12px;overflow:auto;touch-action:pan-x pan-y pinch-zoom';
    const image=document.createElement('img');image.src=largeImage.src;image.alt=largeImage.alt;image.style.cssText='max-width:100%;max-height:100%;object-fit:contain;touch-action:pan-x pan-y pinch-zoom';
    const close=document.createElement('button');close.type='button';close.className='button quiet icon';close.textContent='×';close.setAttribute('aria-label','Close enlarged card');close.style.cssText='position:fixed;right:18px;top:18px;z-index:1';close.onclick=()=>overlay.remove();
    overlay.onclick=event=>{if(event.target===overlay)overlay.remove();};overlay.append(image,close);document.body.append(overlay);
  };}
  const setBusy=busy=>['cancel-card','download-review-image','generate-card','save-card'].forEach(id=>{const el=$('#'+id);if(el)el.disabled=busy;});
  const cardRenderMatchesCache=card=>{
    const faces=card?.faces||[];
    return faces.length>0 && faces.every(face=>!face.error && face.compiled?.renderKey && face.compiled?.render);
  };
  const buildPatch=()=>{
    const credits=creditControls.values();
    const semantic={...f.semanticOverrides};const nickname=$('#nickname-override').value.trim();const sourceNickname=String(c.scryfall.flavor_name||'').trim();if(nickname&&nickname!==sourceNickname)semantic.nickname=nickname;else delete semantic.nickname;const rules=$('#rules-override').value;if(rules)semantic.oracle_text=rules;else delete semantic.oracle_text;
    if($('#remove-flavor').checked)semantic.flavor_text='';else if($('#flavor-override').value)semantic.flavor_text=$('#flavor-override').value;else delete semantic.flavor_text;
    if($('#rarity-override').value)semantic.rarity=$('#rarity-override').value;else delete semantic.rarity;
    const patch={revision:d.revision,quantity:$('#card-qty').value,backOverride:backOverride||null,backDesignOverride,faceId:f.id};
    const changes={...credits,artOverride:artOverride||null,templateOverride:$('#face-template').value||null,fit,semanticOverrides:semantic};
    for(const [k,value] of Object.entries(changes))if(JSON.stringify(value)!==JSON.stringify(f[k]??(['fit','semanticOverrides'].includes(k)?{}:null)))patch[k]=value;
    return patch;
  };
  const persistCard=async()=>{
    const patch=buildPatch();
    if(Object.keys(patch).length<=4)return d;
    syncCurrent(await api('/api/decks/'+d.id+'/cards/'+c.id,patch));
    refreshInspector();
    return d;
  };
  const prepareCard=async()=>{
    syncCurrent(await job('/api/decks/'+d.id+'/cards/'+c.id+'/prepare',{}, {label:'Prepare card'}));
    refreshInspector();
    return d;
  };
  const prepareIfNeeded=async()=>{
    if(d.status!=='draft')return d;
    return prepareCard();
  };
  $('#cancel-card').onclick=closeModal;
  $('#face-art').onclick=()=>attempt(async()=>{const file=await pickFile();if(!file)return;artOverride=(await uploadImage(file)).id;fit={};$('#face-art-state').textContent='Custom art: '+file.name;if($('#inspector-image'))$('#inspector-image').src=asset(artOverride);creditControls.refresh();});
  $('#clear-face-art').onclick=()=>{artOverride=null;fit={};$('#face-art-state').textContent='Using deck source after regeneration';creditControls.refresh();};
  $('#face-back').onclick=()=>attempt(async()=>{const file=await pickFile();if(!file)return;backOverride=(await uploadImage(file,{back:true})).id;backDesignOverride={mode:'custom'};$('#face-back-picker').classList.add('hidden');$('#face-back-state').textContent='Custom back: '+file.name;});
  $('#clear-face-back').onclick=()=>{backOverride=null;backDesignOverride=null;$('#face-back-picker').classList.add('hidden');$('#face-back-state').textContent=hasPhysicalReverse(c)?'Actual reverse will be used':'Deck default back will be used';};
  $('#face-back-designer').onclick=()=>{
    const target=$('#face-back-picker');target.classList.remove('hidden');
    mountBackPicker(target,{backAsset:backOverride||null,backDesign:backDesignOverride},choice=>{
      backOverride=choice.backAsset;backDesignOverride=choice.backDesign;
      $('#face-back-state').textContent='Individual '+(choice.backDesign.mode==='icon'?'icon back':choice.backDesign.mode==='default'?'forge back':'custom back')+' selected; save to apply.';
    },{onBusy:busy=>$('#save-card').disabled=busy});
  };
  for(const name of ['x','y','zoom','rotation'])$('#fit-'+name).oninput=()=>{
    fit={artX:Number($('#fit-x').value)/(data.width||2010),artY:Number($('#fit-y').value)/(data.height||2814),artZoom:Number($('#fit-zoom').value)/100,artRotate:Number($('#fit-rotation').value)};
  };
  $('#reset-fit').onclick=()=>{fit={};toast('Automatic artwork fit will be applied when regenerated.');};
  $('#save-card').onclick=()=>attempt(async()=>{setBusy(true);try{await persistCard();closeModal();await showDeck(d.id,'cards');toast('Card saved. Unchanged front images stay cached.');}finally{setBusy(false);}});
  $('#generate-card').onclick=()=>attempt(async()=>{setBusy(true);try{
    await persistCard();
    await prepareCard();
    syncCurrent(await api('/api/decks/'+d.id));
    refreshInspector();
    let force=false;
    if(!force && cardRenderMatchesCache(c)){
      const ok=await confirmAction(
        'This card already matches the cached render.',
        'Regenerating it now should produce the same image. Do you want to regenerate it anyway?',
        'Regenerate anyway'
      );
      if(!ok)return;
      force=true;
    }
    await renderCard(d.id,c.id,{force});
    syncCurrent(await api('/api/decks/'+d.id));
    refreshInspector();
    await showDeck(d.id,'cards');
  }finally{setBusy(false);}});
  $('#download-review-image').onclick=()=>attempt(async()=>{setBusy(true);try{await persistCard();if(!f.compiled?.render)throw new Error('Generate images for this card before downloading its review image.');
    const out=await job('/api/decks/'+d.id+'/cards/'+c.id+'/review-image',{faceId:f.id},{label:'Review image'});if(state.bootstrap?.browser)await saveApiFile(out.download,out.filename||'BulkProxyForge_Review.png',out.bytes);else location.href=out.download;await showDeck(d.id,'cards');}finally{setBusy(false);}});
  if($('#inspect-flip'))$('#inspect-flip').onclick=()=>{closeModal();if(c.faces.length===2)attempt(()=>inspect(d,c,index===0?1:0));else attempt(()=>inspectMeldReverse(d,c));};
  $('#choose-printing').onclick=()=>attempt(()=>chooseArt(d,c,f,async id=>{
    syncCurrent(await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,faceId:f.id,selectedArtPrintingId:id,artOverride:null}));
    artOverride=null;fit={};$('#face-art-state',host).textContent='Scryfall artwork selected; generate this card to update the render.';
    creditControls.refresh();refreshInspector();await showDeck(d.id,'cards');
  }));
  $('#select-rules-text').onclick=()=>attempt(()=>chooseOfficialText(d,c,f,'rules',async selection=>{
    syncCurrent(await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,faceId:f.id,officialRulesSelection:selection}));
    refreshInspector();await showDeck(d.id,'cards');
  }));
  $('#select-flavor-text').onclick=()=>attempt(()=>chooseOfficialText(d,c,f,'flavor',async selection=>{
    syncCurrent(await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,faceId:f.id,officialFlavorSelection:selection}));
    refreshInspector();await showDeck(d.id,'cards');
  }));
  $('#remove-card').onclick=()=>attempt(async()=>{closeModal();if(!await confirmAction('Remove '+c.name+'?',`Remove all ${c.quantity} copies from this deck? Other decks are not changed.`,'Remove card',true))return;await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,remove:true});await showDeck(d.id);});
  $('#copy-token').onclick=()=>copyToken(d,c);
}

function choiceOverlay(title,description){
  const overlay=document.createElement('div');overlay.className='modal-backdrop';overlay.style.zIndex='10002';
  overlay.innerHTML=`<section class="modal large" role="dialog" aria-modal="true"><header class="modal-header"><h2>${esc(title)}</h2><button class="button quiet icon" aria-label="Close picker">×</button></header><div class="modal-body"><p class="muted">${esc(description)}</p><div class="choice-content"></div></div></section>`;
  overlay.querySelector('button').onclick=()=>overlay.remove();overlay.onclick=event=>{if(event.target===overlay)overlay.remove();};
  document.body.append(overlay);return {overlay,content:overlay.querySelector('.choice-content')};
}
async function printingChoices(deck,card,face,content,draw){
  let next=null;const seen=new Set();
  const more=document.createElement('button');more.type='button';more.className='button quiet section-gap';more.textContent='More printings';
  const list=document.createElement('div');list.className='printing-grid';content.append(list,more);
  const load=async()=>{
    more.disabled=true;more.textContent='Loading printings…';
    try{
      const result=await api('/api/printings',{name:card.name,refresh:deck.settings.refreshData,nextPage:next});next=result.next_page;
      for(const sf of result.data||[]){
        const candidate=sf.card_faces?.[face.index]||sf;
        if(card.scryfall.oracle_id&&sf.oracle_id&&card.scryfall.oracle_id!==sf.oracle_id)continue;
        if(candidate.name&&face.name&&candidate.name!==face.name&&!sf.name?.includes(face.name))continue;
        if(seen.has(sf.id))continue;seen.add(sf.id);draw(list,sf,candidate);
      }
      more.classList.toggle('hidden',!next);
    }finally{more.disabled=false;more.textContent='More printings';}
  };
  more.onclick=()=>attempt(load);
  await load();
  while(next)await load();
}
async function chooseArt(deck,card,face,apply){
  const {overlay,content}=choiceOverlay('Select Art · '+face.name,'Choose artwork from an official Scryfall printing. This changes only the image and its artist credit; the card’s imported printing and rarity stay the same.');
  let selected=face.selectedArtPrintingId||card.scryfall.id;
  const footer=document.createElement('footer');footer.className='modal-footer';
  const cancel=document.createElement('button');cancel.type='button';cancel.className='button quiet';cancel.textContent='Cancel';cancel.onclick=()=>overlay.remove();
  const confirm=document.createElement('button');confirm.type='button';confirm.className='button primary';confirm.textContent='OK';
  confirm.onclick=()=>attempt(async()=>{confirm.disabled=true;try{await apply(selected);overlay.remove();toast('Artwork selected. Generate this card to update the render.');}finally{confirm.disabled=false;}});
  footer.append(cancel,confirm);overlay.querySelector('.modal').append(footer);
  try{
    await printingChoices(deck,card,face,content,(grid,sf,candidate)=>{
      const url=candidate.image_uris?.art_crop||sf.image_uris?.art_crop||candidate.image_uris?.normal||sf.image_uris?.normal;
      if(!url)return;
      const b=document.createElement('button');b.type='button';b.className='printing-option';
      b.innerHTML=`<img src="${esc(url)}" loading="lazy" alt="Artwork from ${esc(sf.set_name||sf.set||'Scryfall')}"><small>${esc((sf.set||'').toUpperCase())} · ${esc(sf.collector_number||'')}<br>${esc(candidate.artist||sf.artist||'')}</small>`;
      b.dataset.printingId=sf.id;b.setAttribute('aria-pressed',selected===sf.id?'true':'false');if(selected===sf.id)b.style.borderColor='#f28b32';
      b.onclick=()=>{selected=sf.id;for(const option of grid.querySelectorAll('[data-printing-id]')){const active=option.dataset.printingId===selected;option.setAttribute('aria-pressed',active?'true':'false');option.style.borderColor=active?'#f28b32':'';}};
      grid.append(b);
    });
  }catch(e){errorBox(content,e.message);}
}
async function chooseOfficialText(deck,card,face,kind,apply){
  const rules=kind==='rules',label=rules?'rules':'flavor';
  const {overlay,content}=choiceOverlay('Choose official '+label+' text · '+face.name,'Current Oracle text is suggested. A typed override remains separate and takes priority until you clear it.');
  const suggested=document.createElement('button');suggested.type='button';suggested.className='button primary section-gap';suggested.textContent='Use current '+(rules?'Oracle':'printing flavor')+' text (suggested)';
  suggested.onclick=()=>attempt(async()=>{await apply(null);overlay.remove();});content.append(suggested);
  const seen=new Set();
  try{
    await printingChoices(deck,card,face,content,(grid,sf,candidate)=>{
      for(const field of (rules?['oracle_text','printed_text']:['flavor_text'])){
        const value=String(candidate[field]||sf[field]||'').trim();if(!value||seen.has(field+'\n'+value))continue;seen.add(field+'\n'+value);
        const b=document.createElement('button');b.type='button';b.className='printing-option';b.style.textAlign='left';
        b.innerHTML=`<strong>${esc(field==='printed_text'?'Printed wording':field==='oracle_text'?'Oracle wording':'Flavor text')}</strong><small>${esc((sf.set||'').toUpperCase())} · ${esc(sf.collector_number||'')}</small><p style="white-space:pre-wrap">${esc(value)}</p>`;
        b.onclick=()=>attempt(async()=>{b.disabled=true;try{await apply({printingId:sf.id,field});overlay.remove();toast('Official '+label+' text selected.');}finally{b.disabled=false;}});
        grid.append(b);
      }
    });
  }catch(e){errorBox(content,e.message);}
}
function copyToken(d,c){
  const host=modal('Copy token · '+c.name,`<p class="muted" style="margin-bottom:18px">Uses the preserved Card Tools token layout. Prepare the source card before creating a token.</p><label class="check-line"><input id="token-nonlegendary" type="checkbox" checked><span>Make it nonlegendary</span></label><label class="field"><span>Creature subtype override <small>optional</small></span><input id="token-subtypes" placeholder="e.g. Illusion"></label><label class="field"><span>Power / toughness <small>optional</small></span><input id="token-pt" placeholder="e.g. 0/1"></label><label class="field"><span>Frame color</span><select id="token-color"><option value="">Use source color</option>${['W','U','B','R','G','M','A','L'].map(x=>`<option>${x}</option>`).join('')}</select></label>`,{size:'small',footer:'<button class="button primary" id="make-token">Add copy token</button>'});
  $('#make-token').onclick=async()=>{try{const spec={nonlegendary:$('#token-nonlegendary').checked};if($('#token-subtypes').value)spec.replace_creature_subtypes=$('#token-subtypes').value.split(/[, ]+/).filter(Boolean);if($('#token-pt').value)spec.power_toughness=$('#token-pt').value;if($('#token-color').value)spec.frame_color=$('#token-color').value;await api('/api/decks/'+d.id+'/cards/'+c.id+'/token',{revision:d.revision,spec});closeModal();await showDeck(d.id);toast('Copy token added.');}catch(e){errorBox($('.modal-body',host),e.message);}};
}
window.addEventListener('pf-deck-metadata',event=>{void refreshDeckProgress(event.detail.id).catch(error=>toast(error.message,true));});
