import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {BrowserRenderSave} from '../web/render-save.js';
Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});

function folder({stage='close',failures=1,error='InvalidStateError'}={}) {
    const files=new Map();let handles=0,writes=0,aborts=0;
    const fail=where=>{if(stage===where&&failures-->0)throw new DOMException('State changed since read from disk',error);};
    const directory={async getFileHandle(name){
        handles++;fail('handle');
        return {async getFile(){fail('read');return files.get(name)||new Blob([]);},async createWritable(){
            writes++;fail('open');const chunks=[];
            return new WritableStream({write(value){fail('write');chunks.push(value);},close(){fail('close');files.set(name,new Blob(chunks));},abort(){aborts++;}});
        }};
    }};
    return {directory,files,counts:()=>({handles,writes,aborts})};
}

test('transient stale-state failures reacquire handles and publish the original bytes',async()=>{
    for(const stage of ['handle','open','write','close']) {
        const f=folder({stage});const saver=new BrowserRenderSave(null,null);
        await saver.write(f.directory,'receipt.json','complete receipt');
        assert.equal(await f.files.get('receipt.json').text(),'complete receipt');
        assert.equal(f.counts().handles,2);
    }
});

test('persistent stale-state errors stop after three attempts without a published receipt',async()=>{
    const f=folder({failures:10});const saver=new BrowserRenderSave(null,null);
    await assert.rejects(saver.write(f.directory,'receipt.json','data'),/receipt.json: InvalidStateError/);
    assert.equal(f.counts().handles,3);assert.equal(f.files.size,0);
});

test('quota and permission failures are surfaced immediately',async()=>{
    for(const error of ['QuotaExceededError','NotAllowedError']) {
        const f=folder({stage:'open',error});const saver=new BrowserRenderSave(null,null);
        await assert.rejects(saver.write(f.directory,'receipt.json','data'),new RegExp(error));
        assert.equal(f.counts().handles,1);assert.equal(f.files.size,0);
    }
});

test('existing hashed assets stay untouched; corrupt same-size bytes are replaced',async()=>{
    const data=new Blob(['valid image bytes']);
    const hash=Buffer.from(await webcrypto.subtle.digest('SHA-256',await data.arrayBuffer())).toString('hex');
    const f=folder({failures:0});const saver=new BrowserRenderSave(null,null);
    f.files.set(hash,data);await saver.write(f.directory,hash,data);
    assert.equal(f.counts().writes,0);
    f.files.set(hash,new Blob(['wrong image bytes']));await saver.write(f.directory,hash,data);
    assert.equal(f.counts().writes,1);assert.equal(await f.files.get(hash).text(),await data.text());
});
