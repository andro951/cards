import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../web/engine-worker.js',import.meta.url),'utf8');
const start=source.slice(source.indexOf('async function start(folder){'),source.indexOf('//The marker avoids'));

function fixture(failure='',folder=false){
  const messages=[];let now=0;
  const check=stage=>{if(failure===stage)throw new Error('Fixture '+stage);};
  const directory={async *entries(){}};
  const python={FS:{mkdirTree(){},readFile(){return new TextEncoder().encode('{"id":"fixture"}');}},
    async loadPackage(){check('pillow');},unpackArchive(){check('bundle-unpack');},runPython(){check('python-app-init');}};
  const context=vm.createContext({
    performance:{now:()=>now+=120},TextDecoder,Uint8Array,
    navigator:{storage:{getDirectory:async()=>directory}},
    loadPyodide:async()=>{check('pyodide');return python;},
    mountWorkspaceFiles:()=>({}),
    fetch:async()=>{check('bundle-fetch');return {ok:true,arrayBuffer:async()=>new ArrayBuffer(0)};},
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