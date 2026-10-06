"""Concurrency, storage ordering and cancellation at the production pool boundary."""
import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('scenario',['complete','cancel','storage-failure','renderer-failure','startup-failure'])
def test_native_render_pool_bounds_work_and_preserves_completed_saves(scenario):
    node=shutil.which('node')
    assert node,'Node is required for JavaScript regression tests.'
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'site/native-render-pool.js').read_bytes()).decode()
    code='''
        import assert from 'node:assert/strict';
        const {NativeRenderPool}=await import(MODULE);
        const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
        const controller=new AbortController();
        let rendering=0,maxRendering=0,writing=0,maxWriting=0,completed=0,loads=0,closed=0;
        const renderers=[];
        const createRenderer=()=>{
            const renderer={closed:false,ready:SCENARIO==='startup-failure'?Promise.reject(new Error('startup')):Promise.resolve(),
                async render(target){
                    rendering++;maxRendering=Math.max(maxRendering,rendering);await wait(5);rendering--;
                    if(SCENARIO==='renderer-failure'&&target.index===1)throw new Error('renderer');
                    if(this.closed)throw new Error('closed');return {blob:new Blob([target.key]),width:5,height:7};
                },close(){if(!this.closed){this.closed=true;closed++;}}
            };renderer.ready.catch(()=>{});renderers.push(renderer);return renderer;
        };
        const pool=new NativeRenderPool({count:2,createRenderer,signal:controller.signal});
        const targets=Array.from({length:12},(_,index)=>({key:String(index),name:String(index)}));
        const commits=[];
        let failure=null;
        try{
            await pool.run(targets,{
                load:async target=>{loads++;return target;},
                save:async target=>{
                    writing++;maxWriting=Math.max(maxWriting,writing);
                    if(SCENARIO==='cancel')controller.abort();
                    await wait(20);writing--;
                    if(SCENARIO==='storage-failure')throw new Error('storage');
                    completed++;commits.push(target.key);
                }
            });
        }catch(error){failure=error.message;}
        assert.equal(maxWriting,SCENARIO==='startup-failure'?0:1);
        assert.equal(closed,2);assert.equal(rendering,0);assert.equal(writing,0);
        assert.equal(pool.saved,completed);assert.equal(new Set(commits).size,commits.length);
        if(SCENARIO==='complete'){
            assert.equal(failure,null);assert.equal(completed,12);assert.equal(maxRendering,2);
        }else{
            assert.ok(failure);assert.ok(loads<=2);assert.ok(completed<=1);
            if(SCENARIO==='cancel')assert.equal(completed,1,'An accepted save must finish before the operation returns.');
            if(SCENARIO==='storage-failure'||SCENARIO==='startup-failure')assert.equal(completed,0);
        }
        console.log(JSON.stringify({scenario:SCENARIO,completed,maxRendering,maxWriting,closed}));
    '''.replace('MODULE',json.dumps(module)).replace('SCENARIO',json.dumps(scenario))
    result=subprocess.run([node,'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
