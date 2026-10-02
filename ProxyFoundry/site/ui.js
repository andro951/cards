import {recordDiagnostic,downloadBrowserDiagnostics} from './diagnostics.js';
import {WorkCoordinator} from './work.js';
export const $=(s,root=document)=>root.querySelector(s);
export const $$=(s,root=document)=>[...root.querySelectorAll(s)];
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const work=new WorkCoordinator(()=>refreshWorkActivity());
export const state={csrf:'',bootstrap:null,decks:[],templates:[],selected:new Set(),dirty:false,get busy(){return work.busy},helper:false,route:'decks',activeDeck:null,routeEpoch:0,deckTab:'cards'};
export const bytes=n=>n>=1024**3?(n/1024**3).toFixed(1)+' GB':n>=1024**2?(n/1024**2).toFixed(1)+' MB':Math.ceil(n/1024)+' KB';
export const date=t=>t?new Date(t*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'}):'—';
export const asset=id=>id?'/api/assets/'+id:'';
export const thumbnail=url=>/^\/api\/assets\/[0-9a-f]{64}$/.test(url||'')?url+'/thumbnail':url;
export const humanStatus=s=>({draft:'Needs preparation',prepared:'Ready to render',ready:'Ready to print',attention:'Needs attention'}[s]||s||'Draft');
export const badge=s=>`<span class="badge ${esc(s)}">${esc(humanStatus(s))}</span>`;
export const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export function requireDeckAvailable(id,owner=null){if(id)work.requireAvailable(['deck:'+id],owner);}
export function requireWorkspaceIdle(){work.requireIdle();}
function mutationResources(path,data){
  const match=/^\/api\/decks\/([-a-f0-9]{36})(?:\/(save|add|delete|restore|prepare|cards)(?:\/|$))/.exec(path);
  if(match)return ['deck:'+match[1]];
  if(['/api/orders/plan','/api/orders/build'].includes(path))return (data?.deckIds||[]).map(id=>'deck:'+id);
  if(['/api/images/delete-all','/api/backups/import-selected','/api/backups/restore'].includes(path))return ['workspace'];
  return [];
}
export async function api(path,data,method='POST',owner=null){
  const resources=data!==undefined&&method==='POST'?mutationResources(path,data):[];
  if(data!==undefined&&method==='POST')work.requireAvailable(resources,owner);
  const lease=!owner&&resources.length?work.begin({label:resources.includes('workspace')?'Update workspace':'Save deck changes',resources}):null;
  try{return await requestApi(path,data,method);}
  finally{if(lease)work.finish(lease);}
}
async function requestApi(path,data,method){
  const opt=data===undefined?{}:{method,headers:{'Content-Type':'application/json','X-Proxy-CSRF':state.csrf},body:JSON.stringify(data)};
  const r=await fetch(path,opt);const text=await r.text();let result;
  try{result=JSON.parse(text)}catch(error){
    recordDiagnostic('invalid API response',`${path}: HTTP ${r.status}; ${r.headers.get('Content-Type')}; ${text.length} characters; ${error.message}; start=${text.slice(0,300)}; end=${text.slice(-300)}`);
    throw new Error(`The workspace returned an unreadable response (${path}, HTTP ${r.status}). Reload the page and try again.`);
  }
  if(!r.ok){recordDiagnostic('API failure',`${path}: HTTP ${r.status}; ${result.error||'Request failed.'}`);throw new Error(result.error||'Request failed.');}return result;
}
export function showWorkspaceError(error,retry=null){
  recordDiagnostic('workspace error',error.stack||error.message);
  const notice=document.createElement('div');notice.className='notice error';notice.textContent=error.message;
  const diagnostics=document.createElement('button');diagnostics.className='button';diagnostics.textContent='Download browser diagnostics';
  diagnostics.onclick=downloadBrowserDiagnostics;
  $('#main').replaceChildren(notice,diagnostics);
  if(retry){
    const button=document.createElement('button');button.className='button';button.textContent='Retry';button.onclick=retry;
    $('#main').append(button);
  }
}
export async function blobRequest(path,body,mime='application/octet-stream',headers={}){
  const r=await fetch(path,{method:'POST',headers:{'X-Proxy-CSRF':state.csrf,'Content-Type':mime,...headers},body});
  if(!r.ok){const d=await r.json().catch(()=>({}));throw new Error(d.error||'Upload failed.');}return r.json();
}
export async function downloadPost(path,data,filename){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Proxy-CSRF':state.csrf},body:JSON.stringify(data)});
  if(!r.ok)throw new Error((await r.json()).error||'Export failed.');downloadBlob(await r.blob(),filename);
}
export function downloadBlob(blob,name){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
export async function saveApiFile(path,name,size=null){
  let handle=null;
  //Small exports use the browser download folder; large files stream to disk.
  const smallFile=Number.isFinite(size)&&size>=0&&size<=50*1024*1024;
  if(!smallFile&&state.bootstrap?.browser&&typeof window.showSaveFilePicker==='function'){
    try{handle=await window.showSaveFilePicker({suggestedName:name});}
    catch(error){if(error.name==='AbortError')return;throw error;}
  }
  if(handle){
    const writer=await handle.createWritable();
    try{
      let offset=0,total=null;
      while(total===null||offset<total){
        const response=await fetch(path,{headers:{Range:`bytes=${offset}-${offset+4*1024*1024-1}`}});
        if(!response.ok)throw new Error((await response.json().catch(()=>({}))).error||'Download failed.');
        const match=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range')||'');
        if(response.status!==206||!match||Number(match[1])!==offset)throw new Error('The saved file did not return a valid download range.');
        const chunk=await response.arrayBuffer();
        if(chunk.byteLength!==Number(match[2])-offset+1)throw new Error('The download was incomplete.');
        await writer.write(chunk);offset+=chunk.byteLength;total=Number(match[3]);
      }
      await writer.close();return;
    }catch(error){await writer.abort().catch(()=>{});throw error;}
  }
  const response=await fetch(path);
  if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error||'Download failed.');}
  downloadBlob(await response.blob(),name);
}
export function toast(message,error=false){
  recordDiagnostic(error?'error notification':'notification',message);
  const el=document.createElement('div');el.className='toast'+(error?' error':'');el.setAttribute('role',error?'alert':'status');el.innerHTML=`<span>${esc(message)}</span><button aria-label="Dismiss notification">×</button>`;$('#toast-host').append(el);$('button',el).onclick=()=>el.remove();setTimeout(()=>el.remove(),error?14000:6500);
}
export async function attempt(fn){try{return await fn()}catch(e){recordDiagnostic('caught error',e.stack||e.message);console.error(e);toast(e.message,true);return null;}}
let lastFocus=null,modalCloser=null;
export function closeModal(){if(modalCloser&&!modalCloser())return;$('#modal-host').replaceChildren();document.body.classList.remove('no-scroll');lastFocus?.focus?.();modalCloser=null;}
export function modal(title,body,{size='',footer='',onClose=null}={}){
  recordDiagnostic('dialog',title);
  lastFocus=document.activeElement;modalCloser=onClose;$('#modal-host').innerHTML=`<div class="modal-backdrop"><section class="modal ${esc(size)}" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header class="modal-header"><h2 id="modal-title">${esc(title)}</h2><button class="button quiet icon" id="modal-close" aria-label="Close dialog">×</button></header><div class="modal-body">${body}</div>${footer?`<footer class="modal-footer">${footer}</footer>`:''}</section></div>`;
  document.body.classList.add('no-scroll');$('#modal-close').onclick=closeModal;
  const el=$('.modal');$('.modal-backdrop').addEventListener('click',e=>{if(e.target.classList.contains('modal-backdrop'))closeModal();});
  el.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();closeModal();}
    if(e.key==='Tab'){const nodes=$$('button,a,input,select,textarea,summary,[tabindex="0"]',el).filter(x=>!x.disabled&&x.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}
  });
  // Focus before returning the mounted dialog. A delayed focus callback can steal
  // typing from a field the user has already chosen (including the artist credit).
  const first=$('input:not([type=file]):not([disabled]),textarea:not([disabled])',el)||$('#modal-close',el);
  first?.focus({preventScroll:true});return el;
}
export function confirmAction(title,text,label='Continue',danger=false){return new Promise(resolve=>{
  modal(title,`<p class="muted">${esc(text)}</p>`,{size:'small',footer:`<button class="button quiet" id="confirm-no">Cancel</button><button class="button ${danger?'danger':'primary'}" id="confirm-yes">${esc(label)}</button>`,onClose:()=>{resolve(false);return true;}});
  $('#confirm-no').onclick=()=>closeModal();$('#confirm-yes').onclick=()=>{modalCloser=null;closeModal();resolve(true);};
});}
export function errorBox(el,message){recordDiagnostic('form error',message);let b=$('.form-error',el);if(!b){b=document.createElement('div');b.className='notice error form-error';b.setAttribute('role','alert');el.prepend(b)}b.textContent=message;b.scrollIntoView({block:'nearest'});}
export function activity(kind,title,detail,done=0,total=0,owner=null){
  if(owner){work.update(owner,{kind,title,detail,done,total});return;}
  drawActivity(kind,title,detail,done,total);
}
function drawActivity(kind,title,detail,done=0,total=0){
  $('#activity').classList.remove('hidden');$('#activity-kind').textContent=kind;$('#activity-title').textContent=title;$('#activity-detail').textContent=detail||'';$('#activity-count').textContent=total?`${done} / ${total}`:'';
  const pct=total?Math.min(100,done/total*100):4;$('#activity-bar').style.width=pct+'%';$('.progress-track').setAttribute('aria-valuenow',Math.round(pct));
  const line=`${new Date().toLocaleTimeString()} · ${detail||title}`;
  if(!$('#activity-log').textContent.endsWith(line+'\n'))$('#activity-log').textContent=($('#activity-log').textContent+line+'\n').split('\n').slice(-80).join('\n');
}
function refreshWorkActivity(){
  const panel=$('#activity');if(!panel)return;
  const task=work.visible();
  if(task){
    const p=task.progress;drawActivity(p.kind,p.title,p.detail,p.done,p.total);
    const cancel=$('#activity-cancel');cancel.textContent=task.controller.signal.aborted?'Cancelling…':'Cancel';cancel.disabled=task.controller.signal.aborted;cancel.onclick=()=>task.controller.abort();
  }
  let queued=$('#queued-work');
  if(!queued){queued=document.createElement('div');queued.id='queued-work';queued.style.display='grid';queued.style.gap='8px';panel.append(queued);}
  queued.replaceChildren();
  for(const entry of work.queue){
    const row=document.createElement('div');row.style.display='flex';row.style.alignItems='center';row.style.gap='12px';
    const label=document.createElement('span');label.textContent=entry.task.label+' · queued';
    const cancel=document.createElement('button');cancel.className='button quiet small';cancel.textContent='Cancel queued task';cancel.setAttribute('aria-label','Cancel queued '+entry.task.label);cancel.onclick=()=>entry.task.controller.abort();
    row.append(label,cancel);queued.append(row);panel.classList.remove('hidden');
  }
}
export function endActivity(message,error=false,owner=null){
  if(owner&&work.visible()!==owner)return;
  $('#activity-title').textContent=message;$('#activity-detail').textContent=error?'Completed images are saved. Details are in the activity log.':'Your progress is saved.';$('#activity-cancel').textContent='Dismiss';$('#activity-cancel').disabled=false;$('#activity-cancel').onclick=()=>$('#activity').classList.add('hidden');if(!error)setTimeout(()=>{if(!work.busy&&$('#activity-title').textContent===message)$('#activity').classList.add('hidden')},6000);
}
export async function job(path,data,{label='Working',onProgress=null,signal=null,owner=null,resources=null}={}){
  const task=owner||work.begin({label,resources:resources||mutationResources(path,data),signal});
  signal=task.controller.signal;let ident=null;
  const cancel=()=>{if(ident)api('/api/jobs/'+ident+'/cancel',{},'POST',task).catch(error=>recordDiagnostic('cancel task',error.message));};
  signal?.addEventListener('abort',cancel,{once:true});
  try{
    if(signal?.aborted)throw new Error('Task cancelled.');
    activity(label,'Starting…','Starting task',0,0,task);
    const result=await api(path,data,'POST',task);if(!result?.id)throw new Error('The app did not start the task.');ident=result.id;
    if(signal?.aborted)cancel();
    while(true){
      await sleep(400);const j=await api('/api/jobs/'+ident);activity(label,j.kind,j.message,j.done,j.total,task);onProgress?.(j);
      if(j.state==='done'){if(!owner)endActivity('Complete',false,task);return j.result;}
      if(j.state==='failed'||j.state==='cancelled'){if(!owner)endActivity(j.message,true,task);throw new Error(j.error||j.message);}
    }
  }catch(error){if(!owner)endActivity(error.message,true,task);throw error;}
  finally{signal?.removeEventListener('abort',cancel);if(!owner)work.finish(task);}
}
export async function uploadImage(file,{symbol=false,back=false}={}){
  if(!file)throw new Error('Choose an image.');if(file.size>64*1024**2)throw new Error('Choose an image under 64 MB.');
  let blob=file;
  if(file.name.toLowerCase().endsWith('.svg')){
    const raw=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<raw.length;i+=32768)text+=String.fromCharCode(...raw.subarray(i,i+32768));
    const safe=await api('/api/svg/validate',{base64:btoa(text)});const url=URL.createObjectURL(new Blob([safe.svg],{type:'image/svg+xml'}));
    try{const im=await image(url);const c=document.createElement('canvas');const scale=512/Math.max(im.naturalWidth||512,im.naturalHeight||512);c.width=Math.max(1,Math.round((im.naturalWidth||512)*scale));c.height=Math.max(1,Math.round((im.naturalHeight||512)*scale));c.getContext('2d').drawImage(im,0,0,c.width,c.height);blob=await new Promise(r=>c.toBlob(r,'image/png'));}finally{URL.revokeObjectURL(url);}
  }
  const kind=symbol?'symbol':back?'back':'';
  return blobRequest('/api/uploads'+(kind?('?kind='+encodeURIComponent(kind)):''),blob,'image/png',{'X-Filename':encodeURIComponent(file.name.replace(/\.svg$/i,'.png'))});
}
export function image(src){return new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('Could not decode image.'));i.src=src;});}
export async function uploadFolder(files,onProgress=()=>{},source=null){
  const images=[...files].filter(f=>/\.(png|jpe?g|webp|gif)$/i.test(f.name));if(images.length>5000)throw new Error('Select at most 5,000 art images.');
  const result={},names={};let done=0;
  for(const file of images){const a=await uploadImage(file);let key=a.stem,duplicate=1;while(Object.hasOwn(result,key))key=a.stem+'__'+(++duplicate);result[key]=a.id;names[key]=file.artworkPath||file.webkitRelativePath?.split('/').slice(1).join('/')||file.name;onProgress?.(++done,images.length);}
  if(!images.length)throw new Error('No supported images were found in that folder.');if(source)source.localNames=names;return result;
}
export function loading(text='Loading…'){return `<div class="loading-state"><span class="spinner"></span>${esc(text)}</div>`;}
export function empty(title,text,button=''){return `<div class="empty-state"><span class="eyebrow">MAKE IT YOURS</span><h2>${esc(title)}</h2><p>${esc(text)}</p>${button}</div>`;}
export function nav(hash){if(state.dirty&&!window.confirm('Leave without saving these setup changes?'))return;state.dirty=false;location.hash=hash;}
window.addEventListener('beforeunload',e=>{if(state.dirty||state.busy){e.preventDefault();e.returnValue='';}});