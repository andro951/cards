const database='bulk-proxy-forge-browser';

function openPreferences(){
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(database,1);
    request.onupgradeneeded=()=>request.result.createObjectStore('preferences');
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
  });
}

async function preference(key,value){
  const db=await openPreferences();
  return new Promise((resolve,reject)=>{
    const transaction=db.transaction('preferences',value===undefined?'readonly':'readwrite');
    const request=value===undefined?transaction.objectStore('preferences').get(key):transaction.objectStore('preferences').put(value,key);
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
    transaction.oncomplete=()=>db.close();
  });
}

export async function savedFolder(){
  const folder=await preference('workspaceFolder');
  return folder||null;
}

export async function chooseFolder(){
  if(!window.showDirectoryPicker)throw new Error('This browser does not support direct folder access. Your browser workspace remains available.');
  const parent=await window.showDirectoryPicker({id:'bulk-proxy-forge',mode:'readwrite',startIn:'documents'});
  const folder=await parent.getDirectoryHandle('BulkProxyForge',{create:true});
  return folder;
}

export async function useFolder(folder){await preference('workspaceFolder',folder);}
export async function useBrowserStorage(){await preference('workspaceFolder',null);}

export async function containsWorkspace(folder){
  for await(const _ of folder.entries())return true;
  return false;
}

export async function copyWorkspace(source,target){
  for await(const [name,entry] of source.entries()){
    if(entry.kind==='directory'){
      const child=await target.getDirectoryHandle(name,{create:true});
      await copyWorkspace(entry,child);
    }
    else{
      const file=await entry.getFile();
      const destination=await target.getFileHandle(name,{create:true});
      const stream=await destination.createWritable();
      await file.stream().pipeTo(stream);
    }
  }
}
