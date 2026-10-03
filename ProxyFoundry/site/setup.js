import {ensureMetadata} from './metadata.js';
import {recordDiagnostic} from './diagnostics.js';
import {mountBackPicker} from './backs.js';
import {githubSetupSection,mountGithubSetupImport} from './github-setup.js';
import {$,$$,esc,state,api,attempt,toast,uploadImage,uploadFolder,asset,job,nav,blobRequest,modal,closeModal,errorBox} from './ui.js';
import {checkArtwork,offerDataSave} from './artwork-review.js';
import {mergeDataDocument,pickArtworkFiles,rememberFile,rememberGithub} from './artwork-files.js';
import {originalArtist,composeCredit} from './credits.js';
import {frameChoices,framePlaceholder,openFramePicker} from './frame-picker.js';
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
  const s=structuredClone(deck.settings),groups={};let stagedCardData=structuredClone(deck.cardData||[]),dataJsonImportNote='';
  s.dataJsonSource=s.dataJsonSource&&typeof s.dataJsonSource==='object'?structuredClone(s.dataJsonSource):null;s.source={mode:'scryfall',githubFolder:'',ref:'',fallback:false,localFiles:{},...s.source};s.symbols={...s.symbols};s.templateRules={...s.templateRules};s.allCardsTokens=Boolean(s.allCardsTokens);s.tokenOptions={power:'',toughness:'',subtypes:'',nonlegendary:false,...s.tokenOptions};
  for(const c of deck.cards)for(const f of c.faces){const g=f.group||f.compiled?.group||'standard';groups[g]=(groups[g]||0)+1;}
  if(deck.pendingImport){for(const key of Object.keys(groups))delete groups[key];for(const group of ['standard','legendary','land','legendary-land','basic-land','token','saga'])groups[group]=null;}
  root.innerHTML=githubSetupSection(s.githubSetupFolder||'')+`<fieldset class="setup-fields" id="setup-fields" aria-label="Deck setup"><div class="setup-columns"><div>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">01 / ARTWORK</span><h2>Choose where the art comes from</h2><p>Your Scryfall deck’s exact printing is kept—not replaced with a random version.</p></div></div>
      <div class="source-choices"><button class="choice ${s.source.mode==='scryfall'?'selected':''}" data-mode="scryfall"><span class="choice-symbol">▧</span><b>Scryfall printing</b><span>Use the art already selected in your deck.</span></button><button class="choice ${s.source.mode==='github'?'selected':''}" data-mode="github"><span class="choice-symbol">⌘</span><b>GitHub folder</b><span>Paste a folder link. No local repository needed.</span></button><button class="choice ${s.source.mode==='local'?'selected':''}" data-mode="local"><span class="choice-symbol">▱</span><b>Computer folder</b><span>Choose your artwork directly from this device.</span></button></div>
      <div data-source="scryfall" class="${s.source.mode==='scryfall'?'':'hidden'}"><div class="notice info">Use any real paper printing. The selected set and collector number are preserved, and each card’s art can still be replaced individually.</div></div>
      <div data-source="github" class="${s.source.mode==='github'?'':'hidden'}"><label class="field"><span>GitHub artwork folder</span><input id="github-folder" value="${esc(s.source.githubFolder)}" placeholder="https://github.com/you/cards/tree/main/my_deck"><small>Names should match cards, for example <code>the_world_tree.png</code>. Apostrophes are removed; spaces become underscores.</small></label><label class="field"><span>Branch or commit override <small>optional</small></span><input id="github-ref" value="${esc(s.source.ref||'')}" placeholder="Use the ref from the URL"></label></div>
      <div data-source="local" class="${s.source.mode==='local'?'':'hidden'}"><label class="field"><span>Choose the artwork folder</span><input type="file" id="local-art" webkitdirectory directory multiple><small id="local-count">${Object.keys(s.source.localFiles||{}).length} images saved for this deck. Files stay in your local workspace; they are not uploaded to GitHub.</small></label></div>
      <label class="check-line ${s.source.mode==='scryfall'?'hidden':''}" id="fallback-line"><input type="checkbox" id="art-fallback" ${s.source.fallback?'checked':''}><span>Use Scryfall artwork when a custom image is missing<small>Turn off to require matching custom art for every card.</small></span></label>
    </section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">02 / TEMPLATES</span><h2>Select Templates</h2></div></div>
      <div id="frame-choices"></div>
      <details><summary>Template safety & advanced options</summary><p class="muted">Special layouts are recognized separately. When the approved recipes do not cover one, choose a compatible custom template; the app will never substitute an incorrect ordinary frame.</p><label class="check-line"><input type="checkbox" id="disable-autofit" ${s.disableAutofit?'checked':''}><span>Keep template art positioning instead of automatic fitting<small>Leave off for the normal cover/center crop behavior.</small></span></label></details>
    </section>
  </div><div>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">03 / SET SYMBOLS</span><h2>Set Symbols</h2></div></div><div class="symbol-grid" id="symbol-grid"></div><div class="actions"><button class="button small" id="symbol-folder-button">From Computer · four images</button><input type="file" id="symbol-folder" webkitdirectory directory multiple accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,.svg" hidden></div><small id="symbol-folder-status" role="status"></small></section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">04 / CARD BACK</span><h2>Card Back</h2></div></div><div id="back-designer"></div></section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">05 / DETAILS</span><h2>Credit the artist</h2></div></div><label class="field"><span>Artist for custom artwork in this deck</span><input id="deck-artist" value="${esc(s.artist||'')}" placeholder="Artist name for your custom artwork"><small>Used only for custom artwork. Scryfall originals and fallback images always keep the real printing artist. If you leave this blank, Generate images will ask whether one artist applies to all custom art or whether you want to enter artists per card.</small></label><div class="credit-preview" aria-live="polite"><span class="eyebrow">EXAMPLE ARTIST LINES</span><small>Scryfall artwork</small><strong id="scryfall-credit-preview"></strong><small>Custom artwork</small><strong id="custom-credit-preview"></strong></div><label class="field"><span>Deck name</span><input id="deck-name" maxlength="200" value="${esc(deck.name)}"></label><label class="field"><span>Notes <small>only visible here</small></span><textarea id="deck-notes" rows="3">${esc(deck.notes||'')}</textarea></label>
      <label class="field"><span>Reuse style from another deck</span><select id="reuse-style"><option value="">Choose a deck…</option>${state.decks.filter(d=>d.id!==deck.id).map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join('')}</select><small>Copies its symbols, back, artist credit and template choices—not its card list or artwork folder.</small></label>
      <label class="field"><span>Flavor text source</span><select id="flavor-policy"><option value="auto" ${(!s.flavorPolicy||s.flavorPolicy==='auto')?'selected':''}>Automatic · preserve exact printings</option><option value="resolved" ${s.flavorPolicy==='resolved'?'selected':''}>Selected printing</option><option value="latest" ${s.flavorPolicy==='latest'?'selected':''}>Latest English paper printing</option></select><small>Only flavor text changes. The selected card printing and artwork remain unchanged.</small></label><label class="check-line"><input type="checkbox" id="refresh-data" ${s.refreshData?'checked':''}><span>Fetch new data when the cached copy is at least one week old<small>Normal mode reuses Scryfall data for one year. This does not refetch every time.</small></span></label>
    </section>
    <section class="panel" id="data-json-section"><div class="panel-head"><div><span class="eyebrow">06 / DATA.JSON</span><h2>Nicknames &amp; flavor text</h2><p>Optionally apply per-card nicknames and flavor text without editing cards one at a time.</p></div></div>
      <label class="field"><span>Import data.json <small>optional</small></span><input type="file" id="data-json-file" accept=".json,application/json"><small>The 1-click GitHub import also checks the project root for <code>data.json</code> automatically. Names must exactly match card faces. Empty nickname or flavor values are ignored.</small></label>
      <div class="notice info" id="data-json-status"></div>
      <div class="well"><small><b>Format</b><br><code>{"version":1,"cards":[{"name":"Sol Ring","nickname":"The Colt","flavor_text":"Custom flavor text."}]}</code></small></div>
    </section>
    <section class="panel"><div class="panel-head"><div><span class="eyebrow">07 / OTHER OPTIONS</span><h2>Other Options</h2><p>Apply optional deck-wide transformations before the cards are rendered.</p></div></div>
      <label class="check-line"><input type="checkbox" id="all-cards-tokens" ${s.allCardsTokens?'checked':''}><span>Make all cards tokens<small>Uses the existing M15 token-frame conversion for every card face in this deck.</small></span></label>
      <div id="all-token-options" class="${s.allCardsTokens?'':'hidden'}">
        <label class="field"><span>Power override <small>optional</small></span><input id="token-power" maxlength="20" value="${esc(s.tokenOptions.power||'')}" placeholder="Keep each card’s power"><small>Blank leaves each card’s original power unchanged.</small></label>
        <label class="field"><span>Toughness override <small>optional</small></span><input id="token-toughness" maxlength="20" value="${esc(s.tokenOptions.toughness||'')}" placeholder="Keep each card’s toughness"><small>Blank leaves each card’s original toughness unchanged.</small></label>
        <label class="field"><span>Subtype override <small>optional</small></span><input id="token-subtypes" maxlength="200" value="${esc(s.tokenOptions.subtypes||'')}" placeholder="e.g. Illusion"><small>When nonblank, replaces the complete subtype list on every token.</small></label>
        <label class="check-line"><input type="checkbox" id="token-nonlegendary" ${s.tokenOptions.nonlegendary?'checked':''}><span>Make nonlegendary<small>Removes Legendary from the supertype when it is present.</small></span></label>
      </div>
    </section>
  </div></div><div class="setup-save"><span class="save-status" id="setup-state">Changes saved</span><button class="button primary" id="save-generate">Generate images</button></div></fieldset>`;
  $('#disable-autofit',root).closest('details').remove();
  for(const id of ['deck-name','deck-notes','reuse-style','flavor-policy','refresh-data'])$('#'+id,root).closest('label').remove();
  $('.credit-preview',root)?.remove();
  const sourceCaption=$('[data-source="github"] small',root);
  if(sourceCaption)sourceCaption.textContent='Name images after the card; The World Tree.png and the_world_tree.png both work.';
  $('[data-source="scryfall"]',root).replaceChildren();
  $('#fallback-line small',root)?.remove();
  $('#fallback-line span',root).textContent='Use Scryfall artwork when custom art is missing';
  $('#local-count',root).textContent=Object.keys(s.source.localFiles||{}).length+' images selected';
  $('#github-ref',root)?.closest('label').remove();
  $('#deck-artist',root).placeholder='Artist name when one artist applies to the custom artwork';
  const legendaryLabel=$('#token-nonlegendary',root).closest('label');
  const legendarySelect=document.createElement('select');legendarySelect.id='token-legendary-mode';
  for(const [value,label] of [['nonlegendary','Nonlegendary'],['original','Original'],['legendary','Legendary']]){
    const option=document.createElement('option');option.value=value;option.textContent=label;legendarySelect.append(option);
  }
  legendarySelect.value=s.tokenOptions.legendaryMode||(s.tokenOptions.nonlegendary?'nonlegendary':'original');
  legendaryLabel.replaceWith(legendarySelect);
  const tokenFrameLabel=document.createElement('label');tokenFrameLabel.className='field';
  const tokenFrameTitle=document.createElement('span');tokenFrameTitle.textContent='Token frame';
  const tokenFrame=document.createElement('select');tokenFrame.id='token-frame';
  for(const [value,label] of [['auto','Automatic token frame'],['token-classic','Classic arched token'],['token-full-art','Modern full-art token'],['token-borderless','Modern borderless token'],['godzilla-card','Godzilla full art token']]){
    const option=document.createElement('option');option.value=value;option.textContent=label;tokenFrame.append(option);
  }
  tokenFrame.value=s.templateRules.token||'auto';tokenFrameLabel.append(tokenFrameTitle,tokenFrame);
  $('#all-token-options',root).prepend(tokenFrameLabel);
  const artistPanel=$('#deck-artist',root).closest('section');
  artistPanel.querySelector('h2').textContent='Artist credits, nicknames & flavor text';
  $('#deck-artist',root).closest('label').querySelector('small').textContent='Used for custom art unless a card has its own credit.';
  const sourcePanel=$('[data-mode="scryfall"]',root).closest('section');
  sourcePanel.querySelector('.panel-head p').remove();
  $('[data-mode="scryfall"] span:last-child',root).textContent='Use the art already selected in your deck.';
  $('[data-mode="github"] span:last-child',root).textContent='Use images in a public GitHub folder.';
  $('[data-mode="local"] span:last-child',root).textContent='Choose artwork from this device.';
  const symbolPanel=$('#symbol-grid',root).closest('section');
  const symbolModes=document.createElement('div');symbolModes.className='source-choices';
  const symbolComputer=document.createElement('button');symbolComputer.type='button';symbolComputer.className='choice selected';symbolComputer.textContent='From Computer';
  const symbolGithub=document.createElement('button');symbolGithub.type='button';symbolGithub.className='choice';symbolGithub.textContent='From GitHub';
  symbolModes.append(symbolComputer,symbolGithub);symbolPanel.querySelector('.panel-head').after(symbolModes);
  const symbolGithubFields=document.createElement('div');symbolGithubFields.className='field';symbolGithubFields.style.display='none';
  const symbolGithubInput=document.createElement('input');symbolGithubInput.type='url';symbolGithubInput.placeholder='https://github.com/you/repo/tree/main/set_symbols';symbolGithubInput.id='symbol-github-folder';
  const symbolGithubImport=document.createElement('button');symbolGithubImport.type='button';symbolGithubImport.className='button small';symbolGithubImport.textContent='Import four symbols';
  symbolGithubFields.append(symbolGithubInput,symbolGithubImport);symbolPanel.append(symbolGithubFields);
  symbolComputer.onclick=()=>{symbolComputer.classList.add('selected');symbolGithub.classList.remove('selected');symbolGithubFields.style.display='none';$('#symbol-folder-button',root).style.display='';};
  symbolGithub.onclick=()=>{symbolGithub.classList.add('selected');symbolComputer.classList.remove('selected');symbolGithubFields.style.display='';$('#symbol-folder-button',root).style.display='none';};
  const otherPanel=$('#all-cards-tokens',root).closest('section');
  otherPanel.querySelector('#all-cards-tokens + span small')?.remove();
  const flavorLine=document.createElement('label');flavorLine.className='check-line';
  const flavorToggle=document.createElement('input');flavorToggle.type='checkbox';flavorToggle.id='show-flavor-text';flavorToggle.checked=s.showFlavorText!==false;
  const flavorLabel=document.createElement('span');flavorLabel.textContent='Show flavor text';
  flavorLine.append(flavorToggle,flavorLabel);$('#all-cards-tokens',root).closest('label').before(flavorLine);
  const columns=$('.setup-columns',root);
  const panels=$$('.setup-columns > div > section',root);
  columns.replaceChildren(...panels);
  Object.assign(columns.style,{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,max(420px,calc((100% - 20px)/2))),1fr))',alignItems:'start',gap:'20px'});
  for(const panel of panels){
    panel.style.margin='0';
    panel.style.minWidth='0';
    panel.style.scrollMarginBottom='120px';
  }

  for(const panel of [sourcePanel,$('#frame-choices',root).closest('section'),artistPanel,otherPanel]){
    panel.style.gridColumn='1 / -1';
  }

  artistPanel.querySelector('h2').textContent='Card Details';
  otherPanel.querySelector('.eyebrow').textContent='06 / OTHER OPTIONS';
  otherPanel.querySelector('.panel-head p').remove();
  Object.assign($('.setup-save',root).style,{bottom:'0',marginTop:'20px'});
  $('#setup-fields',root).style.paddingBottom='24px';
  const byCard=document.createElement('button');byCard.type='button';byCard.className='button small';byCard.textContent='Specify artist by card';
  $('#deck-artist',root).closest('label').after(byCard);
  const importedData=$('#data-json-section',root);
  artistPanel.append(importedData);
  importedData.querySelector('.eyebrow').remove();
  Object.assign(importedData.style,{background:'none',boxShadow:'none',border:'none',borderTop:'1px solid var(--line)',borderRadius:'0',padding:'20px 0 0',margin:'20px 0 0'});
  const localDataButton=document.createElement('button');
  localDataButton.type='button';
  localDataButton.id='open-card-data';
  localDataButton.className='button small';
  localDataButton.textContent='Open data.json file';
  $('#data-json-section',root).append(localDataButton);
  const urlLabel=document.createElement('label');
  urlLabel.className='field';
  const urlText=document.createElement('span');
  urlText.textContent='GitHub data.json file link';
  const dataUrl=document.createElement('input');
  dataUrl.type='url';
  dataUrl.id='card-data-url';
  dataUrl.placeholder='https://github.com/you/cards/blob/main/project/data.json';
  urlLabel.append(urlText,dataUrl);
  $('#data-json-section',root).append(urlLabel);
  const linkDataButton=document.createElement('button');
  linkDataButton.type='button';
  linkDataButton.id='import-card-data-url';
  linkDataButton.className='button small';
  linkDataButton.textContent='Import linked data.json';
  $('#data-json-section',root).append(linkDataButton);
  const dataStatus=document.createElement('p');
  dataStatus.id='card-data-status';
  dataStatus.setAttribute('role','status');
  dataStatus.hidden=true;
  $('#data-json-section',root).append(dataStatus);
  $('#data-json-section .panel-head p',root).remove();
  $('#data-json-section h2',root).textContent='Card data & artwork mappings';
  $('#data-json-section .well code',root).textContent=JSON.stringify({version:1,artist:'Deck Artist',cards:[{name:'Sol Ring',nickname:'The Colt',flavor_text:'Custom flavor text.',artist:'Artist Name'}]},null,2);
  $('#data-json-section .well code',root).style.whiteSpace='pre-wrap';
  const formatHelp=document.createElement('details');
  const formatTitle=document.createElement('summary');
  formatTitle.textContent='Format help';
  formatHelp.append(formatTitle,$('#data-json-section .well',root));
  formatHelp.style.marginTop='20px';
  $('#data-json-file',root).closest('label').style.display='none';
  linkDataButton.style.display='none';
  const dataModes=document.createElement('div');dataModes.className='source-choices';
  const computerMode=document.createElement('button');computerMode.type='button';computerMode.className='choice selected';computerMode.textContent='From Computer';
  const githubMode=document.createElement('button');githubMode.type='button';githubMode.className='choice';githubMode.textContent='From GitHub';
  dataModes.append(computerMode,githubMode);$('#data-json-section .panel-head',root).after(dataModes);
  importedData.append(formatHelp);
  urlLabel.style.display='none';
  computerMode.onclick=()=>{computerMode.classList.add('selected');githubMode.classList.remove('selected');localDataButton.style.display='';urlLabel.style.display='none';};
  githubMode.onclick=()=>{githubMode.classList.add('selected');computerMode.classList.remove('selected');localDataButton.style.display='none';urlLabel.style.display='';};
  dataUrl.addEventListener('change',()=>{if(dataUrl.value.trim())linkDataButton.click();});
  let changeVersion=0,persistedVersion=0,saveTimer=null,saveQueue=Promise.resolve();
  const mark=()=>{changeVersion++;state.dirty=true;$('#setup-state',root).textContent='Saving changes…';clearTimeout(saveTimer);saveTimer=setTimeout(()=>attempt(()=>persistSetup()),400);};
  byCard.onclick=()=>attempt(async()=>{
    refreshMetadata(await ensureMetadata(deck.id));
    s.artist=$('#deck-artist',root).value.trim();
    const previews=await api('/api/setup/custom-art-previews',{deckId:deck.id,settings:s});
    const host=modal('Artist credits by card','',{size:'large',footer:'<button class="button primary" id="save-artists">Apply credits</button>'});
    const body=$('.modal-body',host);
    if(!previews.length){body.textContent='No custom artwork is selected for this deck.';return;}
    const grid=document.createElement('div');grid.className='pair-grid';body.append(grid);
    for(const item of previews){
      const tile=document.createElement('label');tile.className='well field';
      const image=document.createElement('img');image.src=asset(item.assetId);image.alt=item.name+' custom artwork';image.style.cssText='max-height:240px;max-width:100%;object-fit:contain';
      const title=document.createElement('span');title.textContent=item.name;
      const input=document.createElement('input');input.maxLength=300;input.placeholder='Artist name';
      input.value=stagedCardData.find(x=>x.name===item.name)?.artist||item.artist||s.artist;
      input.dataset.artistFace=item.faceId;input.dataset.artistName=item.name;
      tile.append(image,title,input);grid.append(tile);
    }
    $('#save-artists',host).onclick=()=>{
      const inputs=$$('[data-artist-face]',host);
      const empty=inputs.find(input=>!input.value.trim());
      if(empty){empty.focus();empty.style.borderColor='#d85e56';errorBox(body,'Enter an artist for '+empty.dataset.artistName+'.');return;}
      for(const input of inputs){
        const name=input.dataset.artistName;
        let entry=stagedCardData.find(item=>item.name===name);
        if(!entry){entry={name};stagedCardData.push(entry);}
        entry.artist=input.value.trim();
      }
      closeModal();mark();toast('Artist credits imported.');
    };
  });
  const applyDataArtist=settings=>{
    if(settings&&Object.hasOwn(settings,'artist')){
      s.artist=settings.artist;$('#deck-artist',root).value=s.artist;
    }
  };
  const stageCardData=(entries,source,settings)=>{
    applyDataArtist(settings);
    pairedChanges=[];
    s.artReviewSignature='';
    stagedCardData=structuredClone(entries);
    s.dataJsonSource=source;
    dataJsonImportNote='';
    dataStatus.textContent=(source?.kind==='github'?'GitHub data.json: ':'Local data.json: ')+entries.length+' nonempty card entr'+(entries.length===1?'y':'ies')+' imported.';
    dataStatus.hidden=false;
    redrawDataJsonStatus();
    (source?.kind==='github'?githubMode:computerMode).onclick();
    mark();
  };
  localDataButton.onclick=()=>attempt(async()=>{
    if(!window.showOpenFilePicker){$('#data-json-file',root).click();return;}
    let handle;
    try{[handle]=await window.showOpenFilePicker({types:[{description:'Card data',accept:{'application/json':['.json']}}],multiple:false});}
    catch(error){if(error.name==='AbortError')return;throw error;}
    const file=await handle.getFile();
    const result=await blobRequest('/api/setup/card-data/file?deckId='+encodeURIComponent(deck.id),file,'application/json');
    await rememberFile(deck.id,handle,JSON.parse(await file.text()));
    stageCardData(result.cardData,{kind:'local',value:file.name},result.settings);
  });
  linkDataButton.onclick=()=>attempt(async()=>{
    if(!dataUrl.value.trim())throw new Error('Paste a GitHub data.json file link.');
    linkDataButton.disabled=true;
    try{
      const result=await api('/api/setup/card-data/github',{deckId:deck.id,url:dataUrl.value.trim()});
      stageCardData(result.cardData,{kind:'github',value:dataUrl.value.trim()},result.settings);
      await rememberGithub(deck.id,dataUrl.value.trim(),result.document||{version:1,cards:result.cardData});
    }finally{linkDataButton.disabled=false;}
  });
  const redrawFrames=()=>{
    const host=$('#frame-choices',root);
    host.replaceChildren();
    if(!Object.keys(groups).length){
      const empty=document.createElement('p');
      empty.textContent='Add cards first. Their layout groups will appear here.';
      host.append(empty);
      return;
    }
    const body=document.createElement('div');
    body.className='pair-grid';
    Object.assign(body.style,{maxHeight:'none',overflow:'visible',gridTemplateColumns:'repeat(auto-fill,minmax(min(100%,210px),1fr))'});
    for(const [group,count] of Object.entries(groups)){
      const row=document.createElement('article');row.className='well';
      const layout=document.createElement('h3');
      layout.textContent=(state.bootstrap.groups[group]||group)+' · '+(count===null?'Details loading':count);
      const selected=s.templateRules[group]||'auto';
      const picture=document.createElement('img');
      picture.alt='Current '+(state.bootstrap.groups[group]||group)+' frame preview';
      picture.style.cssText='height:220px;max-width:100%;object-fit:contain;display:block;margin:12px auto';
      picture.src=framePlaceholder(s);
      picture.alt='Card back placeholder for '+(state.bootstrap.groups[group]||group);
      const button=document.createElement('button');
      button.type='button';
      button.className='button small';
      button.dataset.frameGroup=group;
      button.textContent='Change Frame';
      button.onclick=()=>attempt(async()=>{
        readSettings();
        openFramePicker(deck,group,s,stagedCardData,selected,choice=>{
          s.templateRules[group]=choice;
          if(group==='token')tokenFrame.value=choice;
          redrawFrames();
          mark();
        });
      });
      row.append(layout,picture,document.createTextNode((frameChoices(group,['legendary','legendary-land'].includes(group)).find(item=>item.id===selected)?.name||selected)+' '),button);
      body.append(row);
    }
    host.append(body);
  };
  const metadataStatus=document.createElement('p');metadataStatus.setAttribute('role','status');metadataStatus.id='deck-metadata-status';
  metadataStatus.textContent='Reading card details in the background. You can choose your art and options now. Images will be generated after you finish your choices.';
  metadataStatus.hidden=!deck.pendingImport;
  $('.setup-columns',root).before(metadataStatus);
  function refreshMetadata(updated){
    deck.cards=updated.cards;deck.revision=Math.max(deck.revision,updated.revision);delete deck.pendingImport;
    for(const group of Object.keys(groups))delete groups[group];
    for(const card of deck.cards){
      for(const face of card.faces){const group=face.group||'standard';groups[group]=(groups[group]||0)+1;}
    }
    redrawFrames();metadataStatus.textContent='Card details are ready. Images start when you choose Generate Images.';
  }
  redrawFrames();
  tokenFrame.addEventListener('input',()=>{s.templateRules.token=tokenFrame.value;redrawFrames();});
  const redrawSymbols=()=>{$('#symbol-grid',root).innerHTML=rarities.map(r=>`<button class="symbol-upload ${s.symbols[r]?'has-image':''}" data-symbol="${r}" aria-label="Upload ${r} set symbol">${s.symbols[r]?`<img src="${asset(s.symbols[r])}" alt="${r} set symbol">`:'<span class="symbol-empty">◇</span>'}<small>${r}</small></button>`).join('');$$('[data-symbol]',root).forEach(b=>b.onclick=()=>attempt(async()=>{const f=await pickFile('image/*,.svg');if(!f)return;b.disabled=true;const a=await uploadImage(f,{symbol:true});s.symbols[b.dataset.symbol]=a.id;s.symbolsSource=null;symbolComputer.click();redrawSymbols();mark();}));};
  const backPicker=mountBackPicker($('#back-designer',root),s,choice=>{
    s.backAsset=choice.backAsset;s.backDesign=choice.backDesign;redrawFrames();mark();
  },{onBusy:busy=>{
    for(const id of ['save-generate','generate-deck'])($('#'+id,root)||$('#'+id)).disabled=busy;
  },allowNone:true});
  const redrawBack=()=>backPicker.set(s);
  function creditPreview(){
    const sample=deck.cards[0],first=sample?.faces?.[0]||{};
    const name=sample?originalArtist(sample,first)||'Original Artist':'Original Artist';
    const artist=$('#deck-artist',root).value;
    $('#scryfall-credit-preview',root).textContent=composeCredit(name,null,artist,null,'scryfall');
    $('#custom-credit-preview',root).textContent=composeCredit(name,null,artist,null,'custom');
  }
  $('#deck-artist',root).addEventListener('input',mark);
  redrawSymbols();redrawBack();
  $$('input:not([type=file]),textarea,select',$('#setup-fields',root)).forEach(el=>el.addEventListener('input',mark));
  const redrawDataJsonStatus=()=>{const status=$('#data-json-status',root);if(!status)return;status.textContent=s.dataJsonSource?.value||dataJsonImportNote||'';status.hidden=!status.textContent;};
  redrawDataJsonStatus();
  (s.dataJsonSource?.kind==='github'?githubMode:computerMode).onclick();
  symbolGithubInput.value=s.symbolsSource?.value||'';
  (s.symbolsSource?.kind==='github'?symbolGithub:symbolComputer).onclick();
  $('#data-json-file',root).onchange=()=>attempt(async()=>{const input=$('#data-json-file',root),file=input.files[0];if(!file)return;try{const result=await blobRequest('/api/setup/card-data/file?deckId='+encodeURIComponent(deck.id),file,'application/json');await rememberFile(deck.id,null,JSON.parse(await file.text()));stageCardData(result.cardData,{kind:'local',value:file.name||'data.json'},result.settings);}finally{input.value='';}});
  const redrawTokenOptions=()=>$('#all-token-options',root).classList.toggle('hidden',!$('#all-cards-tokens',root).checked);
  $('#all-cards-tokens',root).addEventListener('change',redrawTokenOptions);redrawTokenOptions();
  function redrawSource(){
    $$('[data-mode]',root).forEach(x=>x.classList.toggle('selected',x.dataset.mode===s.source.mode));
    $$('[data-source]',root).forEach(x=>x.classList.toggle('hidden',x.dataset.source!==s.source.mode));
    $('#fallback-line',root).classList.toggle('hidden',s.source.mode==='scryfall');
  }
  $$('[data-mode]',root).forEach(b=>b.onclick=()=>{s.source.mode=b.dataset.mode;redrawSource();mark();});
  const githubImport=mountGithubSetupImport($('#github-setup',root),{
    isBusy:()=>backPicker.isBusy()||!!$('.symbol-upload:disabled,#symbol-folder-button:disabled,#save-generate:disabled',root),
    onBusy:busy=>{const fields=$('#setup-fields',root);fields.disabled=busy;fields.inert=busy;},
    deckId:deck.id,
    onImport:async(patch,cardData,hasDataJson,document)=>{
      applyDataArtist(patch);
      pairedChanges=[];s.artDefaults=[];s.artReviewSignature='';
      await rememberGithub(deck.id,patch.githubSetupFolder,document||{version:1,cards:cardData||[]});
      if(hasDataJson){
        stagedCardData=structuredClone(cardData||[]);
        s.dataJsonSource=patch.dataJsonSource||null;
        dataJsonImportNote='';
        dataStatus.textContent='1-click GitHub data.json: '+stagedCardData.length+' card entries imported.';
      }else if(!stagedCardData.length){
        s.dataJsonSource=null;
        dataJsonImportNote='No data.json found in the GitHub project root.';
      }
      redrawDataJsonStatus();
      (s.dataJsonSource?.kind==='github'?githubMode:computerMode).onclick();
      s.symbolsSource=patch.symbolsSource||null;
      symbolGithubInput.value=s.symbolsSource?.value||'';
      (s.symbolsSource?.kind==='github'?symbolGithub:symbolComputer).onclick();
      s.source={...s.source,...patch.source};s.symbols=patch.symbols;s.backAsset=patch.backAsset;s.backDesign=patch.backDesign;s.githubSetupFolder=patch.githubSetupFolder;
      $('#github-folder',root).value=s.source.githubFolder;
      $('#art-fallback',root).checked=s.source.fallback;$('#local-count',root).textContent='0 images saved for this deck.';
      redrawSource();redrawSymbols();redrawBack();redrawFrames();mark();await persistSetup(true);
    }
  });
  let importingArtwork=false;
  const importArtwork=async files=>{
    if(!files?.length)return;
    if(importingArtwork)throw new Error('Artwork import is already running.');
    importingArtwork=true;
    try{
    const data=[...files].find(file=>(file.artworkPath||file.webkitRelativePath?.split('/').slice(1).join('/')||file.name)==='data.json');
    if(data){const result=await blobRequest('/api/setup/card-data/file?deckId='+encodeURIComponent(deck.id),data,'application/json');await rememberFile(deck.id,data.sourceHandle||null,JSON.parse(await data.text()),'folder');stageCardData(result.cardData,{kind:'local',value:'data.json'},result.settings);}
    s.source.localFiles=await uploadFolder(files,(n,total)=>{$('#local-count',root).textContent=`Importing artwork ${n} / ${total}…`;},s.source);
    s.artDefaults=[];s.artReviewSignature='';
    $('#local-count',root).textContent=`${Object.keys(s.source.localFiles).length} images saved in this deck’s local workspace.`;mark();
    }finally{importingArtwork=false;}
  };
  $('#local-art',root).onchange=()=>attempt(()=>importArtwork($('#local-art',root).files));
  if(window.showDirectoryPicker){
    const folderButton=document.createElement('button');folderButton.type='button';folderButton.className='button';folderButton.textContent='Choose artwork folder';
    $('#local-art',root).hidden=true;$('#local-art',root).after(folderButton);
    folderButton.onclick=()=>attempt(async()=>{let files;try{files=await pickArtworkFiles(deck.id);}catch(error){if(error.name==='AbortError')return;throw error;}await importArtwork(files);});
  }
  let pairedChanges=[];
  const reviewArtwork=async()=>{
    refreshMetadata(await ensureMetadata(deck.id));
    readSettings();
    const result=await checkArtwork(deck,s,stagedCardData,async()=>{
      if(s.source.mode==='github')return;
      const files=await pickArtworkFiles(deck.id);
      if(!files)throw new Error('Return to setup to add images in this browser.');
      await importArtwork(files);
    });
    if(!result)return false;
    s.artDefaults=result.defaults;s.artReviewSignature=result.signature;
    stagedCardData=mergeDataDocument({version:1,cards:stagedCardData},result.changes).cards;
    pairedChanges=mergeDataDocument({version:1,cards:pairedChanges},result.changes).cards;
    if(result.changes.length)mark();
    return true;
  };
  const reviewButton=document.createElement('button');reviewButton.type='button';reviewButton.className='button';reviewButton.textContent='Match custom artwork';reviewButton.id='review-artwork';
  $('#local-count',root).closest('section').append(reviewButton);reviewButton.onclick=()=>attempt(async()=>{if(await reviewArtwork()){mark();await persistSetup();await exportPairs();}});
  $('#symbol-folder-button',root).onclick=()=>$('#symbol-folder',root).click();
$('#symbol-folder',root).onchange=()=>attempt(async()=>{
  const input=$('#symbol-folder',root),files=input.files;if(!files.length)return;
  const button=$('#symbol-folder-button',root),save=$('#generate-deck'),render=$('#save-generate',root),status=$('#symbol-folder-status',root);
  button.disabled=true;save.disabled=true;render.disabled=true;
  try{
    const selected=symbolFolderFiles(files),next={};let done=0;
    for(const rarity of rarities){
      status.textContent=`Uploading set symbols ${done+1} / 4 · ${selected[rarity].name}`;
      next[rarity]=(await uploadImage(selected[rarity],{symbol:true})).id;done++;
    }
    s.symbols=next;s.symbolsSource=null;symbolComputer.click();redrawSymbols();mark();status.textContent='Loaded common, uncommon, rare, and mythic symbols from the selected folder.';
  }finally{
    input.value='';button.disabled=false;save.disabled=false;render.disabled=false;
  }
});
  symbolGithubImport.onclick=()=>attempt(async()=>{
    const url=symbolGithubInput.value.trim();if(!url)throw new Error('Paste a GitHub set-symbol folder link.');
    symbolGithubImport.disabled=true;
    try{
      const result=await job('/api/setup/symbols/github',{url},{label:'Import set symbols'});
      s.symbols=result.symbols;s.symbolsSource={kind:'github',value:url};symbolGithub.click();redrawSymbols();mark();toast('Four rarity symbols imported.');
    }finally{symbolGithubImport.disabled=false;}
  });
  function readSettings(){
    s.source.githubFolder=$('#github-folder',root).value.trim();s.source.fallback=$('#art-fallback',root).checked;
    s.artist=$('#deck-artist',root).value;
    s.showFlavorText=$('#show-flavor-text',root).checked;
    s.allCardsTokens=$('#all-cards-tokens',root).checked;
    s.tokenOptions={
      power:$('#token-power',root).value.trim(),
      toughness:$('#token-toughness',root).value.trim(),
      subtypes:$('#token-subtypes',root).value.trim(),
      nonlegendary:$('#token-legendary-mode',root).value==='nonlegendary',
      legendaryMode:$('#token-legendary-mode',root).value
    };
  }
  function persistSetup(importComplete=false){
    clearTimeout(saveTimer);
    const operation=async()=>{
      if(persistedVersion===changeVersion)return deck;
      if(githubImport.isBusy()&&!importComplete){saveTimer=setTimeout(()=>attempt(()=>persistSetup()),400);return deck;}
      if(importingArtwork||backPicker.isBusy()){
        await new Promise(resolve=>setTimeout(resolve,100));return operation();
      }
      readSettings();
      const version=changeVersion;
      const updated=await api('/api/decks/'+deck.id+'/save',{revision:deck.revision,settings:structuredClone(s),cardData:structuredClone(stagedCardData)});
      if(updated.revision>=deck.revision)Object.assign(deck,updated);persistedVersion=version;
      if(state.activeDeck?.id===deck.id)state.activeDeck=deck;
      if(state.setupActions?.root===root)state.dirty=persistedVersion!==changeVersion;
      if(root.isConnected)$('#setup-state',root).textContent=state.dirty?'Saving changes…':'Changes saved';
      return deck;
    };
    saveQueue=saveQueue.catch(error=>console.error("Previous setup save failed",error)).then(operation).catch(error=>{if(root.isConnected)$('#setup-state',root).textContent='Could not save changes: '+error.message;throw error;});
    return saveQueue;
  }
  async function exportPairs(){
    await offerDataSave(deck.id,pairedChanges,{version:1,cards:deck.cardData||[]},s.dataJsonSource?.kind==='github'?s.dataJsonSource.value?.startsWith('https:')?s.dataJsonSource.value:s.githubSetupFolder:s.source.mode==='github'?s.githubSetupFolder||s.source.githubFolder:'',deck.cards);pairedChanges=[];
  }
  let generating=false;
  async function generate(){
    if(generating)return;
    if(importingArtwork||githubImport.isBusy()||backPicker.isBusy())throw new Error('An import is still finishing. Its progress is shown in Art & Setup.');
    generating=true;
    const buttons=[$('#save-generate',root),$('#generate-deck')].filter(Boolean);
    try{
    if(!await githubImport.ensureImported(s.githubSetupFolder))return;
    for(const button of buttons){button.disabled=true;}
    readSettings();
    recordDiagnostic('generation setup',JSON.stringify({deckId:deck.id,sourceMode:s.source.mode,githubFolder:s.source.githubFolder,githubSetupFolder:s.githubSetupFolder||'',customArtistSet:!!s.artist.trim(),fallback:s.source.fallback}));
    mark();await persistSetup();
    refreshMetadata(await ensureMetadata(deck.id));
    if(!await reviewArtwork())return;
    if(!rarities.every(r=>s.symbols[r]))throw new Error('Upload all four rarity symbols individually, upload a correctly named four-image folder, or use Generate four from one image.');
    mark();await persistSetup();await exportPairs();await onSaved(deck,true);
    }finally{generating=false;for(const button of buttons){if(button.isConnected)button.disabled=false;}}
  }
  const actions={deckId:deck.id,root,flush:persistSetup,generate,refreshMetadata,
    metadataProgress:progress=>{metadataStatus.textContent=progress.message+(progress.total?' · '+progress.done+' / '+progress.total:'');},
    metadataError:error=>{metadataStatus.textContent='Card details could not finish: '+error.message+' Generate Images will retry.';}
  };state.setupActions=actions;
  $('#save-generate',root).onclick=()=>attempt(generate);
  return actions;
}
