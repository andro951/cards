const storageKey='bulk-proxy-forge-browser-diagnostics';
let previousSession=null;
try{previousSession=JSON.parse(localStorage.getItem(storageKey)||'null');}
catch(error){console.warn('Previous browser diagnostics could not be read:',error);}
const entries=[];
let engineStatus='Not started';
export function recordDiagnostic(kind,detail){
  entries.push({time:new Date().toISOString(),kind,detail:String(detail).slice(0,1500)});
  if(entries.length>40)
    entries.shift();
  try{localStorage.setItem(storageKey,JSON.stringify({url:location.href,engineStatus,entries}));}
  catch(error){console.warn('Browser diagnostics could not be saved:',error);}
}
export function setEngineStatus(status){
  engineStatus=status;
  recordDiagnostic('engine',status);
}
export function downloadBrowserDiagnostics(){
  const report={url:location.href,userAgent:navigator.userAgent,engineStatus,
    serviceWorker:navigator.serviceWorker?.controller?.scriptURL||null,entries,previousSession};
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download='BulkProxyForge_Browser_Diagnostics.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
}
window.addEventListener('error',event=>recordDiagnostic('browser error',event.error?.stack||event.message));
window.addEventListener('unhandledrejection',event=>recordDiagnostic('unhandled rejection',event.reason?.stack||event.reason));