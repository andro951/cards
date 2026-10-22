import test from 'node:test';
import assert from 'node:assert/strict';
import {createBatchReviewFlow} from '../site/batch-review-flow.js';
import {WorkCoordinator} from '../site/work.js';

function fixture(overrides={}) {
    const events=[];
    const dependencies={
        getCandidates:async()=>({decks:[{id:`a`},{id:`b`}],skipped:[{name:`Manual`,reason:`Needs attention`}]}),
        start:async ids=>{events.push([`start`,ids]);return {id:`session`};},
        render:async ids=>{events.push([`render`,ids]);return {};},
        exportAndStage:async(session,deck)=>{events.push([`stage`,session,deck.id]);return {filename:`${deck.id}.zip`};},
        commit:async session=>{events.push([`commit`,session]);return {checked:true};},
        abort:async session=>events.push([`abort`,session]),
        ...overrides
    };
    return {flow:createBatchReviewFlow(dependencies),events};
}

test(`generation and all exports finish before a single comparison`,async()=>{
    const {flow,events}=fixture();
    const result=await flow.run();
    assert.deepEqual(events,[[`start`,[`a`,`b`]],[`render`,[`a`,`b`]],[`stage`,`session`,`a`],[`stage`,`session`,`b`],[`commit`,`session`]]);
    assert.equal(result.result.checked,true);
    assert.equal(result.skipped[0].name,`Manual`);
    assert.equal(flow.busy,false);
});

test(`generation failure and cancellation never export or compare`,async()=>{
    for(const value of [false,new Error(`render failed`)]) {
        const {flow,events}=fixture({render:async()=>{
            if(value instanceof Error)
                throw value;
            return value;
        }});
        await assert.rejects(flow.run());
        assert.deepEqual(events,[[`start`,[`a`,`b`]],[`abort`,`session`]]);
        assert.equal(flow.busy,false);
    }
});

test(`export or comparison failure aborts the session`,async()=>{
    for(const phase of [`exportAndStage`,`commit`]) {
        const {flow,events}=fixture({[phase]:async()=>{throw new Error(`failed`);}});
        await assert.rejects(flow.run(),/failed/);
        assert.deepEqual(events.at(-1),[`abort`,`session`]);
    }
});

test(`concurrent clicks are rejected throughout the workflow`,async()=>{
    let release;
    const held=new Promise(resolve=>release=resolve);
    const {flow}=fixture({commit:async()=>held});
    const first=flow.run();
    await assert.rejects(flow.run(),/already running/);
    assert.equal(flow.busy,true);
    release({checked:true});await first;
    assert.equal(flow.busy,false);
});

test(`no eligible decks creates no session and preserves skipped details`,async()=>{
    const {flow,events}=fixture({getCandidates:async()=>({decks:[],skipped:[{name:`Blocked`} ]})});
    assert.deepEqual(await flow.run(),{decks:[],skipped:[{name:`Blocked`}],result:null});
    assert.deepEqual(events,[]);
});

test(`batch can claim workspace after generation and release it once`,async()=>{
    const work=new WorkCoordinator();
    const batch=work.begin({label:`Batch review`,resources:[`batch-review`]});
    const render=work.begin({resources:[`deck:a`]});
    assert.throws(()=>work.claim(batch,[`workspace`]),/still/);
    work.finish(render);work.claim(batch,[`workspace`]);
    work.requireAvailable([`deck:a`],batch);
    assert.throws(()=>work.begin({resources:[`deck:b`]}),/workspace/);
    work.finish(batch);work.finish(batch);
    assert.equal(work.busy,false);assert.equal(work.resources.size,0);
});