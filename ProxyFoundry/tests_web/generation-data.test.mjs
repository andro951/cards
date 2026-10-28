import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {WorkCoordinator} from '../site/work.js';

const source=fs.readFileSync(new URL('../site/render.js',import.meta.url),'utf8');
const flow=source.slice(source.indexOf('export async function renderDecks('),source.indexOf('export async function renderCard(')).replace('export async','async');
const single=source.slice(source.indexOf('export async function renderCard('),source.indexOf('export async function renderTemplatePreviews(')).replace('export async','async');

function fixture({github=true,errors=[],save=async()=>{},prepareFailure=false,browser=true}={}){
    const events=[],work=new WorkCoordinator();
    const screen={estimate:{started:0,phase:'prepare'},attach(){},update(){},cancel:{},review:operation=>operation()};
    const context=vm.createContext({work,performance,state:{bootstrap:{browser},decks:[],route:'decks'},
        withGenerationScreen:(name,cards,operation)=>operation(screen),measure:(label,operation)=>operation(),
        ensureArtworkReady:async()=>true,generationNeedsDataSave:async()=>github,
        saveGenerationData:async(ids,options)=>{events.push('save');await save(ids,options);},
        recordDiagnostic(){},endActivity(){},
        job:async()=>{events.push('prepare');if(prepareFailure)throw new Error('Missing artwork');},
        api:async path=>{
            if(path==='/api/render-sessions'||path==='/api/render-sessions/card'){events.push('plan');return {id:'plan',targets:[{key:'card'}],errors,cached:0};}
            if(path==='/api/generation/begin'){events.push('begin');return {id:'generation'};}
            if(path==='/api/generation/commit'){events.push('commit');return {};}
            if(path==='/api/generation/abort'){events.push('abort');return {};}
            if(path.startsWith('/api/generation/targets'))return {id:'plan',targets:[{key:'card'}],errors:[],cursor:1,complete:true};
            throw new Error('Unexpected '+path);
        },
        runRenderPlan:async()=>{events.push('render');return {rows:[]};}
    });
    vm.runInContext(flow+'\n'+single,context);
    return {events,work,run:()=>vm.runInContext('renderDecks',context)(['deck']),one:()=>vm.runInContext('renderCard',context)('deck','card')};
}

test('GitHub recipe is saved after readiness checks and before atomic image generation',async()=>{
    const f=fixture();await f.run();
    assert.deepEqual(f.events,['prepare','plan','save','begin','render','commit']);
    assert.equal(f.work.busy,false);
});

test('missing inputs and preparation errors prevent both saving and rendering',async()=>{
    for(const options of [{errors:['Card not ready']},{prepareFailure:true}]){
        const f=fixture(options);await assert.rejects(f.run());
        assert.ok(!f.events.includes('save'));assert.ok(!f.events.includes('render'));assert.ok(!f.events.includes('begin'));
        assert.equal(f.work.busy,false);
    }
});

test('failed GitHub write prevents image generation and releases the deck',async()=>{
    const f=fixture({save:async()=>{throw new Error('GitHub failed');}});
    await assert.rejects(f.run(),/GitHub failed/);
    assert.deepEqual(f.events,['prepare','plan','save']);assert.equal(f.work.busy,false);
});

test('rendering waits for the complete GitHub write to finish',async()=>{
    let release,started;
    const reached=new Promise(resolve=>started=resolve),waiting=new Promise(resolve=>release=resolve);
    const f=fixture({save:async()=>{started();await waiting;}});
    const running=f.run();await reached;
    assert.deepEqual(f.events,['prepare','plan','save']);
    release();await running;assert.ok(f.events.includes('render'));
});

test('single-card generation uses the same save-before-render gate',async()=>{
    const f=fixture();await f.one();assert.deepEqual(f.events,['plan','save','render']);
    const failed=fixture({save:async()=>{throw new Error('Cancelled save');}});
    await assert.rejects(failed.one(),/Cancelled save/);assert.deepEqual(failed.events,['plan','save']);
});

test('decks without GitHub keep their existing preparation/render flow',async()=>{
    const f=fixture({github:false});await f.run();
    assert.ok(!f.events.includes('save'));assert.ok(f.events.includes('render'));assert.ok(f.events.includes('commit'));
});

test('automatic save requires a real GitHub result and keeps task ownership',async()=>{
    const document=fs.readFileSync(new URL('../site/deck-document.js',import.meta.url),'utf8');
    const helper=document.slice(document.indexOf('export async function saveGenerationData(')).replace('export async','async')
        .replace("await import('./artwork-review.js')",'await loadArtworkReview()');
    for(const result of [{downloaded:true},undefined,{github:'https://github.com/owner/cards/blob/main/data.json'}]){
        const work=new WorkCoordinator(),owner=work.begin({resources:['deck:deck']});let options;
        const context=vm.createContext({api:async()=>({id:'deck',settings:{dataJsonSource:{kind:'github',value:'https://github.com/owner/cards/blob/main/data.json'}},cards:[]}),
            loadArtworkReview:async()=>({offerDataSave:async(...args)=>{options=args.at(-1);return result;}})});
        vm.runInContext(helper,context);
        const pending=vm.runInContext('saveGenerationData',context)(['deck'],{owner});
        if(result?.github)await pending;else await assert.rejects(pending,/not saved to GitHub/);
        assert.equal(options.requireGithubSave,true);assert.equal(options.owner,owner);work.finish(owner);
    }
});
