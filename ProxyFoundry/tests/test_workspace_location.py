"""A saved folder choice is durable before reload, and survives a missing handle as a reconnect hint."""
import json,shutil,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

def test_location_commit_abort_and_missing_handle_do_not_silently_switch_workspaces(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js')
    (tmp_path/'storage.mjs').write_text((ROOT/'web/storage-choice.js').read_text(encoding='utf-8'),encoding='utf-8')
    script=r'''
import assert from 'node:assert/strict';
const values=new Map();globalThis.localStorage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
let stored,current;
globalThis.indexedDB={open:()=>{
    const open={};queueMicrotask(()=>{open.result={close:()=>{},transaction:()=>{
        const tx={objectStore:()=>({get:()=>request(false),put:value=>request(true,value)})};
        function request(write,value){const req={result:write?'workspaceFolder':stored};
            tx.finish=()=>{if(write)stored=value;tx.oncomplete();};
            tx.abort=()=>{tx.error=new Error('Injected disk-full transaction abort');tx.onabort();};
            queueMicrotask(()=>req.onsuccess());return req;}
        current=tx;return tx;}};open.onsuccess();});return open;}};
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const {useFolder,useBrowserStorage,savedFolder,rememberedLocation,chooseFolder}=await import('./storage.mjs');
let completed=false;
const save=useFolder({name:'Saved workspace'}).then(()=>completed=true);
await turn();assert.equal(completed,false);assert.equal(rememberedLocation(),null);
current.finish();await save;assert.equal(rememberedLocation().kind,'folder');
const fail=useBrowserStorage();await turn();current.abort();await assert.rejects(fail,/disk-full/);
assert.equal(rememberedLocation().kind,'folder');assert.equal(stored.name,'Saved workspace');
stored=undefined;const lost=savedFolder();await turn();current.finish();assert.equal(await lost,null);
assert.equal(rememberedLocation().name,'Saved workspace');
let created=false;
globalThis.window={showDirectoryPicker:async()=>({name:'Empty',getFileHandle:async()=>{throw {name:'NotFoundError'};},getDirectoryHandle:async(name,options)=>{created=Boolean(options?.create);throw {name:'NotFoundError'};}})};
await assert.rejects(chooseFolder({existingOnly:true}),/existing folder/);assert.equal(created,false);
const browser=useBrowserStorage();await turn();current.finish();await browser;assert.equal(rememberedLocation().kind,'browser');
console.log(JSON.stringify({committed:true,abortPreservedFolder:true,reconnectHint:true,noEmptyFolderCreated:true,explicitBrowserChoice:true}));
'''
    (tmp_path/'test.mjs').write_text(script,encoding='utf-8')
    result=subprocess.run([node,'test.mjs'],cwd=tmp_path,capture_output=True,text=True,check=True,timeout=20)
    assert all(json.loads(result.stdout).values())
