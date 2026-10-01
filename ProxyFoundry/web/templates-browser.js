import {$,api,attempt,toast,modal,closeModal,confirmAction,downloadBlob,uploadImage,esc} from '/site/ui.js';
import {renderTemplateSource,renderTemplateModel} from '/site/render.js';

const format='bulk-proxy-forge-template';
const ordinary=['standard','legendary','land','legendary-land','basic-land'];
const fields={title:'Card name',type:'Type line',mana:'Mana cost',rules:'Rules and flavor',
              flavor:'Flavor',pt:'Power / toughness',loyalty:'Loyalty',defense:'Defense'};

function element(tag,text='',className=''){
  const node=document.createElement(tag);node.textContent=text;node.className=className;return node;
}
function button(text,action,className='button'){
  const node=element('button',text,className);node.onclick=()=>attempt(action);return node;
}
function chooseFile(accept){
  return new Promise(resolve=>{const input=document.createElement('input');input.type='file';input.accept=accept;
    input.onchange=()=>resolve(input.files[0]||null);input.click();});
}

export async function showTemplates(){
  const templates=await api('/api/templates');
  const main=$('#main');main.replaceChildren();
  const heading=element('div','','page-head');heading.append(element('h1','Templates'));
  const actions=element('div','','actions');
  actions.append(button('Import Template',importTemplate));
  actions.append(button('Import Card Conjurer File',importCardConjurer));
  actions.append(button('＋ Create Template',createTemplate,'button primary'));
  heading.append(actions);main.append(heading);
  main.append(element('p','Saved templates can be selected later in a deck’s Custom Art & Setup screen.','muted'));
  const built=templates.filter(item=>!item.data);
  const custom=templates.filter(item=>item.data);
  const builtSection=element('section','','section-gap');builtSection.append(element('h2','Built-in styles'));
  const builtGrid=element('div','','template-grid');
  for(const item of built){
    const card=element('article','','template-card');card.style.padding='18px';
    card.append(element('h3',item.name));card.append(element('p',item.description,'muted'));
    if(item.id!=='auto'&&!item.id.startsWith('token-'))card.append(button('Use as starting point',()=>createFromSeed(item.id),'button small'));
    builtGrid.append(card);
  }
  builtSection.append(builtGrid);main.append(builtSection);
  const customSection=element('section','','section-gap');customSection.append(element('h2','Your templates'));
  const customGrid=element('div','','template-grid');
  for(const item of custom){
    const card=element('article','','template-card');card.style.padding='18px';
    card.append(element('h3',item.name));card.append(element('p',(item.groups||[]).join(' · '),'muted'));
    const row=element('div','','actions');
    row.append(button('Edit',()=>editTemplate(item),'button small'));
    row.append(button('Export JSON',()=>exportTemplate(item),'button quiet small'));
    row.append(button('Delete',async()=>{
      if(!await confirmAction('Delete this template?',`${item.name} cannot be recovered after deletion. A template used by a deck must be unassigned first.`,'Delete',true))return;
      await api(`/api/templates/${item.id}/delete`,{revision:item.revision});await showTemplates();
    },'button quiet small'));
    card.append(row);customGrid.append(card);
  }
  if(!custom.length)customSection.append(element('p','Create a reusable template from a built-in frame or a Card Conjurer card.','muted'));
  customSection.append(customGrid);main.append(customSection);
}

async function createTemplate(){
  const host=modal('Create Template','');const body=$('.modal-body',host);
  body.append(element('p','Start with an approved frame or a blank ordinary card canvas.','muted'));
  const list=element('div','','stack section-gap');
  for(const [kind,label] of [['normal','Classic card'],['land','Full-art land'],['legend-land','Crowned full art'],['blank','Blank ordinary card']]){
    list.append(button(label,async()=>{closeModal();await createFromSeed(kind);}));
  }
  body.append(list);
}
async function createFromSeed(kind){
  const seed=await api('/api/templates/seed?kind='+encodeURIComponent(kind==='blank'?'normal':kind));
  if(kind==='blank')seed.frames=[];
  const group=kind==='land'||kind==='godzilla-land'?'land':kind==='legend-land'?'legendary-land':'standard';
  const model=await api('/api/templates/convert-cardconjurer',{source:seed,name:'My template',group});
  editTemplate(model);
}
async function importTemplate(){
  const file=await chooseFile('.json');if(!file)return;
  if(file.size>64*1024**2)throw new Error('Template file limit is 64 MB.');
  const model=JSON.parse(await file.text());
  if(model.format!==format)throw new Error('Choose a Bulk Proxy Forge template JSON file. Card Conjurer files use the other import action.');
  await api('/api/templates/import',model);await showTemplates();toast('Template imported.');
}
async function exportTemplate(item){
  const response=await fetch(`/api/templates/${item.id}/export`);
  if(!response.ok)throw new Error((await response.json()).error||'Template export failed.');
  downloadBlob(await response.blob(),item.name.replace(/[^A-Za-z0-9_. -]/g,'_')+'.json');
}
async function importCardConjurer(){
  const file=await chooseFile('.cardconjurer,.json');if(!file)return;
  if(file.size>20*1024**2)throw new Error('Card Conjurer save limit is 20 MB.');
  const parsed=JSON.parse(await file.text());
  const entries=Array.isArray(parsed)?parsed:[parsed];
  if(!entries.length||entries.length>40)throw new Error('Choose a save with 1–40 card faces.');
  const host=modal('Choose a source card','',{size:'large'});
  const body=$('.modal-body',host);body.append(element('p','Rendering each source card. Choose the image whose frame you want to reuse. Artwork and set symbols are removed during conversion.','muted'));
  const grid=element('div','','template-grid');body.append(grid);
  const urls=[];let index=0;
  try{
    await renderTemplateSource(entries,async(target,blob)=>{
      const position=index++;const url=URL.createObjectURL(blob);urls.push(url);
      const choice=element('button','','printing-option');choice.type='button';choice.style.cursor='pointer';
      const image=document.createElement('img');image.src=url;image.alt=target.name;
      choice.append(image,element('small',target.name));
      choice.onclick=()=>attempt(async()=>{
        closeModal();for(const current of urls)URL.revokeObjectURL(current);
        const source=entries[position].data||entries[position];
        const model=await api('/api/templates/convert-cardconjurer',{source,name:target.name,group:'standard'});
        editTemplate(model);
      });
      grid.append(choice);
    });
  }
  catch(error){for(const url of urls)URL.revokeObjectURL(url);closeModal();throw error;}
}

function editTemplate(original){
  if(original.schemaVersion!==2)throw new Error('This legacy template still works in decks. Export its Card Conjurer source and import it through the visual conversion workflow to edit it.');
  const model=structuredClone(original);
  let previewUrl=null;
  let approved=false;
  let selectedRegion='title';
  const host=modal(model.id?'Edit Template':'Create Template','',{size:'large',
    footer:'<button class="button" id="preview-template">Preview difficult card</button><button class="button primary" id="save-template" disabled>Save template</button>',
    onClose:()=>{if(previewUrl)URL.revokeObjectURL(previewUrl);return true;}});
  const body=$('.modal-body',host);
  const form=element('div','','two-col');
  const nameLabel=element('label','','field');nameLabel.append(element('span','Template name'));
  const name=document.createElement('input');name.maxLength=200;name.value=model.name||'';nameLabel.append(name);form.append(nameLabel);
  const groupLabel=element('label','','field');groupLabel.append(element('span','Base layout'));
  const groupSelect=document.createElement('select');
  for(const group of ordinary){const option=document.createElement('option');option.value=group;option.textContent=group;groupSelect.append(option);}
  groupSelect.value=model.baseGroup;groupLabel.append(groupSelect);form.append(groupLabel);body.append(form);
  body.append(element('h3','Supported card groups'));
  const groups=element('div','','group-checkboxes');
  for(const group of ordinary){
    const label=element('label','','check-line');const checkbox=document.createElement('input');
    checkbox.type='checkbox';checkbox.value=group;checkbox.checked=model.groups.includes(group);
    label.append(checkbox,element('span',group));groups.append(label);
  }
  body.append(groups);
  const legendaryLabel=element('label','','check-line');const legendary=document.createElement('input');
  legendary.type='checkbox';legendary.checked=!!model.legendary;
  legendaryLabel.append(legendary,element('span','This frame supports legendary cards'));body.append(legendaryLabel);

  body.append(element('h3','Frame layers'));
  const layers=element('div','','stack');body.append(layers);
  const drawLayers=()=>{
    layers.replaceChildren();
    for(const [index,frame] of model.data.frames.entries()){
      const row=element('div','','trash-row');row.append(element('span',frame.name||`Layer ${index+1}`));
      const actions=element('div','','actions');
      if(index)actions.append(button('↑',()=>{[model.data.frames[index-1],model.data.frames[index]]=[model.data.frames[index],model.data.frames[index-1]];drawLayers();invalidate();},'button quiet small'));
      actions.append(button('Remove',()=>{model.data.frames.splice(index,1);drawLayers();invalidate();},'button quiet small'));
      row.append(actions);layers.append(row);
    }
  };
  body.append(button('Add complete frame image',async()=>{
    const file=await chooseFile('image/*');if(!file)return;
    const asset=await uploadImage(file);model.data.frames.push({name:file.name,src:`/api/assets/${asset.id}`,masks:[],bounds:{x:0,y:0,width:1,height:1}});
    drawLayers();invalidate();
  },'button small'));
  drawLayers();

  body.append(element('h3','Dynamic card regions'));
  body.append(element('p','Each region uses Bulk Proxy Forge’s calculated card layout, with optional normalized offsets. Select one to inspect its outline after preview.','muted'));
  const regions=element('div','','stack');body.append(regions);
  const drawRegions=()=>{
    regions.replaceChildren();
    for(const [slot,region] of Object.entries(model.regions)){
      const row=element('div','','well');row.style.display='flex';row.style.alignItems='center';row.style.gap='10px';row.style.flexWrap='wrap';
      const focus=button(slot,()=>{selectedRegion=slot;drawOverlay();},'button quiet small');row.append(focus);
      const select=document.createElement('select');
      for(const [field,label] of Object.entries(fields)){
        const option=document.createElement('option');option.value=field;option.textContent=label;select.append(option);
      }
      select.value=region.field;select.onchange=()=>{region.field=select.value;invalidate();};row.append(select);
      for(const key of ['x','y','width','height']){
        const label=element('label',key+' ','muted');const input=document.createElement('input');
        input.type='number';input.step='0.001';input.min='-0.5';input.max='0.5';input.style.width='74px';
        input.value=region.offset?.[key]||0;
        input.onchange=()=>{region.offset=region.offset||{};region.offset[key]=Number(input.value);invalidate();};
        label.append(input);row.append(label);
      }
      regions.append(row);
    }
    regions.append(button('Set symbol region',()=>{selectedRegion='setSymbol';drawOverlay();},'button quiet small'));
  };
  drawRegions();
  const preview=element('div','','section-gap');preview.style.maxWidth='420px';preview.style.position='relative';
  const previewImage=document.createElement('img');previewImage.style.width='100%';previewImage.style.display='block';
  const overlay=element('div');overlay.style.position='absolute';overlay.style.inset='0';overlay.style.pointerEvents='none';
  preview.append(previewImage,overlay);body.append(preview);
  let previewData=null;
  function drawOverlay(){
    overlay.replaceChildren();if(!previewData)return;
    const box=selectedRegion==='setSymbol'?previewData.setSymbolBounds:previewData.text?.[selectedRegion];
    if(!box)return;
    const outline=element('div');outline.style.position='absolute';outline.style.border='2px solid #ffb44d';
    outline.style.background='#ffb44d22';outline.style.left=`${(box.x||0)*100}%`;outline.style.top=`${(box.y||0)*100}%`;
    outline.style.width=`${(box.width||0)*100}%`;outline.style.height=`${(box.height||0)*100}%`;
    overlay.append(outline);
  }
  function invalidate(){approved=false;$('#save-template').disabled=true;}
  for(const control of [name,groupSelect,legendary,...groups.querySelectorAll('input')])control.addEventListener('change',invalidate);
  $('#preview-template').onclick=()=>attempt(async()=>{
    model.name=name.value.trim();model.baseGroup=groupSelect.value;model.groups=[...groups.querySelectorAll('input:checked')].map(item=>item.value);
    model.legendary=legendary.checked;
    if(!model.groups.includes(model.baseGroup))throw new Error('Select the base layout among supported groups.');
    let blob=null;
    const plan=await renderTemplateModel(model,async(target,image)=>{blob=image;});
    if(previewUrl)URL.revokeObjectURL(previewUrl);
    previewUrl=URL.createObjectURL(blob);previewImage.src=previewUrl;
    const target=plan.targets[0];const detail=await api(`/api/render-sessions/${plan.id}/${target.key}`);
    previewData=detail.data;drawOverlay();approved=true;$('#save-template').disabled=false;
  });
  $('#save-template').onclick=()=>attempt(async()=>{
    if(!approved)throw new Error('Preview this template before saving.');
    const saved=await api('/api/templates',model);closeModal();await showTemplates();toast(`${saved.name} saved.`);
  });
}
