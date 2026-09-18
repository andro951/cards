import {mountBackPicker} from './backs.js';
import {githubSetupSection,mountGithubSetupImport} from './github-setup.js';
import {$,$$,esc,state,api,attempt,toast,uploadImage,uploadFolder,asset,job,nav} from './ui.js';
import {originalArtist,composeCredit} from './credits.js';
export const rarities=['common','uncommon','rare','mythic'];
const symbolImage=/\.(png|jpe?g|webp|gif|svg)$/i;
export function symbolFolderFiles(files){
  const found={},unexpected=[];
  for(const file of [...files]){
    if(!symbolImage.test(file.name))continue;
    const stem=file.name.replace(/\.[^.]+$/,'').toLowerCase();
    if(!rarities.includes(stem)){unexpected.push(file.name);continue;}
    if(found[stem])throw new Error(`The symbol folder contains more than one ${stem} image. Keep exactly one file named ${stem}.*.`);
    found[stem]=file;
  }
  const missing=rarities.filter(r=>!found[r]);
  if(unexpected.length)throw new Error('The symbol folder must contain only common.*, uncommon.*, rare.*, and mythic.* image files. Rename or remove: '+unexpected.join(', '));
  if(missing.length)throw new Error('The symbol folder is missing: '+missing.map(r=>r+'.*').join(', ')+'.');
  return found;
}
export function pickFile(accept='image/*',multiple=false){return new Promise(resolve=>{const input=document.createElement('input');input.type='file';input.accept=accept;input.multiple=multiple;input.onchange=()=>resolve(multiple?[...input.files]:input.files[0]||null);input.oncancel=()=>resolve(null);input.click();});}
export function templateOptions(group,legendary=false,value='auto'){
  const ordinary=['standard','legendary','land','legendary-land','basic-land'].includes(group);
  return state.templates.filter(t=>t.id==='auto'||(t.groups==='ordinary'?ordinary: Array.isArray(t.groups)&&t.groups.includes(group))&&(!legendary||t.legendary)).map(t=>`<option value="${esc(t.id)}" ${t.id===value?'selected':''}>${esc(t.name)}</option>`).join('');
}
export function renderSetup(root,deck,onSaved){
  const s=structuredClone(deck.settings),groups={};s.source={mode:'scryfall',githubFolder:'',ref:'',fallback:true,localFiles:{},...s.source};s.symbols={...s.symbols};s.templateRules={...s.templateRules};
  for(const c of deck.cards)for(const f of c.faces){const g=f.group||f.compiled?.group||'standard';groups[g]=(groups[g]||0)+1;}
  root.innerHTML=githubSetupSection(s.githubSetupFolder||'')+`<fieldset class="setup-fields" id="setup-fields" aria-label="Deck setup"><div class="setup-columns"><div>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">01 / ARTWORK</span><h2>Choose where the art comes from</h2><p>Your Scryfall deck’s exact printing is kept—not replaced with a random version.</p></div></div>
      <div class="source-choices"><button class="choice ${s.source.mode==='scryfall'?'selected':''}" data-mode="scryfall"><span class="choice-symbol">▧</span><b>Scryfall printing</b><span>Use the art already selected in your deck.</span></button><button class="choice ${s.source.mode==='github'?'selected':''}" data-mode="github"><span class="choice-symbol">⌘</span><b>GitHub folder</b><span>Paste a folder link. No local repository needed.</span></button><button class="choice ${s.source.mode==='local'?'selected':''}" data-mode="local"><span class="choice-symbol">▱</span><b>Computer folder</b><span>Choose your artwork directly from this device.</span></button></div>
      <div data-source="scryfall" class="${s.source.mode==='scryfall'?'':'hidden'}"><div class="notice info">Use any real paper printing. The selected set and collector number are preserved, and each card’s art can still be replaced individually.</div></div>
      <div data-source="github" class="${s.source.mode==='github'?'':'hidden'}"><label class="field"><span>GitHub artwork folder</span><input id="github-folder" value="${esc(s.source.githubFolder)}" placeholder="https://github.com/you/cards/tree/main/my_deck"><small>Names should match cards, for example <code>the_world_tree.png</code>. Apostrophes are removed; spaces become underscores.</small></label><label class="field"><span>Branch or commit override <small>optional</small></span><input id="github-ref" value="${esc(s.source.ref||'')}" placeholder="Use the ref from the URL"></label></div>
      <div data-source="local" class="${s.source.mode==='local'?'':'hidden'}"><label class="field"><span>Choose the artwork folder</span><input type="file" id="local-art" webkitdirectory directory multiple><small id="local-count">${Object.keys(s.source.localFiles||{}).length} images saved for this deck. Files stay in your local workspace; they are not uploaded to GitHub.</small></label></div>
      <label class="check-line ${s.source.mode==='scryfall'?'hidden':''}" id="fallback-line"><input type="checkbox" id="art-fallback" ${s.source.fallback?'checked':''}><span>Use Scryfall artwork when a custom image is missing<small>Turn off to require matching custom art for every card.</small></span></label>
      <label class="check-line"><input type="checkbox" id="use-land-library" ${s.useLandLibrary?'checked':''}><span>Use the full-art land library<small>Uses matching lands from Bulk Proxy Forge's hosted library. Individual art overrides and your main custom-art folder take priority.</small></span></label>
    </section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">02 / TEMPLATES</span><h2>One deck. Your choice of frames.</h2><p>Choose by meaningful layout—not by arbitrary card type.</p></div><button class="button quiet small" id="open-templates">Create / upload ↗</button></div>
      <div class="notice info">Automatic uses your approved Card Tools recipes unchanged. Classic and Crowned full art support legendary cards. Full-art land does not have a compatible crown.</div>
      ${Object.keys(groups).length?`<table class="rules-table"><thead><tr><th>Card layout</th><th>Template</th></tr></thead><tbody>${Object.entries(groups).map(([g,n])=>`<tr><td>${esc(state.bootstrap.groups[g]||g)} <span class="rule-count">${n}</span></td><td><select data-rule="${g}" aria-label="Template for ${esc(state.bootstrap.groups[g]||g)}">${templateOptions(g,['legendary','legendary-land'].includes(g),s.templateRules[g]||'auto')}</select></td></tr>`).join('')}</tbody></table>`:`<p class="muted">Add cards first. Their layout groups will appear here.</p>`}
      <details><summary>Template safety & advanced options</summary><p class="muted">Special layouts are recognized separately. When the approved recipes do not cover one, choose a compatible custom template; the app will never substitute an incorrect ordinary frame.</p><label class="check-line"><input type="checkbox" id="disable-autofit" ${s.disableAutofit?'checked':''}><span>Keep template art positioning instead of automatic fitting<small>Leave off for the normal cover/center crop behavior.</small></span></label></details>
    </section>
  </div><div>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">03 / SET SYMBOLS</span><h2>Four rarities. One identity.</h2><p>Bulk Proxy Forge starts every deck with built-in rarity symbols. Replace a rarity only when you intentionally want a different symbol.</p></div></div><div class="symbol-grid" id="symbol-grid"></div><div class="actions"><button class="button small" id="restore-symbols">Restore built-in defaults</button><button class="button small" id="symbol-folder-button">Replace all four from folder</button><input type="file" id="symbol-folder" webkitdirectory directory multiple accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,.svg" hidden><button class="button small" id="generate-symbols">Replace all four from one image</button><span class="muted" style="font-size:10px">PNG, JPEG, WebP, GIF, or SVG</span></div><small id="symbol-folder-status" style="display:block;margin-top:12px">Click an individual rarity above to replace only that symbol. Folder filenames must be <code>common.*</code>, <code>uncommon.*</code>, <code>rare.*</code>, and <code>mythic.*</code>.</small><small style="display:block;margin-top:7px">Generated treatments preserve transparency. Review the four previews before printing; they are color treatments, not a redraw of your symbol.</small></section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">04 / CARD BACK</span><h2>The back of this deck</h2><p>One default for single-sided cards. Real double-faced cards keep their actual reverse.</p></div></div><div id="back-designer"></div></section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">05 / DETAILS</span><h2>Credit the artist</h2></div></div><label class="field"><span>Artist for custom artwork in this deck</span><input id="deck-artist" value="${esc(s.artist||'')}" placeholder="Artist name for your custom artwork"><small>Used only for custom artwork. Scryfall originals and fallback images always keep the real printing artist. If you leave this blank, Generate images will ask whether one artist applies to all custom art or whether you want to enter artists per card.</small></label><label class="field"><span>Modification credit for this deck <small>optional</small></span><input id="deck-modification" maxlength="160" value="${esc(s.modificationCredit||'')}" placeholder="e.g. Modified by ChatGPT"><small>Appended after each card’s artist. You can change or suppress it per face.</small></label><div class="credit-preview" aria-live="polite"><span class="eyebrow">EXAMPLE ARTIST LINES</span><small>Scryfall artwork</small><strong id="scryfall-credit-preview"></strong><small>Custom artwork</small><strong id="custom-credit-preview"></strong></div><label class="field"><span>Deck name</span><input id="deck-name" maxlength="200" value="${esc(deck.name)}"></label><label class="field"><span>Notes <small>only visible here</small></span><textarea id="deck-notes" rows="3">${esc(deck.notes||'')}</textarea></label>
      <label class="field"><span>Reuse style from another deck</span><select id="reuse-style"><option value="">Choose a deck…</option>${state.decks.filter(d=>d.id!==deck.id).map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join('')}</select><small>Copies its symbols, back, artist/modification credits and template choices—not its card list or artwork folder.</small></label>
      <label class="field"><span>Flavor text source</span><select id="flavor-policy"><option value="auto" ${(!s.flavorPolicy||s.flavorPolicy==='auto')?'selected':''}>Automatic · preserve exact printings</option><option value="resolved" ${s.flavorPolicy==='resolved'?'selected':''}>Selected printing</option><option value="latest" ${s.flavorPolicy==='latest'?'selected':''}>Latest English paper printing</option></select><small>Only flavor text changes. The selected card printing and artwork remain unchanged.</small></label><label class="check-line"><input type="checkbox" id="refresh-data" ${s.refreshData?'checked':''}><span>Fetch new data when the cached copy is at least one week old<small>Normal mode reuses Scryfall data for one year. This does not refetch every time.</small></span></label>
    </section>
  </div></div><div class="setup-save"><span class="save-status" id="setup-state">Saved settings · changes stay local</span><button class="button" id="save-setup">Save changes</button><button class="button primary" id="save-generate">Save & generate images →</button></div></fieldset>`;
  const mark=()=>{state.dirty=true;$('#setup-state',root).textContent='Unsaved changes';};
  const defaultSymbols=()=>Object.fromEntries(rarities.map(r=>[r,state.bootstrap.symbols?.defaults?.[r]?.id]).filter(([,id])=>!!id));
  const isDefaultSymbol=r=>s.symbols[r]===state.bootstrap.symbols?.defaults?.[r]?.id;
  const redrawSymbols=()=>{$('#symbol-grid',root).innerHTML=rarities.map(r=>`<button class="symbol-upload ${s.symbols[r]?'has-image':''}" data-symbol="${r}" aria-label="Replace ${r} set symbol">${s.symbols[r]?`<img src="${asset(s.symbols[r])}" alt="${r} set symbol">`:'<span class="symbol-empty">◇</span>'}<small>${r}${isDefaultSymbol(r)?' · default':''}</small></button>`).join('');$$('[data-symbol]',root).forEach(b=>b.onclick=()=>attempt(async()=>{const f=await pickFile('image/*,.svg');if(!f)return;b.disabled=true;const a=await uploadImage(f,{symbol:true});s.symbols[b.dataset.symbol]=a.id;redrawSymbols();mark();$('#symbol-folder-status',root).textContent=`Replaced ${b.dataset.symbol}. The other rarity symbols are unchanged.`;}));};
  const backPicker=mountBackPicker($('#back-designer',root),s,choice=>{
    s.backAsset=choice.backAsset;s.backDesign=choice.backDesign;mark();
  },{onBusy:busy=>{
    for(const id of ['save-setup','save-generate'])$('#'+id,root).disabled=busy;
  },allowNone:true});
  const redrawBack=()=>backPicker.set(s);
  function creditPreview(){
    const sample=deck.cards[0],first=sample?.faces?.[0]||{};
    const name=sample?originalArtist(sample,first)||'Original Artist':'Original Artist';
    const artist=$('#deck-artist',root).value,suffix=$('#deck-modification',root).value;
    $('#scryfall-credit-preview',root).textContent=composeCredit(name,null,artist,null,null,suffix,'scryfall');
    $('#custom-credit-preview',root).textContent=composeCredit(name,null,artist,null,null,suffix,'custom');
  }
  $('#deck-artist',root).addEventListener('input',creditPreview);$('#deck-modification',root).addEventListener('input',creditPreview);creditPreview();
  redrawSymbols();redrawBack();
  $$('input:not([type=file]),textarea,select',$('#setup-fields',root)).forEach(el=>el.addEventListener('input',mark));
  function redrawSource(){
    $$('[data-mode]',root).forEach(x=>x.classList.toggle('selected',x.dataset.mode===s.source.mode));
    $$('[data-source]',root).forEach(x=>x.classList.toggle('hidden',x.dataset.source!==s.source.mode));
    $('#fallback-line',root).classList.toggle('hidden',s.source.mode==='scryfall');
  }
  $$('[data-mode]',root).forEach(b=>b.onclick=()=>{s.source.mode=b.dataset.mode;redrawSource();mark();});
  const githubImport=mountGithubSetupImport($('#github-setup',root),{
    isBusy:()=>backPicker.isBusy()||!!$('.symbol-upload:disabled,#generate-symbols:disabled,#symbol-folder-button:disabled,#save-setup:disabled,#save-generate:disabled',root),
    onBusy:busy=>{const fields=$('#setup-fields',root);fields.disabled=busy;fields.inert=busy;},
    onImport:patch=>{
      s.source={...s.source,...patch.source};s.symbols=patch.symbols;s.backAsset=patch.backAsset;s.backDesign=patch.backDesign;s.githubSetupFolder=patch.githubSetupFolder;
      $('#github-folder',root).value=s.source.githubFolder;$('#github-ref',root).value=s.source.ref;
      $('#art-fallback',root).checked=s.source.fallback;$('#local-count',root).textContent='0 images saved for this deck.';
      redrawSource();redrawSymbols();redrawBack();mark();
    }
  });
  $('#local-art',root).onchange=()=>attempt(async()=>{const files=$('#local-art',root).files;if(!files.length)return;const b=$('#save-generate',root),saveButton=$('#save-setup',root);b.disabled=true;saveButton.disabled=true;try{s.source.localFiles=await uploadFolder(files,(n,total)=>{$('#local-count',root).textContent=`Importing artwork ${n} / ${total}…`;});$('#local-count',root).textContent=`${Object.keys(s.source.localFiles).length} images saved in this deck’s local workspace.`;mark();}finally{b.disabled=false;saveButton.disabled=false;}});
  $('#restore-symbols',root).onclick=()=>attempt(async()=>{const defaults=defaultSymbols();if(!rarities.every(r=>defaults[r]))throw new Error('Built-in rarity symbols are unavailable. Reinstall the complete application package.');s.symbols=defaults;redrawSymbols();mark();$('#symbol-folder-status',root).textContent='Using the built-in common, uncommon, rare, and mythic symbols.';});
  $('#symbol-folder-button',root).onclick=()=>$('#symbol-folder',root).click();
$('#symbol-folder',root).onchange=()=>attempt(async()=>{
  const input=$('#symbol-folder',root),files=input.files;if(!files.length)return;
  const button=$('#symbol-folder-button',root),restore=$('#restore-symbols',root),generate=$('#generate-symbols',root),save=$('#save-setup',root),render=$('#save-generate',root),status=$('#symbol-folder-status',root);
  button.disabled=true;restore.disabled=true;generate.disabled=true;save.disabled=true;render.disabled=true;
  try{
    const selected=symbolFolderFiles(files),next={};let done=0;
    for(const rarity of rarities){
      status.textContent=`Uploading set symbols ${done+1} / 4 · ${selected[rarity].name}`;
      next[rarity]=(await uploadImage(selected[rarity],{symbol:true})).id;done++;
    }
    s.symbols=next;redrawSymbols();mark();status.textContent='Loaded common, uncommon, rare, and mythic symbols from the selected folder.';
  }finally{
    input.value='';button.disabled=false;restore.disabled=false;generate.disabled=false;save.disabled=false;render.disabled=false;
  }
});
  $('#generate-symbols',root).onclick=()=>attempt(async()=>{const f=await pickFile('image/*,.svg');if(!f)return;const button=$('#generate-symbols',root);button.disabled=true;try{const a=await uploadImage(f,{symbol:true});s.symbols=await api('/api/symbols/generate',{assetId:a.id});redrawSymbols();mark();}finally{button.disabled=false;}});
  $('#open-templates',root).onclick=()=>nav('templates');
  $('#reuse-style',root).onchange=async e=>attempt(async()=>{const id=e.target.value;if(!id)return;const other=await api('/api/decks/'+id);for(const key of ['symbols','backAsset','backDesign','artist','modificationCredit','templateRules'])s[key]=structuredClone(other.settings[key]?? (key==='symbols'||key==='templateRules'?{}:key==='backDesign'?null:''));redrawSymbols();redrawBack();$('#deck-artist',root).value=s.artist;$('#deck-modification',root).value=s.modificationCredit||'';creditPreview();$$('[data-rule]',root).forEach(el=>el.innerHTML=templateOptions(el.dataset.rule,['legendary','legendary-land'].includes(el.dataset.rule),s.templateRules[el.dataset.rule]||'auto'));mark();});
  async function save(generate){
    if(githubImport.isBusy())throw new Error('Wait for the GitHub setup import to finish.');
    if(backPicker.isBusy())throw new Error('Wait for the back image to finish processing.');
    s.source.githubFolder=$('#github-folder',root).value.trim();s.source.ref=$('#github-ref',root).value.trim();s.source.fallback=$('#art-fallback',root).checked;
    s.useLandLibrary=$('#use-land-library',root).checked;s.artist=$('#deck-artist',root).value;s.modificationCredit=$('#deck-modification',root).value.trim();
    s.disableAutofit=$('#disable-autofit',root).checked;s.refreshData=$('#refresh-data',root).checked;s.flavorPolicy=$('#flavor-policy',root).value;
    $$('[data-rule]',root).forEach(el=>s.templateRules[el.dataset.rule]=el.value);
    if(generate&&!rarities.every(r=>s.symbols[r]))throw new Error('Default rarity symbols are unavailable. Restore the built-in defaults or choose replacements.');
    $('#save-setup',root).disabled=true;$('#save-generate',root).disabled=true;
    try{const d=await api('/api/decks/'+deck.id+'/save',{revision:deck.revision,name:$('#deck-name',root).value,notes:$('#deck-notes',root).value,settings:s});state.dirty=false;toast('Deck setup saved.');await onSaved(d,generate);}finally{if($('#save-setup',root))$('#save-setup',root).disabled=false;if($('#save-generate',root))$('#save-generate',root).disabled=false;}
  }
  $('#save-setup',root).onclick=()=>attempt(()=>save(false));$('#save-generate',root).onclick=()=>attempt(()=>save(true));
}
