import {$,$$,esc,state,api,attempt,toast,modal,closeModal,errorBox,confirmAction,downloadBlob,empty,nav} from './ui.js';
import {pickFile} from './setup.js';
const ordinary=['standard','legendary','land','legendary-land','basic-land'];
const fieldNames={title:'Card name',type:'Type line',mana:'Mana cost',rules:'Rules + flavor',flavor:'Flavor text',pt:'Power / toughness',loyalty:'Starting loyalty',defense:'Defense','face2.title':'Other face · name','face2.type':'Other face · type','face2.mana':'Other face · mana','face2.rules':'Other face · rules'};
for(let i=1;i<=12;i++)fieldNames['line'+i]='Rules line '+i;
export async function showTemplates(){
  state.templates=await api('/api/templates');
  const built=state.templates.filter(t=>!t.data),custom=state.templates.filter(t=>t.data);
  $('#main').innerHTML=`<div class="page-head"><div><span class="eyebrow">A STYLE THAT’S YOURS</span><h1>Templates</h1><p>Use the approved Card Tools frames, customize a copy, or upload your own CardConjurer template.</p></div><div class="actions"><button class="button" id="upload-template">Upload template</button><button class="button primary" id="new-template">＋ Create template</button></div></div>
  <div class="notice info">The built-in recipes are protected. Creating or editing a template always makes a separate custom style; it never changes your approved originals.</div>
  <h2 class="section-gap">Built-in styles</h2><div class="template-grid">${built.map(t=>`<article class="template-card"><div class="template-art ${esc(t.id)}" aria-hidden="true"><div class="frame-demo"><span></span><i></i><b></b></div><span class="badge">BUILT IN</span></div><div class="deck-content"><h3>${esc(t.name)}</h3><p class="muted">${esc(t.description)}</p><div class="template-actions">${t.id==='auto'?'<span class="subtitle-line">Type-specific recipes · unchanged</span>':`<button class="button small" data-derive="${esc(t.id)}">Customize a copy</button>`}</div></div></article>`).join('')}</div>
  <div class="panel section-gap"><div class="panel-head"><div><h2>Your custom templates</h2><p>Assign styles by structural card group in each deck’s Art & setup tab. Unsupported group/template combinations are blocked before printing.</p></div></div>${custom.length?`<div class="template-grid">${custom.map(t=>`<article class="well"><span class="eyebrow">CUSTOM TEMPLATE</span><h3>${esc(t.name)}</h3><p class="muted">${(t.groups||[]).map(g=>esc(state.bootstrap.groups[g]||g)).join(' · ')}</p><p class="subtitle-line">${t.legendary?'Supports legendary cards':'Nonlegendary only'} · ${t.data.width} × ${t.data.height}</p><div class="actions"><button class="button small" data-edit="${t.id}">Edit</button><button class="button quiet small" data-export="${t.id}">Export</button><button class="button quiet small" data-delete="${t.id}">Delete</button></div></article>`).join('')}</div>`:empty('Make your first custom style','Start with a built-in frame or upload a .cardconjurer save. Map its text boxes to card fields, then select the groups it supports.',`<button class="button" id="empty-create">Create a template</button>`)}</div>`;
  for(const id of ['new-template','empty-create'])if($('#'+id))$('#'+id).onclick=()=>attempt(()=>createFromSeed());
  $('#upload-template').onclick=()=>attempt(uploadTemplate);
  $$('[data-derive]').forEach(b=>b.onclick=()=>attempt(()=>createFromSeed(b.dataset.derive)));
  $$('[data-edit]').forEach(b=>b.onclick=()=>editTemplate(custom.find(t=>t.id===b.dataset.edit)));
  $$('[data-export]').forEach(b=>b.onclick=()=>{const t=custom.find(t=>t.id===b.dataset.export);downloadBlob(new Blob([JSON.stringify([{key:t.name,data:t.data}],null,2)],{type:'application/json'}),t.name.replace(/[^A-Za-z0-9_. -]/g,'_')+'.cardconjurer');});
  $$('[data-delete]').forEach(b=>b.onclick=()=>attempt(async()=>{const t=custom.find(t=>t.id===b.dataset.delete);if(!await confirmAction('Delete '+t.name+'?','Decks using this template will need a replacement before they can be regenerated. Existing saved PNGs are not erased.','Delete template',true))return;await api('/api/templates/'+t.id+'/delete',{revision:t.revision});await showTemplates();}));
}
async function createFromSeed(kind='normal'){
  const data=await api('/api/templates/seed?kind='+encodeURIComponent(kind));
  editTemplate({name:'My '+({normal:'classic card',land:'full-art land','legend-land':'crowned full art'}[kind]||'card')+' style',data,groups:kind==='legend-land'?ordinary:['standard','land','basic-land'],legendary:kind==='legend-land',mapping:{}});
}
async function uploadTemplate(){
  const f=await pickFile('.cardconjurer,.json');if(!f)return;if(f.size>20*1024**2)throw new Error('Template file limit is 20 MB.');
  let input;try{input=JSON.parse(await f.text())}catch{throw new Error('This file is not valid CardConjurer JSON.');}
  const entries=Array.isArray(input)?input:[input];if(!entries.length)throw new Error('The template file is empty.');
  const open=e=>editTemplate({name:e.key||e.name||f.name,data:e.data||e,groups:['standard'],legendary:false,mapping:{}});
  if(entries.length===1){open(entries[0]);return;}
  if(entries.length>2000)throw new Error('Select a template save containing at most 2,000 faces.');
  const host=modal('Choose a template face',`<p class="muted">This save has ${entries.length} faces. Choose the one to use as a template.</p><label class="field"><span>Template face</span><select id="choose-template-face">${entries.map((e,i)=>`<option value="${i}">${esc(e.key||e.name||'Face '+(i+1))}</option>`).join('')}</select></label>`,{footer:'<button class="button primary" id="select-template-face">Use selected face</button>'});
  $('#select-template-face').onclick=()=>{const e=entries[+$('#choose-template-face').value];closeModal();open(e);};
}
function editTemplate(input){
  const template=structuredClone(input);let data=template.data,mapping=template.mapping||{},changed=false;
  const host=modal(template.id?'Edit custom template':'Create a custom template',`<div class="two-col"><label class="field"><span>Template name</span><input id="template-name" value="${esc(template.name)}" maxlength="200"></label><label class="check-line"><input type="checkbox" id="template-legendary" ${template.legendary?'checked':''}><span>Supports legendary cards<small>Only enable this when your frame has a working crown or another intentional legendary treatment.</small></span></label></div>
  <h3>Which card groups does this template support?</h3><p class="muted">Only select groups your layout was designed to display. A template for split or Adventure cards must include the second face’s rules, not merely its title.</p><div class="group-checkboxes">${Object.entries(state.bootstrap.groups).map(([k,label])=>`<label class="check-line"><input type="checkbox" name="template-groups" value="${esc(k)}" ${(template.groups||[]).includes(k)?'checked':''}><span>${esc(label)}</span></label>`).join('')}</div>
  <section class="well section-gap"><h3>Connect text boxes to card fields</h3><p class="muted">Choose “Keep template text” for static labels. Named boxes keep their existing position, font, size, and formatting.</p><div id="mapping-table"></div></section>
  <details class="well section-gap"><summary>Template data & advanced editing</summary><p class="muted">Edit the native CardConjurer data below, or design it in CardConjurer and upload the save. No frame or typography is reimplemented here. Keep all asset URLs public or embedded.</p><textarea id="template-data" class="json-editor" rows="16" spellcheck="false" aria-label="CardConjurer template JSON">${esc(JSON.stringify(data,null,2))}</textarea><button class="button small" id="reload-slots">Apply JSON & refresh text slots</button></details>
  <div class="notice">Template changes affect a deck after it is prepared again. Review a rendered example before ordering. The original built-in templates remain unchanged.</div>`,{size:'large',footer:'<span class="footer-hint">Native CardConjurer template · custom copy</span><button class="button primary" id="save-template">Save template</button>',onClose:()=>!changed||window.confirm('Discard unsaved template changes?')});
  function slots(){
    const defaults=['title','type','mana','rules','flavor','pt','loyalty','defense'];
    $('#mapping-table').innerHTML=`<div class="template-mapping">${Object.entries(data.text||{}).map(([slot,obj])=>{const value=mapping[slot]??(defaults.includes(slot)?slot:'');return `<label class="field"><span>${esc(obj.name||slot)} <small>${esc(slot)}</small></span><select data-slot="${esc(slot)}"><option value="">Keep template text</option>${Object.entries(fieldNames).map(([key,label])=>`<option value="${esc(key)}" ${value===key?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`}).join('')}</div>`;
    $$('[data-slot]',host).forEach(s=>{mapping[s.dataset.slot]=s.value;s.onchange=()=>{mapping[s.dataset.slot]=s.value;changed=true;};});
  }
  slots();$$('input,textarea',host).forEach(e=>e.addEventListener('input',()=>{changed=true;}));
  $('#reload-slots').onclick=()=>{try{data=JSON.parse($('#template-data').value);if(data.data)data=data.data;if(!data.text||typeof data.text!=='object')throw new Error('Template text{} is missing.');slots();toast('Text slots refreshed.')}catch(e){errorBox($('.modal-body',host),e.message)}};
  $('#save-template').onclick=async()=>{
    try{
      const raw=JSON.parse($('#template-data').value);data=raw.data||raw;
      const payload={...template,name:$('#template-name').value.trim(),legendary:$('#template-legendary').checked,groups:$$('[name="template-groups"]:checked',host).map(e=>e.value),data,mapping:Object.fromEntries(Object.entries(mapping).filter(([slot])=>slot in data.text))};
      $('#save-template').disabled=true;await api('/api/templates',payload);changed=false;closeModal();await showTemplates();toast('Custom template saved. Select it in a deck’s Art & setup tab.');
    }catch(e){errorBox($('.modal-body',host),e.message);if($('#save-template'))$('#save-template').disabled=false;}
  };
}
