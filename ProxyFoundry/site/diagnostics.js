const storageKey='bulk-proxy-forge-browser-diagnostics';
const originalWarn=console.warn.bind(console);
let previousSession=null;
try{previousSession=JSON.parse(localStorage.getItem(storageKey)||'null');}
catch(error){console.warn('Previous browser diagnostics could not be read:',error);}
const entries=[];
let engineStatus='Not started';
let persistTimer=null;
const cleanDetail=detail=>String(detail).replace(/github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|Bearer\s+[^\s"']+/g,`[redacted credential]`).slice(0,8000);
const persist=()=>{
  clearTimeout(persistTimer);persistTimer=null;
  try{localStorage.setItem(storageKey,JSON.stringify({url:location.href,engineStatus,entries}));}
  catch(error){originalWarn('Browser diagnostics could not be saved:',error);}
};
export function recordDiagnostic(kind,detail){
  entries.push({time:new Date().toISOString(),kind,detail:cleanDetail(detail)});
  if(entries.length>500) {
    const timing=entries.findIndex(entry=>entry.kind==='timing');
    entries.splice(timing<0?0:timing,1);
  }
  if(!persistTimer)persistTimer=setTimeout(persist,100);
}
export function setEngineStatus(status){
  engineStatus=status;
  recordDiagnostic('engine',status);
}
export function browserDiagnosticReport(){
  persist();
  return {url:location.href,userAgent:navigator.userAgent,engineStatus,
    serviceWorker:navigator.serviceWorker?.controller?.scriptURL||null,entries,previousSession};
}
export async function diagnosticZipRequest(csrf){
  return fetch('/api/diagnostics.zip',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json','X-Proxy-CSRF':csrf},body:JSON.stringify({browser:browserDiagnosticReport()})});
}
export function downloadBrowserDiagnostics(){
  const report=browserDiagnosticReport();
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download='BulkProxyForge_Browser_Diagnostics.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
}
window.addEventListener('error',event=>recordDiagnostic('browser error',event.error?.stack||event.message));
window.addEventListener('unhandledrejection',event=>recordDiagnostic('unhandled rejection',event.reason?.stack||event.reason));
window.addEventListener('pagehide',persist);
for(const level of ['warn','error']) {
  const original=console[level].bind(console);
  console[level]=(...values)=>{
    recordDiagnostic('console '+level,values.map(value=>value instanceof Error?value.stack||value.message:String(value)).join(' '));
    original(...values);
  };
}

window.document.addEventListener('click',event=>{
  const control=event.target.closest?.('button,a,summary,[role="button"]');
  if(control)recordDiagnostic('user action',control.getAttribute('aria-label')||control.textContent.trim());
},true);
const statusTexts=new WeakMap();
new MutationObserver(mutations=>{
  const statuses=new Set();
  for(const mutation of mutations) {
    const parent=mutation.target.nodeType===1?mutation.target:mutation.target.parentElement;
    const status=parent?.closest('[role="status"],[role="alert"]');
    if(status)statuses.add(status);
    for(const added of mutation.addedNodes) {
      if(added.nodeType!==1)continue;
      if(added.matches('[role="status"],[role="alert"]'))statuses.add(added);
      for(const node of added.querySelectorAll('[role="status"],[role="alert"]'))statuses.add(node);
    }
  }

  for(const status of statuses) {
    if(status.classList.contains('toast')||status.classList.contains('form-error'))continue;
    const text=status.textContent.trim();
    if(text&&text!==statusTexts.get(status))recordDiagnostic('displayed '+status.getAttribute('role'),text);
    statusTexts.set(status,text);
  }
}).observe(window.document.documentElement,{subtree:true,childList:true,characterData:true});