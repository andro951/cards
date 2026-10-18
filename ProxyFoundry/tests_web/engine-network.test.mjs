import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../web/engine-worker.js',import.meta.url),'utf8');
const transport=source.slice(source.indexOf('  self.syncFetch=url=>{'),source.indexOf('  self.syncGithubBatch='));

test('GitHub reads see a newly created data.json immediately after saving',()=>{
    const cached=new Map(),requests=[];
    let head='old',sequence=0;
    class XMLHttpRequest {
        open(method,url){this.url=url;requests.push(url);}
        setRequestHeader(){}
        getResponseHeader(){return 'application/json';}
        send(){
            if(!cached.has(this.url)) {
                const url=new URL(this.url);
                cached.set(this.url,url.hostname==='api.github.com'?JSON.stringify({sha:head}):url.hostname==='forge.test'?'{}':url.pathname.includes('/new/')?'{"version":1,"cards":[]}':null);
            }

            const body=cached.get(this.url);
            this.status=body?200:404;
            this.response=new TextEncoder().encode(body||'').buffer;
        }
    }

    const self={location:{origin:'https://forge.test'}};
    vm.runInNewContext(transport,{self,XMLHttpRequest,URL,Uint8Array,crypto:{randomUUID:()=>String(++sequence)}});
    const read=url=>JSON.parse(new TextDecoder().decode(self.syncFetch(url).bytes));
    const branch='https://api.github.com/repos/owner/cards/commits/main';
    assert.equal(read(branch).sha,'old');
    head='new';
    const commit=read(branch).sha;
    assert.equal(commit,'new');
    assert.deepEqual(read(`https://raw.githubusercontent.com/owner/cards/${commit}/deck/data.json`),{version:1,cards:[]});
    assert.notEqual(requests[0],requests[1]);
    assert.equal(requests[2],'https://raw.githubusercontent.com/owner/cards/new/deck/data.json');
    self.syncFetch('/api/jobs/test/control?owner=one');
    assert.equal(requests.at(-1),'https://forge.test/api/jobs/test/control?owner=one');
    assert.throws(()=>self.syncFetch('https://raw.githubusercontent.com/owner/cards/missing/deck/data.json'),/HTTP 404/);
});