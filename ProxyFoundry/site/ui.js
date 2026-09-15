export const $=(s,root=document)=>root.querySelector(s);
export const $$=(s,root=document)=>[...root.querySelectorAll(s)];
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const state={csrf:'',bootstrap:null,decks:[],templates:[],selected:new Set(),dirty:false,busy:false,helper:false,route:'decks',activeDeck:null};
export const bytes=n=>n>=1024**3?(n/1024**3).toFixed(1)+' GB':n>=1024**2?(n/1024**2).toFixed(1)+' MB':Math.ceil(n/1024)+' KB';
export const date=t=>t?new Date(t*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'}):'—';
export const asset=id=>id?'/api/assets/'+id:'';
export const humanStatus=s=>({draft:'Needs preparation',prepared:'Ready to render',ready:'Ready to print',attention:'Needs attention'}[s]||s||'Draft');
export const badge=s=>`<span class="badge ${esc(s)}">${esc(humanStatus(s))}</span>`;
export const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export async function api(path,data,method='POST'){
  const opt=data===undefined?{}:{method,headers:{'Content-Type':'application/json','X-Proxy-CSRF':state.csrf},body:JSON.stringify(data)};
  const r=await fetch(path,opt);const text=await r.text();let result;
  try{result=JSON.parse(text)}catch{throw new Error('The local app returned an unreadable response. Check that its launcher is still running.');}
  if(!r.ok)throw new Error(result.error||'Request failed.');return result;
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
export function toast(message,error=false){
  const el=document.createElement('div');el.className='toast'+(error?' error':'');el.setAttribute('role',error?'alert':'status');el.innerHTML=`<span>${esc(message)}</span><button aria-label="Dismiss notification">×</button>`;$('#toast-host').append(el);$('button',el).onclick=()=>el.remove();setTimeout(()=>el.remove(),error?14000:6500);
}
export async function attempt(fn){try{return await fn()}catch(e){console.error(e);toast(e.message,true);return null;}}
let lastFocus=null,modalCloser=null;
export function closeModal(){if(modalCloser&&!modalCloser())return;$('#modal-host').replaceChildren();document.body.classList.remove('no-scroll');lastFocus?.focus?.();modalCloser=null;}
export function modal(title,body,{size='',footer='',onClose=null}={}){
  lastFocus=document.activeElement;modalCloser=onClose;$('#modal-host').innerHTML=`<div class="modal-backdrop"><section class="modal ${esc(size)}" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header class="modal-header"><h2 id="modal-title">${esc(title)}</h2><button class="button quiet icon" id="modal-close" aria-label="Close dialog">×</button></header><div class="modal-body">${body}</div>${footer?`<footer class="modal-footer">${footer}</footer>`:''}</section></div>`;
  document.body.classList.add('no-scroll');$('#modal-close').onclick=closeModal;
  const el=$('.modal');$('.modal-backdrop').addEventListener('click',e=>{if(e.target.classList.contains('modal-backdrop'))closeModal();});
  el.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();closeModal();}
    if(e.key==='Tab'){const nodes=$$('button,a,input,select,textarea,summary,[tabindex="0"]',el).filter(x=>!x.disabled&&x.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}
  });
  setTimeout(()=>($('input:not([type=file]),textarea',el)||$('#modal-close')).focus(),20);return el;
}
export function confirmAction(title,text,label='Continue',danger=false){return new Promise(resolve=>{
  modal(title,`<p class="muted">${esc(text)}</p>`,{size:'small',footer:`<button class="button quiet" id="confirm-no">Cancel</button><button class="button ${danger?'danger':'primary'}" id="confirm-yes">${esc(label)}</button>`,onClose:()=>{resolve(false);return true;}});
  $('#confirm-no').onclick=()=>closeModal();$('#confirm-yes').onclick=()=>{modalCloser=null;closeModal();resolve(true);};
});}
export function errorBox(el,message){let b=$('.form-error',el);if(!b){b=document.createElement('div');b.className='notice error form-error';b.setAttribute('role','alert');el.prepend(b)}b.textContent=message;b.scrollIntoView({block:'nearest'});}
export function activity(kind,title,detail,done=0,total=0){
  $('#activity').classList.remove('hidden');$('#activity-kind').textContent=kind;$('#activity-title').textContent=title;$('#activity-detail').textContent=detail||'';$('#activity-count').textContent=total?`${done} / ${total}`:'';
  const pct=total?Math.min(100,done/total*100):4;$('#activity-bar').style.width=pct+'%';$('.progress-track').setAttribute('aria-valuenow',Math.round(pct));
  const line=`${new Date().toLocaleTimeString()} · ${detail||title}`;
  if(!$('#activity-log').textContent.endsWith(line+'\n'))$('#activity-log').textContent=($('#activity-log').textContent+line+'\n').split('\n').slice(-80).join('\n');
}
export function endActivity(message,error=false){$('#activity-title').textContent=message;$('#activity-detail').textContent=error?'Completed images are saved. Details are in the activity log.':'Your progress is saved.';$('#activity-cancel').textContent='Dismiss';$('#activity-cancel').disabled=false;$('#activity-cancel').onclick=()=>$('#activity').classList.add('hidden');if(!error)setTimeout(()=>{if($('#activity-title').textContent===message)$('#activity').classList.add('hidden')},6000);}
export async function job(path,data,{label='Working',onProgress=null}={}){
  const result=await api(path,data);if(!result?.id)throw new Error('The app did not start the task.');const ident=result.id;
  $('#activity-cancel').disabled=false;$('#activity-cancel').textContent='Cancel';$('#activity-cancel').onclick=()=>attempt(async()=>{await api('/api/jobs/'+ident+'/cancel',{});$('#activity-cancel').disabled=true;});
  activity(label,'Starting…','Starting task');
  while(true){
    await sleep(400);const j=await api('/api/jobs/'+ident);activity(label,j.kind,j.message,j.done,j.total);onProgress?.(j);
    if(j.state==='done'){endActivity('Complete');return j.result;}
    if(j.state==='failed'||j.state==='cancelled'){endActivity(j.message,true);throw new Error(j.error||j.message);}
  }
}
export async function uploadImage(file,{symbol=false}={}){
  if(!file)throw new Error('Choose an image.');if(file.size>64*1024**2)throw new Error('Choose an image under 64 MB.');
  let blob=file;
  if(file.name.toLowerCase().endsWith('.svg')){
    const raw=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<raw.length;i+=32768)text+=String.fromCharCode(...raw.subarray(i,i+32768));
    const safe=await api('/api/svg/validate',{base64:btoa(text)});const url=URL.createObjectURL(new Blob([safe.svg],{type:'image/svg+xml'}));
    try{const im=await image(url);const c=document.createElement('canvas');const scale=512/Math.max(im.naturalWidth||512,im.naturalHeight||512);c.width=Math.max(1,Math.round((im.naturalWidth||512)*scale));c.height=Math.max(1,Math.round((im.naturalHeight||512)*scale));c.getContext('2d').drawImage(im,0,0,c.width,c.height);blob=await new Promise(r=>c.toBlob(r,'image/png'));}finally{URL.revokeObjectURL(url);}
  }
  return blobRequest('/api/uploads'+(symbol?'?kind=symbol':''),blob,'image/png',{'X-Filename':encodeURIComponent(file.name.replace(/\.svg$/i,'.png'))});
}
export function image(src){return new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('Could not decode image.'));i.src=src;});}
export async function uploadFolder(files,onProgress=()=>{}){
  const images=[...files].filter(f=>/\.(png|jpe?g|webp|gif)$/i.test(f.name));if(images.length>5000)throw new Error('Select at most 5,000 art images.');
  const result={};let n=0;
  for(const file of images){const a=await uploadImage(file);if(result[a.stem])throw new Error('Two images have the same normalized card name: '+file.name);result[a.stem]=a.id;onProgress(++n,images.length);}
  if(!n)throw new Error('No supported images were found in that folder.');return result;
}
export function loading(text='Loading…'){return `<div class="loading-state"><span class="spinner"></span>${esc(text)}</div>`;}
export function empty(title,text,button=''){return `<div class="empty-state"><span class="eyebrow">MAKE IT YOURS</span><h2>${esc(title)}</h2><p>${esc(text)}</p>${button}</div>`;}
export function nav(hash){if(state.dirty&&!window.confirm('Leave without saving these setup changes?'))return;state.dirty=false;location.hash=hash;}
window.addEventListener('beforeunload',e=>{if(state.dirty||state.busy){e.preventDefault();e.returnValue='';}});
