import {mountBackPicker} from './backs.js';
import {$,$$,esc,state,api,attempt,toast,modal,closeModal,errorBox,job,loading,empty,badge,asset,nav,confirmAction,uploadImage,downloadPost,downloadBlob} from './ui.js';
import {renderSetup,templateOptions,pickFile,rarities} from './setup.js';
import {renderDecks,renderCard} from './render.js';
import {chooseOrder} from './orders.js';
import {creditFields,bindCreditFields,ensureCustomArtCredits} from './credits.js';
const views=new Map();
export async function importDeck(existing=null){
  if(state.busy)throw new Error('Wait for the current task or cancel it before importing another deck.');
  const host=modal(existing?'Add cards to '+existing.name:'Bring your next deck to the table',`<span class="eyebrow">START WITH THE CARDS YOU ALREADY CHOSE</span><p class="muted" style="margin-bottom:22px">Paste a public Scryfall deck link, a card list, or upload the deck’s JSON export. Exact printing identifiers keep your chosen artwork intact.</p>${existing?'':`<label class="field"><span>Deck name <small>optional</small></span><input id="import-name" placeholder="Use the name from Scryfall" maxlength="200"></label>`}<label class="field"><span>${existing?'Cards to add':'Deck link or decklist'}</span><textarea id="import-source" rows="7" placeholder="https://scryfall.com/@you/decks/…&#10;&#10;or&#10;1 Sol Ring (CMM) 396&#10;12 Forest"></textarea></label><label class="field"><span>Or upload a deck export</span><input type="file" id="import-file" accept=".json,.txt"><small>JSON is best for keeping each selected printing. Plain names use Scryfall’s named-card result; you can change the printing afterward.</small></label><label class="check-line"><input type="checkbox" id="import-outside"><span>Include “Outside the Game” cards<small>Sideboard and maybeboard remain excluded, matching Card Tools.</small></span></label>${existing?'':`<div class="notice info">Next: choose artwork, reuse or customize templates, add four rarity symbols and a deck back. You can use existing templates or create/upload your own.</div>`}`,{footer:`<span class="footer-hint">Nothing is sent to a printer during import.</span><button class="button primary" id="do-import">${existing?'Add cards':'Import deck →'}</button>`});
  $('#import-file').onchange=()=>attempt(async()=>{const f=$('#import-file').files[0];if(!f)return;if(f.size>20*1024**2)throw new Error('Choose a deck export under 20 MB.');$('#import-source').value=await f.text();});
  $('#do-import').onclick=async()=>{
    const source=$('#import-source').value.trim();if(!source){errorBox($('.modal-body',host),'Paste a deck link or card list first.');return;}
    $('#do-import').disabled=true;
    const payload={source,includeOutside:$('#import-outside').checked,...(existing?{revision:existing.revision}:{name:$('#import-name').value.trim()})};
    closeModal();
    try{
      const d=await job(existing?'/api/decks/'+existing.id+'/add':'/api/decks/import',payload,{label:existing?'Add cards':'Import deck'});
      state.dirty=false;
      if(existing){await showDeck(d.id,'cards');toast('Cards added. Generate images to prepare the new entries.');}
      else nav('deck/'+d.id+'/setup');
    }catch(e){toast(e.message,true);}
  };
}
function preview(c,f){
  return f.compiled?.render?.url||(f.compiled?.artId?asset(f.compiled.artId):null)||(c.scryfall.card_faces?.[f.index]?.image_uris?.art_crop)||c.scryfall.image_uris?.art_crop||'';
}
function backPreview(c,d){
  if(c.backOverride)return asset(c.backOverride);
  if(c.meldBackAsset)return asset(c.meldBackAsset);
  if(c.faces.length===2)return preview(c,c.faces[1]);
  return asset(d.settings.backAsset);
}
export async function showDeck(id,tab='cards'){
  const oldScroll=$('.card-grid')?.scrollTop||0;
  const d=await api('/api/decks/'+id);state.activeDeck=d;
  let v=views.get(id);if(!v){v={query:'',filter:'all'};views.set(id,v);}
  const summary=d.summary,dirty=d.status==='draft';
  $('#main').innerHTML=`<a class="back-to-library" href="#decks">← All decks</a><div class="page-head"><div><span class="eyebrow">DECK STUDIO</span><h1>${esc(d.name)}</h1><div class="actions" style="margin-top:12px">${badge(d.status)}<span class="count-label">${summary.cards} cards · ${summary.faces} faces · ${summary.rendered} rendered</span></div><div class="deck-progress"><span class="complete"><b>✓</b>Import</span><span class="${dirty?'current':'complete'}"><b>${dirty?'2':'✓'}</b>Art & style</span><span class="${d.status==='ready'?'complete':!dirty?'current':''}"><b>${d.status==='ready'?'✓':'3'}</b>Generate images</span><span><b>4</b>Review & print</span></div></div><div class="actions"><button class="button" id="deck-menu">More ▾</button><button class="button" id="add-cards">＋ Add cards</button><button class="button primary" id="generate-deck">Generate images</button></div></div>
    <div class="tabs"><button data-tab="cards" class="${tab==='cards'?'active':''}">Cards <span>${summary.cards}</span></button><button data-tab="setup" class="${tab==='setup'?'active':''}">Art & setup</button><button data-tab="review" class="${tab==='review'?'active':''}">Review <span>${summary.warnings+summary.errors||''}</span></button></div>${d.upgradeRequired?`<div class="notice info">This deck was prepared with an older render pipeline. Generate images will force a fresh render of every face. Running pipeline: ${esc(state.bootstrap.pipelineVersion||'unknown')}.</div>`:''}<div id="deck-body"></div>`;
  $$('[data-tab]').forEach(b=>b.onclick=()=>nav('deck/'+id+'/'+b.dataset.tab));
  $('#add-cards').onclick=()=>attempt(()=>importDeck(d));
  $('#generate-deck').onclick=()=>attempt(()=>generate(d));
  $('#deck-menu').onclick=()=>deckMenu(d);
  if(tab==='setup'){
    renderSetup($('#deck-body'),d,async(updated,generateNow)=>{
      if(generateNow){history.replaceState(null,'','#deck/'+id);await showDeck(id,'cards');await generate(updated);}
      else await showDeck(id,'setup');
    });return;
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
    let cards=d.cards.filter(c=>c.name.toLowerCase().includes(v.query.toLowerCase()));
    if(v.filter==='attention')cards=cards.filter(c=>c.faces.some(f=>f.error||f.compiled?.crop?.warning||f.compiled?.flags?.length));
    if(v.filter==='unrendered')cards=cards.filter(c=>c.faces.some(f=>!f.compiled?.render));
    $('#deck-body').innerHTML=`${dirty?'<div class="notice info">You have saved changes to prepare. Generate images will rebuild only the affected faces and reuse unchanged PNGs.</div>':''}<div class="toolbar"><div class="filter-pills"><button data-card-filter="all" class="${v.filter==='all'?'active':''}">All cards</button><button data-card-filter="unrendered" class="${v.filter==='unrendered'?'active':''}">Not rendered</button><button data-card-filter="attention" class="${v.filter==='attention'?'active':''}">Needs review</button></div><label class="search"><input id="card-search" type="search" aria-label="Find a card" placeholder="Find a card…" value="${esc(v.query)}"></label><button class="button small" id="quick-order">Review order ↗</button></div>${cards.length?`<div class="card-grid">${cards.map(c=>{
      const f=c.faces[0],front=preview(c,f),back=backPreview(c,d),done=!!f.compiled?.render;
    const warning=c.faces.some(x=>x.error||x.compiled?.crop?.warning||x.compiled?.flags?.length);
    return `<article class="card-item"><button class="card-image" data-card="${c.id}" aria-label="Edit ${esc(c.name)}"><span class="quantity-pill">${c.quantity}×</span><span class="card-name-pill" title="${esc(c.name)}">${esc(c.name)}</span>${warning?'<span class="warn-pill">!</span>':''}${front?`<img src="${esc(front)}" data-hover-front="${esc(front)}" ${back?`data-hover-back="${esc(back)}"`:''} class="${done?'':'art-only'}" loading="lazy" alt="${esc(c.name)}">`:'<span class="card-empty-symbol">▱</span>'}${!done?`<span class="image-label">${f.error?'Needs attention':'Art preview · not rendered'}</span>`:dirty?'<span class="image-label">Previous render · changes pending</span>':''}</button></article>`;
    }).join('')}</div>`:empty(d.cards.length?'No cards match':'This deck is waiting for cards',d.cards.length?'Try a different search or review filter.':'Add a card list or a Scryfall export to get started.',`<button class="button primary" id="empty-add">＋ Add cards</button>`)}<div class="subtitle-line">Hover a card to see its back. Click it to edit its artist, art, printing, quantity or template. Real double-faced cards hover to their actual reverse face.</div>`;
    $$('[data-card]').forEach(b=>b.onclick=()=>attempt(()=>inspect(d,d.cards.find(c=>c.id===b.dataset.card),0)));
    $$('[data-hover-back]').forEach(img=>{const card=img.closest('[data-card]'),front=img.dataset.hoverFront,back=img.dataset.hoverBack;if(!card||!front||!back)return;card.onmouseenter=()=>{img.src=back;};card.onmouseleave=()=>{img.src=front;};});
    $$('[data-card-filter]').forEach(b=>b.onclick=()=>{v.filter=b.dataset.cardFilter;cardsGrid();});
    $('#card-search').oninput=e=>{v.query=e.target.value;const start=e.target.selectionStart??v.query.length,end=e.target.selectionEnd??start;cardsGrid();const search=$('#card-search');search.focus();try{search.setSelectionRange(start,end)}catch{}};
    $('#quick-order').onclick=()=>attempt(()=>chooseOrder([id]));if($('#empty-add'))$('#empty-add').onclick=()=>attempt(()=>importDeck(d));
  }
  cardsGrid();if($('.card-grid'))$('.card-grid').scrollTop=oldScroll;
}
async function generate(d){
  if(state.dirty)throw new Error('Save the setup changes before generating images.');
  if(!rarities.every(r=>d.settings.symbols?.[r])){nav('deck/'+d.id+'/setup');throw new Error('Set up your four rarity symbols first.');}
  d=await ensureCustomArtCredits(d);if(!d)return;
  await renderDecks([d.id],{force:!!d.upgradeRequired,onUpdate:async()=>{if(state.route==='deck'&&state.activeDeck?.id===d.id)await showDeck(d.id,'cards');}});
}
function deckMenu(d){
  const permanent=!!state.bootstrap.settings?.deletePermanently;
  modal('Deck actions',`<div class="stack"><button class="button" id="duplicate-deck">Duplicate deck</button><button class="button" id="deck-image-zip">Download paired images ZIP</button><button class="button" id="download-cc">Export CardConjurer save</button><button class="button" id="download-originals">Download original printing images</button><button class="button" id="download-cropped-art">Download Cropped Art</button><button class="button" id="download-review-images">Download review Images</button><button class="button" id="use-as-defaults">Use this deck’s style as my default</button><button class="button danger" id="trash-deck">${permanent?'Delete deck permanently':'Move deck to Trash'}</button></div><p class="muted" style="margin-top:16px;font-size:12px">${permanent?'Permanent deletion cannot be undone. Shared artwork and render caches are retained.':'Exports use prepared card data. Review images place the selected Scryfall printing beside your rendered card with a 1 px gap. Only actual double-faced reverse faces are included.'}</p>`,{size:'small'});
  $('#duplicate-deck').onclick=()=>attempt(async()=>{const copy=await api('/api/decks/'+d.id+'/duplicate',{});closeModal();nav('deck/'+copy.id);});
  $('#deck-image-zip').onclick=()=>attempt(async()=>{closeModal();await chooseOrder([d.id]);});
  $('#download-cc').onclick=()=>attempt(()=>downloadPost('/api/cardconjurer/export',{deckIds:[d.id]},d.name+'.cardconjurer'));
  $('#download-originals').onclick=()=>attempt(async()=>{closeModal();const out=await job('/api/decks/'+d.id+'/originals',{}, {label:'Original printing images'});location.href=out.download;});
  $('#download-cropped-art').onclick=()=>attempt(async()=>{closeModal();const out=await job('/api/decks/'+d.id+'/cropped-art',{}, {label:'Cropped art'});location.href=out.download;});
  $('#download-review-images').onclick=()=>attempt(async()=>{
    closeModal();
    let current=await api('/api/decks/'+d.id);
    const needsGeneration=!!current.upgradeRequired||current.status==='draft'||Number(current.summary?.rendered||0)<Number(current.summary?.faces||0);
    if(needsGeneration){
      await generate(current);
      current=await api('/api/decks/'+d.id);
      if(Number(current.summary?.rendered||0)<Number(current.summary?.faces||0)){
        throw new Error('Some card images could not be generated. Fix those cards before downloading review images.');
      }
    }
    const out=await job('/api/decks/'+d.id+'/review-images',{}, {label:'Review images'});
    location.href=out.download;
  });
  $('#use-as-defaults').onclick=()=>attempt(async()=>{const defaults={symbols:d.settings.symbols,backAsset:d.settings.backAsset,backDesign:d.settings.backDesign||null,artist:d.settings.artist,modificationCredit:d.settings.modificationCredit||'',templateRules:d.settings.templateRules};await api('/api/settings',{defaults});closeModal();toast('Symbols, back, artist credits and templates saved as defaults for new decks.');});
  $('#trash-deck').onclick=()=>attempt(async()=>{closeModal();const title=permanent?'Delete this deck permanently?':'Move this deck to Trash?',detail=permanent?d.name+' will be deleted immediately and cannot be restored. Shared artwork and render caches are kept.':d.name+' and its saved setup can be restored later.',label=permanent?'Delete permanently':'Move to Trash';if(!await confirmAction(title,detail,label,true))return;await api('/api/decks/'+d.id+'/delete',{revision:d.revision});state.selected.delete(d.id);nav('decks');toast(permanent?'Deck permanently deleted.':'Deck moved to Trash.');});
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
    if(f.compiled?.crop?.warning){const crop=f.compiled.crop;parts.push(`<div class="notice">Crop warning: ${(crop.cropX*100).toFixed(1)}% width / ${(crop.cropY*100).toFixed(1)}% height outside the art window.</div>`);}
    if(f.error)parts.push(`<div class="notice error">${esc(f.error)}</div>`);
    return parts.join('');
  };
  const host=modal(f.name,`<div class="inspector"><div class="inspector-preview">${preview(c,f)?`<img src="${esc(preview(c,f))}" id="inspector-image" alt="${esc(f.name)}">`:'<div class="card-image">No artwork yet</div>'}${c.faces.length===2?`<button class="button quiet wide" id="inspect-flip">Edit ${index===0?'reverse':'front'} face ↻</button>`:''}<div class="subtitle-line" id="inspector-status">${esc(comp?.render?'CardConjurer render':'Artwork preview; generate this card for the full card image.')}</div><div id="inspector-notices">${renderNotice()}</div></div><div><h3>Card details</h3><div class="field-row"><label class="field"><span>Quantity in this deck</span><input id="card-qty" type="number" min="1" max="9999" step="1" value="${c.quantity}"></label><div class="field"><span>Selected printing</span><button class="button" id="choose-printing">${esc((c.scryfall.set||'').toUpperCase())} · ${esc(c.scryfall.collector_number||'')} &nbsp; Change ↗</button></div></div>${creditFields(d,c,f)}<label class="field"><span>Template for this face</span><select id="face-template"><option value="">Use deck rule</option>${templateOptions(group,legendary,f.templateOverride||'auto')}</select><small>Layout: ${esc(state.bootstrap.groups[group]||group)}. Incompatible choices are hidden.</small></label>
  <div class="field"><span>Custom artwork override</span><div class="actions"><button class="button small" id="face-art">Upload art</button><button class="button quiet small" id="clear-face-art">Use deck artwork source</button></div><small id="face-art-state">${artOverride?'Individual custom artwork selected':esc(comp?.artOrigin||'Using deck source')}</small>${artShapeHint}</div>
  <div class="field"><span>Back override <small>optional, applies to this card only</small></span><div class="actions"><button class="button small" id="face-back">Upload full back</button><button class="button small" id="face-back-designer">Default / icon back</button><button class="button quiet small" id="clear-face-back">${c.faces.length===2?'Use actual reverse':'Use deck back'}</button></div><small id="face-back-state">${backOverride?'Individual back selected':c.faces.length===2?'Paired with '+esc(c.faces[1].name):'Using deck default back'}</small><div id="face-back-picker" class="hidden"></div></div>
  <details><summary>Artwork positioning & text overrides</summary><p class="muted" style="font-size:11px;margin-bottom:13px">The default is Card Tools’ existing fit. Changing these values affects only this face.</p><div class="field-row"><label class="field"><span>Horizontal position (pixels)</span><input id="fit-x" type="number" step="1" value="${Math.round((data.artX||0)*(data.width||2010))}"></label><label class="field"><span>Vertical position (pixels)</span><input id="fit-y" type="number" step="1" value="${Math.round((data.artY||0)*(data.height||2814))}"></label></div><div class="field-row"><label class="field"><span>Art scale (%)</span><input id="fit-zoom" type="number" min=".01" step=".1" value="${((data.artZoom||1)*100).toFixed(2)}"></label><label class="field"><span>Rotation (degrees)</span><input id="fit-rotation" type="number" step="1" value="${data.artRotate||0}"></label></div><button class="button quiet small" id="reset-fit">Reset to automatic fitting</button><label class="field section-gap"><span>Rules text override</span><textarea id="rules-override" rows="4" placeholder="Use current Scryfall Oracle text">${esc(f.semanticOverrides?.oracle_text??'')}</textarea><small>Leave blank to use the fetched Oracle text. The original Scryfall record remains cached unchanged.</small></label><label class="field"><span>Flavor text override</span><textarea id="flavor-override" rows="3" placeholder="Use the deck’s flavor policy">${esc(f.semanticOverrides?.flavor_text??'')}</textarea></label><label class="check-line"><input type="checkbox" id="remove-flavor" ${f.semanticOverrides?.flavor_text===''?'checked':''}><span>Remove flavor text from this face</span></label><label class="field"><span>Rarity / set-symbol override</span><select id="rarity-override"><option value="">Use selected printing (${esc(c.scryfall.rarity||'common')})</option>${rarities.map(r=>`<option value="${r}" ${f.semanticOverrides?.rarity===r?'selected':''}>${r}</option>`).join('')}</select></label></details><div class="inspector-actions"><button class="button danger-quiet small" id="remove-card">Remove card</button><button class="button quiet small" id="copy-token">Make copy token</button></div></div></div>`,{size:'large',footer:`<span class="footer-hint">Changes are saved to this deck only.</span><button class="button quiet" id="cancel-card">Cancel</button><button class="button quiet" id="download-review-image">Download review image</button><button class="button" id="generate-card">Generate this card</button><button class="button primary" id="save-card">Save card</button>`});
  const creditControls=bindCreditFields(host,d,c,f,()=>artOverride);
  $('#face-template').value=f.templateOverride||'';
  const syncCurrent=updated=>{d=updated;c=d.cards.find(x=>x.id===card.id);if(!c)throw new Error('This card was removed.');f=c.faces.find(x=>x.id===f.id)||c.faces[index]||c.faces[0];};
  const refreshInspector=()=>{
    const img=$('#inspector-image');const src=preview(c,f);if(img&&src)img.src=src;
    if($('#inspector-status'))$('#inspector-status').textContent=f.compiled?.render?'CardConjurer render':'Artwork preview; generate this card for the full card image.';
    if($('#inspector-notices'))$('#inspector-notices').innerHTML=renderNotice();
  };
  const setBusy=busy=>['cancel-card','download-review-image','generate-card','save-card'].forEach(id=>{const el=$('#'+id);if(el)el.disabled=busy;});
  const cardRenderMatchesCache=card=>{
    const faces=card?.faces||[];
    return faces.length>0 && faces.every(face=>!face.error && face.compiled?.renderKey && face.compiled?.render);
  };
  const buildPatch=()=>{
    const credits=creditControls.values();
    const semantic={...f.semanticOverrides};const rules=$('#rules-override').value;if(rules)semantic.oracle_text=rules;else delete semantic.oracle_text;
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
  $('#clear-face-back').onclick=()=>{backOverride=null;backDesignOverride=null;$('#face-back-picker').classList.add('hidden');$('#face-back-state').textContent=c.faces.length===2?'Actual reverse will be used':'Deck default back will be used';};
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
    let force=!!d.upgradeRequired;
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
  $('#download-review-image').onclick=()=>attempt(async()=>{setBusy(true);try{const force=!!d.upgradeRequired;await persistCard();await prepareIfNeeded();if(!f.compiled?.render){await renderCard(d.id,c.id,{force});syncCurrent(await api('/api/decks/'+d.id));refreshInspector();}
    const out=await job('/api/decks/'+d.id+'/cards/'+c.id+'/review-image',{faceId:f.id},{label:'Review image'});location.href=out.download;await showDeck(d.id,'cards');}finally{setBusy(false);}});
  if($('#inspect-flip'))$('#inspect-flip').onclick=()=>{closeModal();attempt(()=>inspect(d,c,index===0?1:0));};
  $('#choose-printing').onclick=()=>attempt(()=>printings(d,c));
  $('#remove-card').onclick=()=>attempt(async()=>{closeModal();if(!await confirmAction('Remove '+c.name+'?',`Remove all ${c.quantity} copies from this deck? Other decks are not changed.`,'Remove card',true))return;await api('/api/decks/'+d.id+'/cards/'+c.id,{revision:d.revision,remove:true});await showDeck(d.id);});
  $('#copy-token').onclick=()=>copyToken(d,c);
}

async function printings(d,c){
  const host=modal('Choose a printing · '+c.name,loading(),{size:'large'});let next=null;
  async function load(append=false){
    const result=await api('/api/printings',{name:c.name,refresh:d.settings.refreshData,nextPage:append?next:null});next=result.next_page;
    let grid=$('.printing-grid',host);
    if(!append){$('.modal-body',host).innerHTML='<p class="muted" style="margin-bottom:18px">This changes the selected paper printing and its default artwork. Individual custom-art overrides are kept.</p><div class="printing-grid"></div><button class="button quiet section-gap" id="more-printings">More printings</button>';grid=$('.printing-grid',host);}
    for(const sf of result.data){const b=document.createElement('button');b.className='printing-option';const url=sf.image_uris?.normal||sf.card_faces?.[0]?.image_uris?.normal;b.innerHTML=`${url?`<img src="${esc(url)}" loading="lazy" alt="${esc(sf.name)}">`:esc(sf.name)}<small>${esc((sf.set||'').toUpperCase())} · ${esc(sf.collector_number)}<br>${esc(sf.artist||sf.card_faces?.[0]?.artist||'')}</small>`;b.onclick=()=>attempt(async()=>{b.disabled=true;await api('/api/decks/'+d.id+'/cards/'+c.id+'/printing',{revision:d.revision,source:sf.id});closeModal();await showDeck(d.id);toast('Printing changed. Generate images to use its artwork.');});grid.append(b);}
    $('#more-printings').classList.toggle('hidden',!next);$('#more-printings').onclick=()=>attempt(()=>load(true));
  }
  try{await load();}catch(e){errorBox($('.modal-body',host),e.message);}
}
function copyToken(d,c){
  const host=modal('Copy token · '+c.name,`<p class="muted" style="margin-bottom:18px">Uses the preserved Card Tools token layout. Prepare the source card before creating a token.</p><label class="check-line"><input id="token-nonlegendary" type="checkbox" checked><span>Make it nonlegendary</span></label><label class="field"><span>Creature subtype override <small>optional</small></span><input id="token-subtypes" placeholder="e.g. Illusion"></label><label class="field"><span>Power / toughness <small>optional</small></span><input id="token-pt" placeholder="e.g. 0/1"></label><label class="field"><span>Frame color</span><select id="token-color"><option value="">Use source color</option>${['W','U','B','R','G','M','A','L'].map(x=>`<option>${x}</option>`).join('')}</select></label>`,{size:'small',footer:'<button class="button primary" id="make-token">Add copy token</button>'});
  $('#make-token').onclick=async()=>{try{const spec={nonlegendary:$('#token-nonlegendary').checked};if($('#token-subtypes').value)spec.replace_creature_subtypes=$('#token-subtypes').value.split(/[, ]+/).filter(Boolean);if($('#token-pt').value)spec.power_toughness=$('#token-pt').value;if($('#token-color').value)spec.frame_color=$('#token-color').value;await api('/api/decks/'+d.id+'/cards/'+c.id+'/token',{revision:d.revision,spec});closeModal();await showDeck(d.id);toast('Copy token added.');}catch(e){errorBox($('.modal-body',host),e.message);}};
}
