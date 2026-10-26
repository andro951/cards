import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {RuntimeDownloads} from '../web/runtime-downloads.js';

const source=fs.readFileSync(new URL('../web/engine-worker.js',import.meta.url),'utf8');
const start=source.slice(source.indexOf('async function start(folder){'),source.indexOf('//The marker avoids'));

function fixture(failure='',folder=false){
  const messages=[];let now=0;
  const check=stage=>{if(failure===stage)throw new Error('Fixture '+stage);};
  const directory={async *entries(){}};
  const python={FS:{mkdirTree(){},readFile(){return new TextEncoder().encode(JSON.stringify({id:failure==='bundle-version'?'older':'fixture'}));}},
    async loadPackage(){check('pillow');},unpackArchive(){check('bundle-unpack');},runPython(){check('python-app-init');}};
  const context=vm.createContext({
    performance:{now:()=>now+=120},TextDecoder,Uint8Array,RuntimeDownloads,
    navigator:{storage:{getDirectory:async()=>directory}},
    loadPyodide:async()=>{check('pyodide');return python;},
    mountWorkspaceFiles:()=>({}),
    fetch:async(url,options)=>{assert.equal(url,'/web/runtime.zip?v=fixture');assert.equal(options.cache,'no-store');check('bundle-fetch');return {ok:true,arrayBuffer:async()=>new ArrayBuffer(0)};},
    self:{postMessage:data=>messages.push(data)},
  });
  vm.runInContext("let python,mount,workspaceMount;let initialized=false;const owner='test',buildId='fixture';"+start,context);
  const result=vm.runInContext('start',context)(folder?directory:null);
  return {result,messages};
}

for(const folder of [false,true])test('startup timers identify '+(folder?'selected folder':'browser')+' storage',async()=>{
  const {result,messages}=fixture('',folder);await result;
  const rows=messages.filter(data=>data.type==='startup-timing');
  assert.deepEqual(rows.map(row=>row.stage),['pyodide','pillow','workspace-open','bundle-fetch','bundle-unpack','python-app-init','engine-total']);
  assert.ok(rows.every(row=>row.seconds>=.1&&row.storageType===(folder?'selected-folder':'browser')));
  assert.equal(rows.at(-1).outcome,'ok');assert.equal(rows.at(-1).lastStage,'ready');
  assert.equal(messages.filter(data=>data.type==='ready').length,1);
});

for(const stage of ['pyodide','pillow','bundle-fetch','bundle-unpack','python-app-init'])test('startup failure records last stage '+stage,async()=>{
  const {result,messages}=fixture(stage);await assert.rejects(result,/Fixture/);
  const total=messages.filter(data=>data.type==='startup-timing').at(-1);
  assert.equal(total.stage,'engine-total');assert.equal(total.outcome,'failed');assert.equal(total.lastStage,stage);
  assert.equal(messages.filter(data=>data.type==='ready').length,0);
});

test('bundle mismatch is identifiable before Python workspace tools start',async()=>{
  const {result,messages}=fixture('bundle-version');
  await assert.rejects(result,error=>error.code==='BUILD_MISMATCH'&&/Engine fixture, bundle older/.test(error.message));
  assert.equal(messages.filter(data=>data.type==='ready').length,0);
});

test('update reload bypasses stale HTML and stops automatic reload loops',()=>{
  const source=fs.readFileSync(new URL('../web/bootstrap.js',import.meta.url),'utf8');
  const start=source.indexOf('function reloadUpdatedPage(');
  const helper=source.slice(start,source.indexOf('\ntry{',start));
  const values=new Map(),navigations=[];let now=100000;
  const context=vm.createContext({URL,Date:{now:()=>now},
    sessionStorage:{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)},
    location:{href:'https://forge.test/cards/?keep=1#deck/test',replace:url=>navigations.push(url)}});
  vm.runInContext(helper,context);
  const reload=vm.runInContext('reloadUpdatedPage',context);
  assert.equal(reload(true),true);
  assert.equal(navigations[0],'https://forge.test/cards/?keep=1&_pf_update=100000#deck/test');
  now+=1000;assert.equal(reload(true),false);assert.equal(navigations.length,1);
  assert.equal(reload(),true);assert.equal(navigations.length,2);
  now+=60000;assert.equal(reload(true),true);
});