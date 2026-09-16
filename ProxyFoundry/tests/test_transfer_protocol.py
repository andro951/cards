"""Run actual shared browser/worker validators, without huge buffers."""
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_multi_gigabyte_metadata_and_corrupt_batches():
    script = r'''
    const assert = require('node:assert/strict');
    require('./extension/transfer-protocol.js');
    const P = globalThis.ProxyFoundryTransfer;
    const meta = {protocol:2,count:177,zipBytes:Math.floor(1.4*1024**3),batches:[
      {index:0,firstCard:1,lastCard:100,count:100,zipBytes:1024**3},
      {index:1,firstCard:101,lastCard:177,count:77,zipBytes:500*1024**2}
    ]};
    const ready = P.metadata(meta);
    assert.equal(ready.count,177);assert.equal(ready.batches.length,2);
    assert.equal(P.batchAt(ready,1).count,77);
    for (const bad of [-1,2,'0']) assert.throws(()=>P.batchAt(ready,bad));
    for (const patch of [{count:76},{zipBytes:1024**3+1},{firstCard:100},{index:0}]) {
      const bad=structuredClone(meta);Object.assign(bad.batches[1],patch);
      assert.throws(()=>P.metadata(bad));
    }
    for (const patch of [{protocol:3},{batches:[]},{count:1},{count:'177'},{zipBytes:Infinity}]) {
      assert.throws(()=>P.metadata({...meta,...patch}));
    }
    assert.throws(()=>P.metadata({count:177,zipBytes:meta.zipBytes}),/Update and restart/);
    const legacy=P.metadata({count:2,zipBytes:123});
    assert.equal(legacy.legacy,true);assert.equal(legacy.batches[0].zipBytes,123);
    const large={protocol:2,count:600,zipBytes:6*1024**3,batches:Array.from({length:6},(_,i)=>
      ({index:i,firstCard:i*100+1,lastCard:(i+1)*100,count:100,zipBytes:1024**3}))};
    assert.equal(P.metadata(large).batches.length,6);
    '''
    subprocess.run(['node', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
