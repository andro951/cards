(() => {
  const VERSION = '1.0.0';
  const params = new URLSearchParams(location.search);
  const requestedSessionId = params.get('proxyFoundryOrder');
  if (!requestedSessionId) return;
  if (window.__proxyPrintBridgeRunning) return;
  window.__proxyPrintBridgeRunning = true;

  let metadata = null;
  let NEW_CARD_COUNT = 0;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  try {
    const clean = new URL(location.href);
    clean.searchParams.delete('proxyFoundryOrder');
    history.replaceState(history.state, '', clean.toString());
  } catch (_) {}

  const DEBUG = {version: VERSION, startedAt: new Date().toISOString(), events: []};
  function debugEvent(message, data) {
    const event = {time: new Date().toISOString(), message};
    if (data !== undefined) event.data = data;
    DEBUG.events.push(event);
    console.log('[Proxy Print Helper]', message, data ?? '');
  }

  // Controls are outside document.body so they cannot inflate card-count signals.
  const overlay = document.createElement('div');
  overlay.id = 'proxy-print-helper-status';
  overlay.innerHTML = `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px">
      <div style="display:flex;align-items:center;gap:9px;min-width:0">
        <div style="width:10px;height:10px;border-radius:50%;background:#ff7a32;box-shadow:0 0 14px #ff7a32;flex:0 0 auto"></div>
        <b style="font-size:14px;color:#fff;line-height:1.2">Proxy Print Helper <span style="font-size:10px;color:#8d98a6;font-weight:700">v${VERSION}</span></b>
      </div>
      <div style="display:flex;gap:6px;flex:0 0 auto">
        <button id="pph-min" title="Minimize" style="width:28px;height:28px;border-radius:8px;border:1px solid #3b414d;background:#171c23;color:#c9d1da;cursor:pointer;font-size:16px;line-height:1">–</button>
        <button id="pph-close" title="Close" style="width:28px;height:28px;border-radius:8px;border:1px solid #3b414d;background:#171c23;color:#c9d1da;cursor:pointer;font-size:16px;line-height:1">×</button>
      </div>
    </div>
    <div id="pph-body">
      <div id="pph-line" style="color:#dce4ee">Starting handoff…</div>
      <div id="pph-sub" style="margin-top:8px;color:#8491a3;font-size:11px">Keep this tab open while the paired order is being prepared.</div>
      <div id="pph-choice" style="display:none;margin-top:14px;padding-top:13px;border-top:1px solid #2b323c">
        <button id="pph-replace" style="width:100%;border:0;border-radius:10px;background:linear-gradient(180deg,#ff8b4d,#f36b25);color:#130c08;font-weight:800;padding:11px 12px;cursor:pointer;margin-bottom:8px"></button>
        <button id="pph-add" style="width:100%;border:1px solid #3b4654;border-radius:10px;background:#1b222b;color:#e8edf3;font-weight:750;padding:11px 12px;cursor:pointer"></button>
        <div style="margin-top:9px;color:#6f7b89;font-size:10px">Nothing changes until you choose.</div>
      </div>
      <div style="display:flex;gap:7px;margin-top:12px">
        <button id="pph-debug" style="flex:1;border:1px solid #47515f;border-radius:9px;background:#1c232c;color:#e5eaf0;font-weight:750;padding:9px 10px;cursor:pointer">Show Debug</button>
        <button id="pph-select" style="display:none;border:1px solid #47515f;border-radius:9px;background:#1c232c;color:#cbd3dc;font-weight:750;padding:9px 10px;cursor:pointer">Select Text</button>
      </div>
      <textarea id="pph-debug-text" readonly style="display:none;width:100%;height:230px;margin-top:8px;resize:vertical;border:1px solid #3b4654;border-radius:9px;background:#080b0f;color:#b8c3d0;padding:9px;font:10px/1.35 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre"></textarea>
    </div>`;
  Object.assign(overlay.style, {
    position:'fixed', top:'16px', right:'16px', zIndex:'2147483647', width:'400px', maxWidth:'calc(100vw - 32px)',
    background:'rgba(8,10,14,.97)', border:'1px solid #3b414d', borderRadius:'14px',
    boxShadow:'0 18px 50px rgba(0,0,0,.45)', padding:'14px 16px',
    font:'13px/1.45 Inter,system-ui,-apple-system,Segoe UI,sans-serif'
  });
  document.documentElement.appendChild(overlay);
  const line = overlay.querySelector('#pph-line');
  const sub = overlay.querySelector('#pph-sub');
  const body = overlay.querySelector('#pph-body');
  const choiceBox = overlay.querySelector('#pph-choice');
  const replaceBtn = overlay.querySelector('#pph-replace');
  const addBtn = overlay.querySelector('#pph-add');
  const debugBtn = overlay.querySelector('#pph-debug');
  const selectBtn = overlay.querySelector('#pph-select');
  const debugText = overlay.querySelector('#pph-debug-text');
  const minBtn = overlay.querySelector('#pph-min');
  const closeBtn = overlay.querySelector('#pph-close');
  let cancelled = false, minimized = false, pendingChoiceResolve = null, lastError = null;
  minBtn.addEventListener('click', () => {
    minimized = !minimized;
    body.style.display = minimized ? 'none' : 'block';
    minBtn.textContent = minimized ? '+' : '–';
    minBtn.title = minimized ? 'Expand' : 'Minimize';
    overlay.style.width = minimized ? '245px' : '400px';
  });
  closeBtn.addEventListener('click', () => {
    cancelled = true;
    if (pendingChoiceResolve) {pendingChoiceResolve('cancel'); pendingChoiceResolve = null;}
    overlay.remove();
  });
  function bodyText() {return document.body?.innerText || '';}
  function processingVisible() {
    const text = bodyText();
    return text.includes('Applying Bleed Settings') || text.includes('Processing card');
  }
  function interactiveElements() {
    return [...document.querySelectorAll('button,[role="button"],a')].filter(el => {
      if (overlay.contains(el)) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && !el.disabled;
    });
  }
  function buttonLabel(el) {
    return [el.innerText || el.textContent || '', el.getAttribute('aria-label') || '',
      el.getAttribute('title') || '', el.getAttribute('data-tooltip') || ''].join(' ').replace(/\s+/g, ' ').trim();
  }
  function clickControl(re) {
    const el = interactiveElements().find(x => re.test(buttonLabel(x)));
    if (!el) return false;
    el.click(); return true;
  }
  function textCardCounts() {
    const text = bodyText(), values = [];
    const patterns = [/(\d+)\s+Cards?\b/gi, /\bCards?\s*[:·|/–—-]?\s*(\d+)\b/gi, /\bTotal\s*[:·|/–—-]?\s*(\d+)\s+Cards?\b/gi];
    for (const re of patterns) for (const m of text.matchAll(re)) values.push(Number(m[1]));
    return values.filter(Number.isFinite);
  }
  function likelyRemoveButtonCount() {
    const re = /remove\s+(this\s+)?(card|image)|delete\s+(this\s+)?(card|image)/i;
    return interactiveElements().filter(el => re.test(buttonLabel(el))).length;
  }
  function likelyCardTileElements() {
    const selectors = ['[data-card-id]', '[data-card-index]', '[data-card]', '[class*="card-preview" i]',
      '[class*="card-item" i]', '[class*="uploaded-card" i]', '[class*="card-thumbnail" i]', '[class*="card-tile" i]'];
    const set = new Set();
    for (const sel of selectors) try {
      for (const el of document.querySelectorAll(sel)) {
        if (overlay.contains(el)) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 20 && r.height > 20) set.add(el);
      }
    } catch (_) {}
    return [...set];
  }
  function likelyUploadedCardMedia() {
    const list = [];
    for (const el of document.querySelectorAll('img,canvas')) {
      if (overlay.contains(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 55 || r.height < 70) continue;
      const ratio = r.width / r.height;
      if (ratio < 0.58 || ratio > 0.86) continue;
      if (el.tagName === 'IMG' && !/^(blob:|data:)/i.test(el.currentSrc || el.src || '')) continue;
      list.push(el);
    }
    return list;
  }
  function detectExistingCards() {
    const textCounts = textCardCounts(), positiveText = textCounts.filter(n => n > 0);
    const removeButtonCount = likelyRemoveButtonCount(), tileCount = likelyCardTileElements().length, mediaCount = likelyUploadedCardMedia().length;
    let count = 0, source = 'none';
    if (removeButtonCount > 0) {count = removeButtonCount; source = 'remove-buttons';}
    else if (positiveText.length) {count = Math.max(...positiveText); source = 'text-counter';}
    else if (tileCount > 0) {count = tileCount; source = 'card-tiles';}
    else if (mediaCount > 0) {count = mediaCount; source = 'card-media';}
    const explicitZero = textCounts.includes(0);
    const confidentlyEmpty = explicitZero && count === 0 && tileCount === 0 && mediaCount === 0 && removeButtonCount === 0;
    return {count,source,explicitZero,confidentlyEmpty,signals:{textCounts,removeButtonCount,tileCount,mediaCount}};
  }
  function nearbyText(el, maxDepth=5) {
    let n = el;
    for (let d=0; n && d<=maxDepth; d++, n=n.parentElement) {
      const text = (n.innerText || n.textContent || '').replace(/\s+/g,' ').trim();
      if (text) return text.slice(0,600);
    }
    return '';
  }
  function collectDiagnostics(extra={}) {
    let fileInputs = [], buttons = [];
    try {
      fileInputs = [...document.querySelectorAll('input[type="file"]')].map((el,i) => ({
        index:i, accept:el.getAttribute('accept'), multiple:!!el.multiple, id:el.id || null,
        name:el.getAttribute('name'), filesLength:el.files?.length ?? null, nearbyText:nearbyText(el), outerHTML:el.outerHTML.slice(0,900)
      }));
    } catch (e) {fileInputs = [{error:String(e)}];}
    try {buttons = interactiveElements().slice(0,180).map((el,i) => ({index:i,label:buttonLabel(el).slice(0,300),tag:el.tagName,outerHTML:el.outerHTML.slice(0,700)}));}
    catch (e) {buttons = [{error:String(e)}];}
    return {version:VERSION,startedAt:DEBUG.startedAt,capturedAt:new Date().toISOString(),url:location.href,title:document.title,
      readyState:document.readyState,existingCardDetection:(()=>{try{return detectExistingCards()}catch(e){return {error:String(e)}}})(),
      fileInputs,controls:buttons,storage:'[omitted: browser storage is private]',bodyTextSample:bodyText().slice(0,12000),
      events:DEBUG.events,lastError,userAgent:navigator.userAgent,viewport:{width:innerWidth,height:innerHeight},...extra};
  }
  function refreshDebug() {
    try {debugText.value = JSON.stringify(collectDiagnostics(), null, 2);}
    catch (e) {debugText.value = 'Could not build diagnostics: ' + String(e);}
  }
  function showDebug() {
    refreshDebug(); debugText.style.display = 'block'; selectBtn.style.display = 'block'; debugBtn.textContent = 'Hide Debug';
  }
  debugBtn.addEventListener('click', () => {
    if (debugText.style.display === 'none') showDebug();
    else {debugText.style.display = 'none';selectBtn.style.display = 'none';debugBtn.textContent = 'Show Debug';}
  });
  selectBtn.addEventListener('click', () => {
    refreshDebug();debugText.focus();debugText.select();selectBtn.textContent = 'Selected — press Ctrl+C';
    setTimeout(() => {if (selectBtn.isConnected) selectBtn.textContent = 'Select Text';}, 2200);
  });
  function log(message, detail='Keep this tab open while the paired order is being prepared.') {
    debugEvent(message);line.textContent = message;sub.textContent = detail;choiceBox.style.display = 'none';
  }
  function success(message) {
    chrome.runtime.sendMessage({type:'PF_ORDER_FINISHED'}).catch(() => {});
    debugEvent('SUCCESS: ' + message);line.textContent = message;line.style.color = '#84e6a1';
    sub.textContent = 'This message will close automatically in a few seconds. You can also close it now.';
    overlay.style.borderColor = '#2e8d4f';choiceBox.style.display = 'none';
    setTimeout(() => {if (overlay.isConnected) overlay.remove();}, 7000);
  }
  function fail(err) {
    if (cancelled) return;
    lastError = err?.stack || err?.message || String(err);debugEvent('FAILURE', {error:lastError});
    line.textContent = 'FAILED — ' + (err?.message || String(err));line.style.color = '#ff8383';
    sub.textContent = 'Diagnostics are shown below. Review them before sharing: card names and visible page text may be included.';
    overlay.style.borderColor = '#a83d3d';choiceBox.style.display = 'none';showDebug();
  }
  async function waitFor(fn, timeout, label, interval=250) {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      if (cancelled) throw new Error('Handoff cancelled.');
      const value = fn();if (value) return value;await sleep(interval);
    }
    throw new Error('Timed out waiting for ' + label);
  }
  async function loadDeckPayload() {
    log('Connecting to your saved print order…', 'Keep the Proxy Foundry launcher running until the ZIP upload is finished.');
    metadata = await chrome.runtime.sendMessage({type:'PF_ORDER_METADATA'});
    if (!metadata?.ok) throw new Error(metadata?.error || 'This order transfer is no longer available. Reopen it from Proxy Foundry.');
    if (!Number.isSafeInteger(metadata.count) || metadata.count < 1 || metadata.count > 10000 || !Number.isSafeInteger(metadata.zipBytes) || metadata.zipBytes < 22) throw new Error('The saved order metadata is invalid.');
    NEW_CARD_COUNT = metadata.count;debugEvent('Saved paired order connected', {cards:NEW_CARD_COUNT,bytes:metadata.zipBytes});
  }
  async function createDeckZipFile() {
    const parts=[];let offset=0;
    while (offset < metadata.zipBytes) {
      if (cancelled) throw new Error('Handoff cancelled.');
      const part=await chrome.runtime.sendMessage({type:'PF_ORDER_CHUNK',offset});
      if (!part?.ok) throw new Error(part?.error || 'The order transfer failed.');
      if (part.offset!==offset || part.total!==metadata.zipBytes || !Number.isSafeInteger(part.length) || part.length<1 || part.length>1024*1024) throw new Error('The order chunk did not match its saved package.');
      const text=atob(part.base64),bytes=Uint8Array.from(text,c=>c.charCodeAt(0));
      if (bytes.length!==part.length) throw new Error('An order chunk was truncated.');
      parts.push(bytes);offset+=bytes.length;
      log(`Transferring paired ZIP: ${Math.round(offset/metadata.zipBytes*100)}%`,`${NEW_CARD_COUNT} cards. Fronts and backs remain paired by filename.`);
    }
    if (cancelled) throw new Error('Handoff cancelled.');
    const file=new File(parts,metadata.filename||'ProxyFoundry_Order.zip',{type:'application/zip'});
    if (file.size!==metadata.zipBytes) throw new Error('The paired ZIP transfer was incomplete.');
    debugEvent('Paired ZIP transferred',{bytes:file.size,cards:NEW_CARD_COUNT});return file;
  }
  function setFiles(input, files) {
    if (cancelled) throw new Error('Handoff cancelled.');
    const dt = new DataTransfer();for (const file of files) dt.items.add(file);
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'files')?.set;
    if (!setter) throw new Error('Browser did not expose the file-input setter.');
    setter.call(input,dt.files);
    input.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
    input.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
    return input.files?.length || 0;
  }
  function findFrontInput() {
    return [...document.querySelectorAll('input[type="file"]')].find(el => {
      const accept = (el.getAttribute('accept') || '').toLowerCase();
      if (!accept.includes('image')) return false;
      return !/Sequential Backs|Upload Back/i.test(nearbyText(el,4));
    }) || null;
  }
  function findDeckZipInput() {
    const inputs = [...document.querySelectorAll('input[type="file"]')];
    for (const el of inputs) if ((el.getAttribute('accept') || '').toLowerCase().includes('zip')) return el;
    let best=null,depthBest=Infinity;
    for (const el of inputs) {
      let node=el.parentElement;
      for (let depth=0;node && depth<9;node=node.parentElement,depth++) {
        if (/Upload\s+Deck\s+ZIP/i.test(node.innerText || '')) {
          if (depth<depthBest) {depthBest=depth;best=el;}break;
        }
      }
    }
    return best;
  }
  // Detection only: this control is never assigned sequential back images.
  function findSequentialBackInput() {
    const inputs=[...document.querySelectorAll('input[type="file"]')];let best=null,depthBest=Infinity;
    for (const el of inputs) {
      let node=el.parentElement;
      for (let depth=0;node && depth<9;node=node.parentElement,depth++) {
        if ((node.innerText || '').includes('Sequential Backs')) {if (depth<depthBest) {depthBest=depth;best=el;}break;}
      }
    }
    return best;
  }
  function startDesignControl() {return interactiveElements().find(el => /^(Start Your Design|Start Design)$/i.test(buttonLabel(el))) || null;}
  function frontStepControl() {
    return interactiveElements().find(el => {
      const label=buttonLabel(el);
      return /Customize\s*Front/i.test(label) || /^Fronts?$/i.test(label) || /^1\s*[-:–—]?\s*Customize\s*Front/i.test(label);
    }) || null;
  }
  function looksLikeDesigner() {
    if (findFrontInput() || findDeckZipInput() || findSequentialBackInput()) return true;
    if (/Customize\s*Front|Customize\s*Back|Preview|Save Draft/i.test(interactiveElements().map(buttonLabel).join('\n'))) return true;
    const d=detectExistingCards();return d.count>0 || d.explicitZero;
  }
  async function acceptCookies() {
    const el=interactiveElements().find(x => /^(Accept|Accept All)$/i.test(buttonLabel(x)));
    if (el) {el.click();await sleep(400);}
  }
  async function enterDesignerIfNeeded() {
    if (looksLikeDesigner()) return;
    const start=startDesignControl();
    if (start) {log('Opening the TCGPlaytest card editor…');debugEvent('Clicking Start Your Design',{label:buttonLabel(start)});start.click();await sleep(1000);}
    await waitFor(looksLikeDesigner,20000,'TCGPlaytest to open its card editor');
  }
  async function ensureFrontStep() {
    const existing=findFrontInput();if (existing) return existing;
    const step=frontStepControl();
    if (step) {log('Returning to Customize Front…');debugEvent('Clicking front-step control',{label:buttonLabel(step)});step.click();await sleep(800);return await waitFor(findFrontInput,12000,'the Customize Front uploader');}
    const start=startDesignControl();
    if (start) {log('Opening Customize Front…');start.click();await sleep(900);return await waitFor(findFrontInput,12000,'the front-card uploader');}
    debugEvent('Could not find a path to Customize Front',collectDiagnostics({stage:'ensure-front'}));
    throw new Error('Could not navigate TCGPlaytest to Customize Front.');
  }
  async function dismissCommonDialogs() {
    for (const label of ['Got It','Got it!','OK']) {
      const exact=new RegExp('^'+label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$','i');
      if (clickControl(exact)) {await sleep(350);return;}
    }
  }
  function askHowToHandleExisting(existing,uncertain=false) {
    return new Promise(resolve => {
      pendingChoiceResolve=resolve;line.style.color='#f3f6fa';
      if (uncertain || !Number.isFinite(existing) || existing<=0) {
        line.textContent='TCGPlaytest may already contain cards.';
        sub.textContent=`I cannot safely prove the current editor is empty. Choose whether to replace the current list or append this ${NEW_CARD_COUNT}-card deck.`;
        replaceBtn.textContent='Replace the current list';addBtn.textContent=`Keep current list + add ${NEW_CARD_COUNT} cards`;
      } else {
        line.textContent=`TCGPlaytest already has ${existing} ${existing===1?'card':'cards'}.`;
        sub.textContent=`Replace ${existing===1?'it':'them'}, or keep ${existing===1?'it':'them'} and append this ${NEW_CARD_COUNT}-card deck?`;
        replaceBtn.textContent=`Replace existing ${existing} ${existing===1?'card':'cards'}`;
        addBtn.textContent=`Keep them + add ${NEW_CARD_COUNT} new cards`;
      }
      choiceBox.style.display='block';
      const finish=value=>{if(!pendingChoiceResolve)return;const r=pendingChoiceResolve;pendingChoiceResolve=null;choiceBox.style.display='none';r(value);};
      replaceBtn.onclick=()=>finish('replace');addBtn.onclick=()=>finish('add');
    });
  }
  function clearAllControl() {
    const patterns=[/clear\s+all\s+cards/i,/remove\s+all\s+cards/i,/delete\s+all\s+cards/i,/clear\s+cards/i,/clear\s+deck/i,/empty\s+deck/i];
    return interactiveElements().find(el=>patterns.some(re=>re.test(buttonLabel(el)))) || null;
  }
  function cardRemoveControls() {
    const re=/remove\s+(this\s+)?(card|image)|delete\s+(this\s+)?(card|image)|^(remove|delete)$/i;
    return interactiveElements().filter(el=>re.test(buttonLabel(el)));
  }
  function visibleDialogLikeElements() {
    const found=new Set();
    for (const sel of ['[role="dialog"]','[aria-modal="true"]','dialog','[class*="modal" i]','[class*="dialog" i]']) try {
      for (const el of document.querySelectorAll(sel)) {
        if (overlay.contains(el)) continue;
        const r=el.getBoundingClientRect();if(r.width>0&&r.height>0)found.add(el);
      }
    } catch (_) {}
    return [...found];
  }
  function findDeleteCardDialog() {return visibleDialogLikeElements().find(el=>/Delete this card\?/i.test(el.innerText||el.textContent||'')) || null;}
  function findDeleteCardButton(dialog) {
    if(!dialog)return null;
    return [...dialog.querySelectorAll('button,[role="button"]')].find(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&!el.disabled&&/^Delete\s+card$/i.test(buttonLabel(el));}) || null;
  }
  async function confirmDeleteCardIfPresent(timeoutMs=5000) {
    const started=Date.now();
    while(Date.now()-started<timeoutMs){
      if(cancelled)throw new Error('Handoff cancelled.');
      const dialog=findDeleteCardDialog();
      if(dialog){
        const deleteButton=findDeleteCardButton(dialog);
        if(!deleteButton){debugEvent('Delete-card dialog missing confirmation',{dialogText:(dialog.innerText||dialog.textContent||'').slice(0,1000)});throw new Error('TCGPlaytest asked to delete a card, but the helper could not find the “Delete card” confirmation button.');}
        debugEvent('Confirming Delete card dialog',{dialogText:(dialog.innerText||dialog.textContent||'').slice(0,700),button:buttonLabel(deleteButton)});
        deleteButton.click();
        const disappearStart=Date.now();
        while(Date.now()-disappearStart<6000){if(!findDeleteCardDialog())return true;await sleep(120);}
        throw new Error('Clicked “Delete card”, but the confirmation dialog did not close.');
      }
      await sleep(100);
    }
    return false;
  }
  async function maybeConfirmDestructiveAction() {
    // Only called after the user chose Replace; confirmation clicks stay inside the modal.
    if(await confirmDeleteCardIfPresent(1800))return true;
    const started=Date.now();
    while(Date.now()-started<2200){
      const dialog=visibleDialogLikeElements().find(el=>/clear|remove all|delete all|empty/i.test((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim()));
      if(dialog){
        const button=[...dialog.querySelectorAll('button,[role="button"]')].find(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&!el.disabled&&/^(Confirm|Yes|Clear all|Remove all|Delete all)$/i.test(buttonLabel(el));});
        if(button){debugEvent('Confirming bulk destructive dialog',{dialogText:(dialog.innerText||dialog.textContent||'').slice(0,700),button:buttonLabel(button)});button.click();await sleep(300);return true;}
      }
      await sleep(100);
    }
    return false;
  }
  async function clearExistingCards(expected) {
    log(Number.isFinite(expected)&&expected>0?`Removing ${expected} existing ${expected===1?'card':'cards'}…`:'Removing the existing TCGPlaytest cards…',
      'You chose Replace. The helper will not upload the new deck until the old list is cleared.');
    const clearAll=clearAllControl();
    if(clearAll){
      debugEvent('Trying clear-all control',{label:buttonLabel(clearAll)});clearAll.click();await maybeConfirmDestructiveAction();await sleep(700);
      const state=detectExistingCards();if(state.confidentlyEmpty||(state.count===0&&state.explicitZero))return;
    }
    let safety=Math.max((expected||detectExistingCards().count||20)+10,30);
    while(safety-->0){
      if(cancelled)throw new Error('Handoff cancelled.');
      const state=detectExistingCards();if(state.confidentlyEmpty||(state.count===0&&state.explicitZero))return;
      const controls=cardRemoveControls();if(!controls.length)break;
      let changed=false;const before=state.count;
      for(const control of controls){
        if(!control.isConnected)continue;
        debugEvent('Trying per-card remove control',{label:buttonLabel(control),before});control.click();
        const confirmed=await maybeConfirmDestructiveAction();
        if(!confirmed){debugEvent('Unrecognized delete confirmation',{control:buttonLabel(control),before});throw new Error('TCGPlaytest opened a card-removal flow that the helper could not confirm automatically.');}
        let after=detectExistingCards();const changeStart=Date.now();
        while(Date.now()-changeStart<7000&&!(after.count<before||after.confidentlyEmpty)){await sleep(150);after=detectExistingCards();}
        if(after.count<before||after.confidentlyEmpty){changed=true;debugEvent('Existing card deleted successfully',{before,after:after.count,detection:after});break;}
        throw new Error('TCGPlaytest confirmed the deletion, but the existing-card count did not decrease.');
      }
      if(!changed)break;
    }
    const finalState=detectExistingCards();
    if(!(finalState.confidentlyEmpty||(finalState.count===0&&finalState.explicitZero))){debugEvent('Could not prove current list is empty',finalState);throw new Error('I could not safely prove the existing cards were removed, so I stopped before uploading the new deck.');}
  }
  async function waitForUploadProcessing(minWaitMs=1800,timeoutMs=180000) {
    const started=Date.now();let sawProcessing=false;
    while(Date.now()-started<timeoutMs){
      if(cancelled)throw new Error('Handoff cancelled.');
      if(processingVisible())sawProcessing=true;
      if(sawProcessing&&!processingVisible()&&Date.now()-started>minWaitMs)return;
      if(!sawProcessing&&Date.now()-started>7000)return;
      await sleep(350);
    }
    throw new Error('TCGPlaytest did not finish processing the ZIP. Stop and review its editor before retrying.');
  }
  async function appendDeckViaZip(existing) {
    log(Number.isFinite(existing)&&existing>0?`Keeping ${existing} existing ${existing===1?'card':'cards'} and adding ${NEW_CARD_COUNT} more…`:`Uploading ${NEW_CARD_COUNT} cards with their paired backs…`,
      'Using TCGPlaytest’s Deck ZIP importer so each FRONT/###.png is locked to the matching BACK/###.png.');
    await ensureFrontStep();
    const zipInput=await waitFor(findDeckZipInput,15000,'the Upload Deck ZIP control');
    const zipFile=await createDeckZipFile();
    if(setFiles(zipInput,[zipFile])!==1)throw new Error('TCGPlaytest did not accept the deck ZIP.');
    await waitForUploadProcessing(2200,120000);await dismissCommonDialogs();
    const expected=Number.isFinite(existing)?existing+NEW_CARD_COUNT:NEW_CARD_COUNT;let after=null;
    await waitFor(()=>{
      after=detectExistingCards();const explicit=after.signals.textCounts.filter(x=>x>0);
      return explicit.includes(expected)||(after.count===expected)||(!Number.isFinite(existing)&&after.count>=NEW_CARD_COUNT);
    },120000,'the completed paired-card count');
    if(cancelled)return;
    debugEvent('Paired upload count verified',{expected,detected:after});
    if(clickControl(/Next.*Customize Back/i)){
      await sleep(1100);if(cancelled)return;
      clickControl(/Next.*Preview/i)||clickControl(/^Preview$/i);
    }
    success(`Uploaded ${NEW_CARD_COUNT} paired cards. Review both sides in the printer preview before checkout.`);
  }
  async function run() {
    try{
      await loadDeckPayload();log('Completed renders loaded — preparing TCGPlaytest…');
      debugEvent('Initial page state',{url:location.href,title:document.title,readyState:document.readyState});
      await acceptCookies();await sleep(300);await enterDesignerIfNeeded();await sleep(450);
      const state=detectExistingCards();debugEvent('Existing-card detection before upload',state);
      // Only skip the question when the editor explicitly reports 0 and no other detector sees a card.
      if(state.count>0||!state.confidentlyEmpty){
        const exact=state.count>0?state.count:null;
        const action=await askHowToHandleExisting(exact,exact==null);
        if(action==='cancel')return;
        if(action==='add'){await appendDeckViaZip(exact);return;}
        await ensureFrontStep();await clearExistingCards(exact);
      }
      // Always use paired ZIPs, including empty/replaced decks. Never infer sequential backs.
      await appendDeckViaZip(0);
    }catch(e){fail(e);}
  }
  run();
})();
