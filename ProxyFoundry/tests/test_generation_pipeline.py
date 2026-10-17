"""Streaming work, bounded save overlap and deferred preview scheduling."""
import base64,json,shutil,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

def node(code):
 result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr

def module(path):
 return json.dumps('data:text/javascript;base64,'+base64.b64encode((ROOT/path).read_bytes()).decode())

@pytest.mark.parametrize('scenario',['complete','cancel','save-failure'])
def test_streaming_pool_overlaps_saves_and_drains_on_failure(scenario):
 code=r'''import assert from 'node:assert/strict';
 const {NativeRenderPool}=await import(MODULE);
 const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const controller=new AbortController();let drawing=0,writing=0,overlap=false,finished=0,closed=0,remaining=14,serial=0;
 const pool=new NativeRenderPool({count:3,concurrentSaves:true,signal:controller.signal,createRenderer:()=>({
  closed:false,ready:Promise.resolve(),async render(target){drawing++;if(writing)overlap=true;await delay(4);drawing--;return {blob:new Blob([target.key])};},close(){if(!this.closed){this.closed=true;closed++;}}
 })});
 const targets=[{key:'first'}],committed=[];let error;
 try{await pool.run(targets,{pipeline:true,
  moreTargets:async()=>{await delay(2);const count=Math.min(4,remaining);remaining-=count;return {targets:Array.from({length:count},()=>({key:String(serial++)})),complete:remaining===0};},
  load:async target=>target,
  save:async target=>{writing++;await delay(18);writing--;if(SCENARIO==='save-failure')throw new Error('injected save');committed.push(target.key);finished++;if(SCENARIO==='cancel')controller.abort();}
 });}catch(failure){error=failure;}
 assert.equal(writing,0);assert.equal(drawing,0);assert.equal(pool.saved,finished);assert.equal(closed,3);assert.equal(new Set(committed).size,committed.length);
 if(SCENARIO==='complete'){assert.equal(error,undefined);assert.equal(finished,15);assert.ok(overlap);}
 else{assert.ok(error);assert.ok(finished<15);}
 '''.replace('MODULE',module('site/native-render-pool.js')).replace('SCENARIO',json.dumps(scenario))
 node(code)

def test_deferred_thumbnails_do_not_block_render_requests():
 node(r'''import assert from 'node:assert/strict';
 const {RequestQueue}=await import(MODULE);const queue=new RequestQueue();let generating=true;const seen=[];
 const preview=queue.enqueue(()=>seen.push('preview'),()=>generating?Infinity:1);
 await queue.enqueue(()=>seen.push('render'),2);assert.deepEqual(seen,['render']);
 await queue.enqueue(()=>{generating=false;},0);await preview;assert.deepEqual(seen,['render','preview']);
 '''.replace('MODULE',module('web/request-queue.js')))


def test_svg_frames_bypass_composition_cache_and_text_frames_stay_live():
 node(r'''import assert from 'node:assert/strict';
 const {FrameCompositionCache}=await import(MODULE);const cache=new FrameCompositionCache();
 const runtime={drawTextBetweenFrames:false,frameCanvas:{width:2010,height:2814},card:{version:'planeswalker',frames:[{src:'blob:one',image:{blob:{type:'image/svg+xml'}}}]}};
 assert.equal(cache.key(runtime),null);
 runtime.card.frames[0].image.blob.type='image/png';assert.ok(cache.key(runtime));
 runtime.drawTextBetweenFrames=true;assert.equal(cache.key(runtime),null);
 '''.replace('MODULE',module('site/frame-composition-cache.js')))


def test_failed_save_interrupts_wait_for_future_prepared_faces():
 node(r'''import assert from 'node:assert/strict';
 const {NativeRenderPool}=await import(MODULE);
 const pool=new NativeRenderPool({count:1,concurrentSaves:true,createRenderer:()=>({ready:Promise.resolve(),render:async()=>({blob:new Blob(['png'])}),close(){}})});
 let cancelled=false;
 const completed=pool.run([{key:'one'}],{pipeline:true,load:async()=>({}),save:async()=>{throw new Error('disk full');},
  moreTargets:signal=>new Promise((resolve,reject)=>{signal.addEventListener('abort',()=>{cancelled=true;reject(signal.reason);},{once:true});})});
 await assert.rejects(()=>Promise.race([completed,new Promise((resolve,reject)=>setTimeout(()=>reject(new Error('hung waiting for preparation')),1000))]),/disk full/);
 assert.equal(cancelled,true);
 '''.replace('MODULE',module('site/native-render-pool.js')))
