import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_protocol_accepts_large_totals_but_only_bounded_complete_batches():
    node = shutil.which('node')
    if not node: pytest.skip('Node is required for extension protocol unit tests')
    source = (ROOT / 'extension/transfer-protocol.js').read_text()
    script = source + r'''
const assert=require('node:assert/strict');
const limit=PF_TRANSFER.MAX_BATCH_BYTES;
const batch=(index,count,start,size)=>({index,count,startCard:start,endCard:start+count-1,zipBytes:size,filename:`Batch_${index}.zip`});
const meta={protocol:2,count:177,zipBytes:Math.floor(1.4*limit),batches:[batch(0,125,1,limit),batch(1,52,126,Math.floor(.4*limit))]};
assert.equal(PF_TRANSFER.normalize(meta).batches.length,2);
const invalid=[
 {...meta,batches:[]},
 {...meta,batches:[batch(0,177,1,limit+1)]},
 {...meta,batches:[batch(0,125,1,limit),batch(1,52,127,100)]},
 {...meta,batches:[batch(0,125,1,limit),batch(0,52,126,100)]},
 {...meta,count:178}, {...meta,protocol:3}, {...meta,zipBytes:Infinity},
 {...meta,batches:[batch(0,177,1,-1)]},
 {...meta,batches:[{...batch(0,177,1,100),filename:'../../bad.zip'}]}
];
for(const value of invalid)assert.throws(()=>PF_TRANSFER.normalize(value));
assert.equal(PF_TRANSFER.normalize({count:1,zipBytes:123,filename:'Old.zip'}).batches[0].count,1);
assert.throws(()=>PF_TRANSFER.normalize({count:177,zipBytes:2*limit}));
'''
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)
    manifest = json.loads((ROOT / 'extension/manifest.json').read_text())
    assert manifest['version'] == '1.1.0'
    assert manifest['content_scripts'][1]['js'] == ['transfer-protocol.js', 'bridge.js']
    assert "importScripts('transfer-protocol.js')" in (ROOT / 'extension/background.js').read_text()
