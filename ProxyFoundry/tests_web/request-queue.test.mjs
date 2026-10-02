import test from 'node:test';
import assert from 'node:assert/strict';
import {RequestQueue,requestPriority} from '../web/request-queue.js';

test('foreground requests overtake pending assets without overlapping the active operation',async()=>{
    const queue=new RequestQueue(),order=[];
    let release,started;
    const entered=new Promise(resolve=>started=resolve);
    const active=queue.enqueue(async()=>{
        order.push('active');started();
        await new Promise(resolve=>release=resolve);
        order.push('released');
    },2);
    await entered;
    const background=queue.enqueue(()=>order.push('asset'),2);
    const foreground=queue.enqueue(()=>order.push('foreground'),0);
    assert.deepEqual(order,['active']);
    release();await Promise.all([active,background,foreground]);
    assert.deepEqual(order,['active','released','foreground','asset']);
});

test('equal priorities retain arrival order and rejected operations release the queue',async()=>{
    const queue=new RequestQueue(),order=[];
    const first=queue.enqueue(()=>{order.push(1);throw new Error('fixture');});
    const failed=assert.rejects(first,/fixture/);
    const second=queue.enqueue(()=>order.push(2));
    const third=queue.enqueue(()=>order.push(3));
    await Promise.all([failed,second,third]);assert.deepEqual(order,[1,2,3]);
});

test('a task turn admits new foreground requests before the next background operation',async()=>{
    const queue=new RequestQueue(),order=[];
    let foreground;
    const first=queue.enqueue(()=>{
        order.push('first');
        setTimeout(()=>foreground=queue.enqueue(()=>order.push('foreground')),0);
    },2);
    const second=queue.enqueue(()=>order.push('second'),2);
    await Promise.all([first,second]);await foreground;
    assert.deepEqual(order,['first','foreground','second']);
});

test('UI mutations and cancellation outrank native reads, previews and diagnostics',()=>{
    for(const url of ['/api/templates','/api/decks','/api/jobs/abc/cancel','/api/decks/abc/setup']){
        assert.equal(requestPriority({url}),0);
    }

    assert.equal(requestPriority({url:'/api/assets/abc/thumb'}),1);
    for(const url of ['/img/frame.png','/runtime/native.js','/js/frames/version.js','/api/render-sessions/abc']){
        assert.equal(requestPriority({url}),2);
    }

    assert.equal(requestPriority({url:'/api/render-diagnostic'}),3);
    assert.equal(requestPriority({url:'/api/client-error'}),3);
    assert.equal(requestPriority({url:null}),0);
});

test('queued job chunks acquire foreground priority when an import arrives',async()=>{
    const queue=new RequestQueue(),order=[];
    let foreground=false,release,started;
    const entered=new Promise(resolve=>started=resolve);
    const active=queue.enqueue(async()=>{started();await new Promise(resolve=>release=resolve);},2);
    await entered;
    const asset=queue.enqueue(()=>order.push('asset'),2);
    const job=queue.enqueue(()=>order.push('job'),()=>foreground?0:2);
    foreground=true;release();await Promise.all([active,asset,job]);
    assert.deepEqual(order,['job','asset']);
});