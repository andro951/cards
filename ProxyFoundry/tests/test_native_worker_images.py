"""Worker bitmap sharing, late loads and live-image eviction safeguards."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_native_worker_image_leases_and_stale_loads():
    node=shutil.which('node');assert node
    code='''
        import assert from 'node:assert/strict';
        import vm from 'node:vm';
        import fs from 'node:fs';
        const gates=new Map();let fetched=0,closed=0;
        class Context {drawImage(){}}
        class Canvas {constructor(width,height){this.width=width;this.height=height;}}
        const worker={EventTarget,Event,URL,URLSearchParams,Map,Set,Promise,OffscreenCanvas:Canvas,
            OffscreenCanvasRenderingContext2D:Context,location:{origin:'http://test.local',search:''},
            fetch:async url=>{fetched++;return await new Promise(resolve=>gates.set(url,resolve));},
            createImageBitmap:async()=>({width:5000,height:5000,close(){closed++;}}),
            addEventListener(){},postMessage(){},__PF_RUNTIME:{errors:[],phase:'assets'}};
        worker.self=worker;
        vm.runInNewContext(fs.readFileSync(SOURCE,'utf8'),worker);
        const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
        const a=new worker.Image(),b=new worker.Image();
        a.src='/img/shared.png';b.src='/img/shared.png';assert.equal(fetched,1);
        a.src='/img/frameThumb.png';
        gates.get('http://test.local/img/shared.png?owner=')({ok:true,blob:async()=>({type:'image/png'})});
        await tick();assert.equal(a.naturalWidth,0,'A stale load must not replace a thumbnail assignment.');
        assert.equal(b.naturalWidth,5000);
        worker.__PF_RELEASE_IMAGES();assert.equal(closed,0,'Live frame bitmaps must remain pinned.');
        b.dispose();worker.__PF_RELEASE_IMAGES();assert.equal(closed,1);
        const c=new worker.Image();c.src='/img/shared.png';assert.equal(fetched,2,'Evicted images must reload.');
        gates.get('http://test.local/img/shared.png?owner=')({ok:false,status:404});await tick();
        assert.equal(worker.__PF_RUNTIME.errors.length,1);
        const d=new worker.Image();d.src='/img/shared.png';assert.equal(fetched,3,'A failed cache entry must be retryable.');
    '''.replace('SOURCE',json.dumps(str(ROOT/'site/native-render-worker.js')))
    result=subprocess.run([node,'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
