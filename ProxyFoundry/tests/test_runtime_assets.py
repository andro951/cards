"""Renderer asset lifetime, failure and memory bounds with real JS promises."""
import base64
import json
import shutil
import subprocess
from pathlib import Path


def test_runtime_asset_cache_lifetime_and_cancellation():
    root=Path(__file__).resolve().parents[1]
    node=shutil.which('node') or 'D:/nvm4w/nodejs/node.exe'
    script='''
import assert from 'node:assert/strict';
const {RuntimeAssets}=await import(process.argv[1]);
let calls=0,serial=0;
const revoked=[];
const urls={createObjectURL:()=>`blob:${++serial}`,revokeObjectURL:url=>revoked.push(url)};
const cache=new RuntimeAssets({limit:8,urls,fetchAsset:async()=>{calls++;return {ok:true,blob:async()=>new Blob([`12345678`])};}});
const first={artSource:`/api/assets/${`a`.repeat(64)}`,frames:[{src:`/img/frame.png`,masks:[{src:`/img/frame.png`}]}],watermarkSource:`data:image/png;base64,AA==`};
await cache.acquire(first);
assert.equal(calls,2);assert.equal(first.frames[0].src,first.frames[0].masks[0].src);
assert.equal(first.watermarkSource,`data:image/png;base64,AA==`);
assert.equal(cache.bytes,16);assert.equal(revoked.length,0);
cache.release();assert.equal(cache.bytes,8);assert.equal(revoked.length,1);
const second={frames:[{src:`/img/frame.png`}]};await cache.acquire(second);
assert.equal(calls,2);cache.release();cache.dispose();
assert.equal(cache.bytes,0);assert.equal(revoked.length,2);
await assert.rejects(cache.get(`/img/frame.png`),/closed/);
assert.equal(cache.accepts(`//example.org/img/a.png`),false);
assert.equal(cache.accepts(`/img/../a.png`),false);
assert.equal(cache.accepts(`/img/a.png?version=1`),false);
assert.equal(cache.accepts(`/api/assets/not-a-hash`),false);
let finish;
const pending=new RuntimeAssets({urls,fetchAsset:async()=>{await new Promise(resolve=>finish=resolve);return {ok:true,blob:async()=>new Blob([`late`])};}});
const one=pending.get(`/img/late.png`),two=pending.get(`/img/late.png`);
pending.dispose();finish();
await assert.rejects(one,/cancelled/);await assert.rejects(two,/cancelled/);
assert.equal(pending.bytes,0);assert.equal(serial,2);
let attempts=0;
const retry=new RuntimeAssets({urls,fetchAsset:async()=>({ok:++attempts>1,status:503,blob:async()=>new Blob([`retry`])})});
await assert.rejects(retry.get(`/img/retry.png`),/503/);
await retry.get(`/img/retry.png`);assert.equal(attempts,2);retry.dispose();
console.log(JSON.stringify({passed:true}));
'''
    module='data:text/javascript;base64,'+base64.b64encode((root/'site/runtime-assets.js').read_bytes()).decode()
    result=subprocess.run([node,'--input-type=module','-e',script,module],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['passed']
