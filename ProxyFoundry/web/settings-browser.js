import {$,api,attempt,toast,modal,closeModal,confirmAction,job,bytes,downloadBlob,state,work} from '/site/ui.js';
import {savedFolder,chooseFolder,useFolder,useBrowserStorage,containsWorkspace,copyWorkspace} from './storage-choice.js';

function element(tag,text='',className=''){
  const node=document.createElement(tag);
  node.textContent=text;
  node.className=className;
  return node;
}
function button(label,action,className='button'){
  const node=element('button',label,className);
  node.onclick=()=>attempt(action);
  return node;
}
function panel(title){
  const section=element('section','','panel section-gap');
  section.append(element('h2',title));
  return section;
}
async function download(path,name){
  const response=await fetch(path);
  if(!response.ok)throw new Error((await response.json()).error||'Download failed.');
  downloadBlob(await response.blob(),name);
}
function chooseFile(accept){
  return new Promise(resolve=>{
    const input=document.createElement('input');input.type='file';input.accept=accept;
    input.onchange=()=>resolve(input.files[0]||null);
    input.click();
  });
}
async function changeWorkspace(operation){
  const task=work.begin({label:'Move workspace',resources:['workspace']});
  try{return await operation();}
  finally{work.finish(task);}
}

export async function showSettings(){
  const epoch=state.routeEpoch;
  const [settings,stats,styles,estimate,folder,storage]=await Promise.all([
    api('/api/settings'),api('/api/stats'),api('/api/style-presets'),api('/api/backups/estimate'),
    savedFolder(),navigator.storage.estimate()]);
  if(epoch!==state.routeEpoch)return;
  const main=$('#main');main.replaceChildren();
  const heading=element('div','','page-head');heading.append(element('h1','Settings'));main.append(heading);

  const locationPanel=panel('Workspace storage');
  locationPanel.append(element('p',folder?`Using your BulkProxyForge folder on this computer.`:'Saved on this device in browser storage.','muted'));
  locationPanel.append(element('p',`Using ${bytes(storage.usage||0)} of ${bytes(storage.quota||0)} available browser storage.`, 'muted'));
  const locationActions=element('div','','actions section-gap');
  locationActions.append(button('Choose a different location',async()=>{
    const changed=await changeWorkspace(async()=>{
    const target=await chooseFolder();
    if(folder?.isSameEntry&&await folder.isSameEntry(target))return;
    const occupied=await containsWorkspace(target);
    if(occupied){
      if(!await confirmAction('Open this existing workspace?',
        'The selected BulkProxyForge folder already contains files. It will open as a separate workspace. Your current workspace stays where it is.',
        'Open folder'))return;
    }
    else{
      const source=folder||await navigator.storage.getDirectory();
      await copyWorkspace(source,target);
    }
    await useFolder(target);return true;
    });
    if(changed)location.reload();
  }));
  if(folder)locationActions.append(button('Save in browser storage',async()=>{
    const changed=await changeWorkspace(async()=>{
    const target=await navigator.storage.getDirectory();
    const occupied=await containsWorkspace(target);
    if(occupied){
      if(!await confirmAction('Open browser workspace?',
        'Browser storage already contains a workspace. Opening it keeps your current folder workspace intact.',
        'Open browser workspace'))return;
    }
    else await copyWorkspace(folder,target);
    await useBrowserStorage();return true;
    });
    if(changed)location.reload();
  },'button quiet'));
  locationPanel.append(locationActions);main.append(locationPanel);

  const dataPanel=panel('Card data');
  const refreshLabel=element('label','','check-line');
  const refresh=document.createElement('input');refresh.type='checkbox';refresh.checked=!!settings.refreshData;
  refreshLabel.append(refresh,element('span','Refresh Scryfall card data when the cache is at least one week old.'));
  refresh.onchange=()=>attempt(async()=>{
    const updated=await api('/api/settings',{revision:settings.revision,refreshData:refresh.checked});
    Object.assign(settings,updated);toast('Card data preference saved.');
  });
  dataPanel.append(refreshLabel);main.append(dataPanel);

  const stylePanel=panel('Saved deck styles');
  const defaultLabel=element('label','','field');defaultLabel.append(element('span','Default style for new decks'));
  const defaultChoice=document.createElement('select');
  const none=document.createElement('option');none.value='';none.textContent='None — Default Look';defaultChoice.append(none);
  for(const style of styles){
    const option=document.createElement('option');option.value=style.id;option.textContent=style.name;defaultChoice.append(option);
  }
  defaultChoice.value=settings.defaultStylePresetId||'';
  defaultChoice.onchange=()=>attempt(async()=>{
    const updated=await api('/api/settings',{revision:settings.revision,defaultStylePresetId:defaultChoice.value||null});
    Object.assign(settings,updated);toast('Default style saved.');
  });
  defaultLabel.append(defaultChoice);stylePanel.append(defaultLabel);
  for(const style of styles){
    const row=element('div','','trash-row');row.append(element('strong',style.name));
    const actions=element('div','','actions');
    actions.append(button('Export JSON',()=>download(`/api/style-presets/${style.id}/export`,`${style.name}.json`),'button small'));
    actions.append(button('Delete',async()=>{
      if(!await confirmAction('Delete this saved style?',style.name+' will be removed. Existing decks keep their own settings.','Delete style',true))return;
      await api(`/api/style-presets/${style.id}/delete`,{revision:style.revision});await showSettings();
    },'button quiet small'));
    row.append(actions);stylePanel.append(row);
  }
  stylePanel.append(button('Import Style JSON',async()=>{
    const file=await chooseFile('.json');if(!file)return;
    const payload=JSON.parse(await file.text());
    await api('/api/style-presets/import',payload);await showSettings();toast('Style imported.');
  }));
  main.append(stylePanel);

  const backupPanel=panel('Backup and recovery');
  backupPanel.append(element('p','Backups include your decks, templates, saved styles, and source artwork. Generated images are optional.','muted'));
  const backupActions=element('div','','actions section-gap');
  backupActions.append(button('Export Backup',()=>exportBackup(estimate),'button primary'));
  backupActions.append(button('Import from Backup',importBackup));
  backupPanel.append(backupActions);main.append(backupPanel);

  const cleanupPanel=panel('Maintenance');
  cleanupPanel.append(element('p',`${stats.renders} generated images · ${bytes(stats.renderBytes||0)}.`, 'muted'));
  const cleanupActions=element('div','','actions section-gap');
  cleanupActions.append(button('Delete All Images',async()=>{
    if(!await confirmAction('Delete all generated images?','Decks, source artwork, backs, symbols, and settings remain. You can regenerate the images later.','Delete images',true))return;
    const result=await api('/api/images/delete-all',{});toast(`${result.deleted} generated images deleted.`);await showSettings();
  },'button danger'));
  cleanupActions.append(button('Download Diagnostics',()=>download('/api/diagnostics.zip','BulkProxyForge_Diagnostics.zip')));
  cleanupPanel.append(cleanupActions);main.append(cleanupPanel);
}

async function exportBackup(estimate){
  const host=modal('Export Backup','',{footer:'<button class="button primary" id="start-backup">Export backup</button>'});
  const body=$('.modal-body',host);
  body.append(element('p','Generated card images can be rebuilt later. Choose whether to include them.','muted'));
  const options=element('div','','stack section-gap');
  for(const [value,label,size] of [['no','Without generated images',estimate.withoutRenders],
                                    ['yes','With generated images',estimate.withRenders]]){
    const choice=element('label','','check-line');const radio=document.createElement('input');
    radio.type='radio';radio.name='backup-renders';radio.value=value;radio.checked=value==='no';
    choice.append(radio,element('span',`${label} · approximately ${bytes(size)}`));options.append(choice);
  }
  body.append(options);
  $('#start-backup').onclick=()=>attempt(async()=>{
    const includeRenders=body.querySelector('input[name="backup-renders"]:checked').value==='yes';
    closeModal();const output=await job('/api/backups/export',{includeRenders},{label:'Export backup'});
    await download(output.download,output.filename);toast('Backup downloaded.');
  });
}

async function importBackup(){
  const file=await chooseFile('.zip');if(!file)return;
  if(file.size>2*1024**3)throw new Error('Choose a backup under 2 GB.');
  const response=await fetch('/api/backups/inspect',{method:'POST',body:file});
  const catalog=await response.json();
  if(!response.ok)throw new Error(catalog.error||'Could not read this backup.');
  const host=modal('Import from Backup','',{size:'large',footer:'<button class="button primary" id="import-selected">Import selected</button>'});
  const body=$('.modal-body',host);
  body.append(element('p','Choose what to bring into this workspace. Existing items are replaced only after you confirm each collision.','muted'));
  const labels={'decks':'Decks','templates':'Templates','style-presets':'Saved styles'};
  for(const [kind,title] of Object.entries(labels)){
    const section=panel(title);section.dataset.kind=kind;
    const entries=catalog.objects[kind]||[];
    if(!entries.length)section.append(element('p','None in this backup.','muted'));
    for(const item of entries){
      const label=element('label','','check-line');const checkbox=document.createElement('input');
      checkbox.type='checkbox';checkbox.checked=true;checkbox.dataset.id=item.id;checkbox.dataset.kind=kind;
      label.append(checkbox,element('span',item.name+(item.collision?' · already in this workspace':'')));section.append(label);
    }
    body.append(section);
  }
  $('#import-selected').onclick=()=>attempt(async()=>{
    const selected={'decks':[],'templates':[],'style-presets':[]};const replace=[];
    for(const checkbox of body.querySelectorAll('input[type="checkbox"]:checked')){
      selected[checkbox.dataset.kind].push(checkbox.dataset.id);
      const entry=catalog.objects[checkbox.dataset.kind].find(item=>item.id===checkbox.dataset.id);
      if(entry.collision){
        if(!await confirmAction('Replace existing item?',`You already have ${entry.name}. Replace it completely with the version from this backup?`,'Replace',true))return;
        replace.push(entry.id);
      }
    }
    const epoch=state.routeEpoch;closeModal();
    await job('/api/backups/import-selected',{token:catalog.token,selected,replace},{label:'Import from backup'});
    toast('Selected backup items imported.');if(epoch===state.routeEpoch)await showSettings();
  });
}
