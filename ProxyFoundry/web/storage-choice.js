const database='bulk-proxy-forge-browser';
const locationKey='bulk-proxy-forge-workspace-location';

export function rememberedLocation(){
  try{return JSON.parse(localStorage.getItem(locationKey)||'null');}
  catch{return null;}
}
function rememberLocation(kind,name=''){
  try{localStorage.setItem(locationKey,JSON.stringify({kind,name}));}
  catch{} //Folder handles still persist in IndexedDB when localStorage is unavailable.
}

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
    let result;
    const transaction=db.transaction('preferences',value===undefined?'readonly':'readwrite');
    const request=value===undefined?transaction.objectStore('preferences').get(key):transaction.objectStore('preferences').put(value,key);
    request.onsuccess=()=>{result=request.result;};
    transaction.oncomplete=()=>{db.close();resolve(result);};
    transaction.onerror=transaction.onabort=()=>{db.close();reject(transaction.error||request.error||new Error('The workspace location could not be saved.'));};
  });
}

export async function savedFolder(){
  const folder=await preference('workspaceFolder');
  if(folder)rememberLocation('folder',folder.name);
  return folder||null;
}

export async function chooseFolder({existingOnly=false}={}){
  if(!window.showDirectoryPicker)throw new Error('This browser does not support direct folder access. Your browser workspace remains available.');
  const parent=await window.showDirectoryPicker({id:'bulk-proxy-forge',mode:'readwrite',startIn:'documents'});
  if(existingOnly){
    try{await parent.getFileHandle('workspace.sqlite3');return parent;}
    catch(error){if(error.name!=='NotFoundError')throw error;}
    try{
      const child=await parent.getDirectoryHandle('BulkProxyForge');
      await child.getFileHandle('workspace.sqlite3');return child;
    }catch(error){if(error.name!=='NotFoundError')throw error;}
    throw new Error('Choose the existing folder containing workspace.sqlite3 to reopen your saved decks.');
  }
  //Selecting the workspace itself must reopen it, not create a nested empty one.
  if(parent.name.toLowerCase()==='bulkproxyforge')return parent;
  try{
    await parent.getFileHandle('workspace.sqlite3');
    return parent;
  }
  catch(error){if(error.name!=='NotFoundError')throw error;}
  const folder=await parent.getDirectoryHandle('BulkProxyForge',{create:true});
  return folder;
}

export async function useFolder(folder){await preference('workspaceFolder',folder);rememberLocation('folder',folder.name);}
export async function useBrowserStorage(){await preference('workspaceFolder',null);rememberLocation('browser');}

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
