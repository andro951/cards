"""Run the shipped ZIP writer with slow writable acknowledgements and validate its archive."""
import json,shutil,subprocess,zipfile
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]

def test_zip_writes_bounded_native_chunks_and_reports_saving_and_close(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js')
    (tmp_path/'stored-zip.mjs').write_text((ROOT/'site/stored-zip.js').read_text(encoding='utf-8'),encoding='utf-8')
    (tmp_path/'worker.mjs').write_text((ROOT/'site/order-zip-worker.js').read_text(encoding='utf-8').replace("'./stored-zip.js'","'./stored-zip.mjs'"),encoding='utf-8')
    script=r'''
import {writeFile} from 'node:fs/promises';
const events=[],chunks=[];let resolve,reject;
const complete=new Promise((yes,no)=>{resolve=yes;reject=no;});
globalThis.self={postMessage:value=>{events.push(value);if(value.state==='done')resolve();if(value.error)reject(new Error(value.error));}};
await import('./worker.mjs');
const file=new Blob([new Uint8Array(40*1024*1024).fill(23)]);
let closed=false;
const writer={write:async data=>{if(!(data instanceof Blob))throw new Error('Keep native Blob copying');chunks.push(Buffer.from(await data.arrayBuffer()));await new Promise(r=>setTimeout(r,300));},
    close:async()=>{await new Promise(r=>setTimeout(r,1200));closed=true;},abort:async()=>{}};
const directory={getDirectoryHandle:async()=>directory,getFileHandle:async()=>({getFile:async()=>file,createWritable:async()=>writer})};
self.onmessage({data:{directory,path:'orders/test.zip',entries:[{path:'assets/front',name:'FRONT/000001.png',label:'Front'},{path:'assets/front',name:'BACK/000001.png',label:'Back'}]}});
await complete;
if(!closed)throw new Error('Completed before close');
await writeFile('paired.zip',Buffer.concat(chunks));
console.log(JSON.stringify({sizes:chunks.map(c=>c.length),events}));
'''
    (tmp_path/'test.mjs').write_text(script,encoding='utf-8')
    result=subprocess.run([node,'test.mjs'],cwd=tmp_path,capture_output=True,text=True,check=True,timeout=30)
    report=json.loads(result.stdout)
    assert max(report['sizes'])==64*1024*1024 and len(report['sizes'])==2
    saving=[e for e in report['events'] if e.get('phase')=='saving']
    assert any(0<e['savedBytes']<e['totalBytes'] and e['saveEtaSeconds']>0 for e in saving)
    assert sum(e.get('saveStage')=='finalizing' for e in saving)>=2
    assert saving[-1]['state']=='done' and saving[-1]['savedBytes']==saving[-1]['totalBytes']
    with zipfile.ZipFile(tmp_path/'paired.zip') as archive:
        assert archive.testzip() is None
        assert archive.namelist()==['FRONT/000001.png','BACK/000001.png']
        assert all(archive.getinfo(name).file_size==40*1024*1024 for name in archive.namelist())
