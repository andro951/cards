/* A GitHub bundle populates the setup draft; saving still uses deck revisions. */
import {$,esc,state,job,toast} from './ui.js';

export function githubSetupSection(folder=''){
  return `<section class="panel github-setup" id="github-setup" aria-labelledby="github-setup-title">
    <div class="panel-head"><div><span class="eyebrow">QUICK START / OPTIONAL</span><h2 id="github-setup-title">1-click GitHub import</h2><p>Bring your artwork, set symbols and card back into this setup from one public GitHub folder.</p></div></div>
    <div class="github-setup-action"><label class="field"><span>GitHub project folder</span><input type="url" id="github-setup-folder" value="${esc(folder)}" placeholder="https://github.com/you/cards/tree/main/my_deck" aria-describedby="github-setup-help"><small id="github-setup-help">Link the parent folder shown below, not its art subfolder. No local repository needed.</small></label><button type="button" class="button primary" id="github-setup-button">1-click import</button></div>
    <div class="github-setup-guide"><pre aria-label="GitHub setup folder structure"><code>folder/
├── art/
│   ├── sol_ring.png
│   ├── command_tower.png
│   └── ...
├── set_symbols/
│   ├── common.png
│   ├── uncommon.png
│   ├── rare.png
│   └── mythic.png
├── set_symbol.png
├── back.png
└── back_icon.png</code></pre>
      <div class="github-setup-notes">
        <p><b>Required: choose one symbol option.</b><br><code>set_symbols/</code> with all four rarity images is <strong>recommended</strong>. Alternatively, <code>set_symbol.png</code> is color-shifted into four variants (<strong>not recommended</strong>). The four-image folder wins when both are present.</p>
        <p><b>Artwork is optional.</b><br><code>art/</code> becomes the live GitHub artwork source. Without it, Scryfall printing is selected. “Use Scryfall artwork when a custom image is missing” is enabled on import; individual art overrides are kept.</p>
        <p><b>Both back options are optional.</b><br><code>back.png</code> uses your complete back. <code>back_icon.png</code> centers your icon on the Bulk Proxy Forge back. A complete back takes priority over an icon. With neither file, the default forge back is used. Real reverse faces are kept.</p>
      </div>
    </div>
    <p class="subtitle-line">PNG examples shown; JPEG, WebP and GIF also work. Symbols and backs are copied on import; GitHub art is fetched when generating. Import again to update symbols or a back.</p>
    <p class="subtitle-line">This replaces the artwork source, symbols and deck back in the setup below. Your card list, printing choices, credits and templates stay unchanged. Review, then Save changes or Save &amp; generate images.</p>
    <div id="github-setup-status" class="notice hidden" role="status" aria-live="polite"></div><div id="github-setup-warnings"></div>
  </section>`;
}

export function mountGithubSetupImport(host,{isBusy=()=>false,onBusy=()=>{},onImport}){
  const input=$('#github-setup-folder',host),button=$('#github-setup-button',host),status=$('#github-setup-status',host),warnings=$('#github-setup-warnings',host);
  let importing=false;
  function message(text,kind='info'){
    status.className='notice '+kind;status.textContent=text;
  }
  async function run(){
    if(importing)return;
    if(state.busy||isBusy()){message('Wait for the current upload or task to finish before importing.');return;}
    const url=input.value.trim();
    if(!url){message('Paste the GitHub project folder link first.','error');input.focus();return;}
    const wasDirty=state.dirty;
    let applied=false;
    importing=true;state.busy=true;state.dirty=true;
    button.disabled=true;input.disabled=true;button.textContent='Importing…';onBusy(true);
    warnings.replaceChildren();message('Reading GitHub project folder…');
    try{
      const result=await job('/api/setup/github-import',{url},{label:'GitHub setup',onProgress:j=>{if(host.isConnected)message(j.message);}});
      // A navigation during the job must not apply the result to a different deck.
      if(!host.isConnected)return;
      onImport(result.settings);applied=true;input.value=result.settings.githubSetupFolder;
      const art=result.summary.art==='github'?'GitHub art folder':'Scryfall artwork (no art folder)',symbols=result.summary.symbols==='folder'?'four rarity symbols':'four color-shifted symbols';
      const back={default:'default forge back',icon:'custom icon on the forge back',custom:'complete custom back'}[result.summary.back];
      message(`Imported ${art}, ${symbols}, and ${back}. Review below, then save your setup.`,'success');
      for(const text of result.warnings||[]){const note=document.createElement('div');note.className='notice';note.textContent=text;warnings.append(note);}
      toast('GitHub setup imported. Review below, then save.');
    }catch(error){
      if(host.isConnected)message(error.message+' Your setup was not changed.','error');
    }finally{
      importing=false;state.busy=false;
      if(host.isConnected){if(!applied)state.dirty=wasDirty;button.disabled=false;input.disabled=false;button.textContent='1-click import';onBusy(false);}
    }
  }
  button.onclick=run;
  input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();run();}});
  return {isBusy:()=>importing};
}
