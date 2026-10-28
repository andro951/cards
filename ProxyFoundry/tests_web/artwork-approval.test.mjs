import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {WorkCoordinator} from '../site/work.js';

const source=fs.readFileSync(new URL('../site/tokens.js',import.meta.url),'utf8');
const anchor='const approve=button(`All look good`,async()=>{';
const start=source.indexOf(anchor)+anchor.length;
const handler=source.slice(start,source.indexOf('\n            },true);',start));
const ui=fs.readFileSync(new URL('../site/ui.js',import.meta.url),'utf8');
const api=ui.slice(ui.indexOf('function mutationResources('),ui.indexOf('async function requestApi(')).replace('export async function api','async function api');

function fixture({fail=false,save=async()=>({github:'https://github.com/owner/cards/blob/main/data.json'})}={}){
    const work=new WorkCoordinator(),calls=[],notifications=[];
    const deck={id:'11111111-1111-4111-8111-111111111111',revision:2,settings:{dataJsonSource:{kind:'github',value:'https://github.com/owner/cards/tree/main'}},cards:[]};
    const context=vm.createContext({work,deck,approving:false,approve:{style:{},setAttribute(){},removeAttribute(){}},
        reviewRevision:1,reviewFaces:[{faceId:'face',renderKey:'render'}],confirmAction:async()=>true,
        snapshot:()=>null,offerDataSave:save,toast:message=>notifications.push(message),draw(){},
        onChanged:async value=>calls.push(['changed',value.id]),
        requestApi:async(path,data)=>{
            calls.push([path,data]);
            if(path.endsWith('/save')&&fail)throw new Error('Save failed');
            return path.endsWith('/accept-art')?{deck,changes:[{name:'Card'}]}:deck;
        }});
    vm.runInContext(api,context);
    return {work,calls,notifications,run:vm.runInContext('(async()=>{'+handler+'})',context)};
}

test('bulk approval reconnects its GitHub data file under the existing task owner',async()=>{
    const f=fixture();await f.run();
    const save=f.calls.find(([path])=>path.endsWith('/save'));
    assert.equal(save[1].settings.dataJsonSource.value,'https://github.com/owner/cards/blob/main/data.json');
    assert.equal(f.calls.at(-1)[0],'changed');
    assert.match(f.notifications.at(-1),/accepted for printing/);
    assert.equal(f.work.busy,false);
});

test('bulk approval keeps other deck mutations blocked until saving finishes',async()=>{
    let release,entered;
    const waiting=new Promise(resolve=>entered=resolve);
    const held=new Promise(resolve=>release=resolve);
    const f=fixture({save:async()=>{entered();return held;}});
    const pending=f.run();await waiting;
    assert.throws(()=>f.work.begin({resources:['deck:11111111-1111-4111-8111-111111111111']}),/Save artwork approvals/);
    release({github:'https://github.com/owner/cards/blob/main/data.json'});await pending;
    assert.equal(f.work.busy,false);
});

test('a failed connection save releases the approval task',async()=>{
    const f=fixture({fail:true});
    await assert.rejects(f.run(),/Save failed/);
    assert.equal(f.work.busy,false);
    assert.equal(f.work.resources.size,0);
});
