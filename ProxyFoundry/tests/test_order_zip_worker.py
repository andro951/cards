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

def test_native_worker_splits_only_between_pairs_and_fills_each_part(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js')
    source=(ROOT/'site/stored-zip.js').read_text(encoding='utf-8').replace('PRINTER_ZIP_LIMIT=1_999_999_999','PRINTER_ZIP_LIMIT=3000')
    (tmp_path/'stored-zip.mjs').write_text(source,encoding='utf-8')
    (tmp_path/'worker.mjs').write_text((ROOT/'site/order-zip-worker.js').read_text(encoding='utf-8').replace("'./stored-zip.js'","'./stored-zip.mjs'"),encoding='utf-8')
    script='''
import {writeFile} from 'node:fs/promises';
let complete,fail;const ready=new Promise((yes,no)=>{complete=yes;fail=no});
globalThis.self={postMessage:row=>{if(row.error)fail(Error(row.error));if(row.state==='done')complete(row)}};
await import('./worker.mjs');
const files=new Map();
const directory={getDirectoryHandle:async()=>directory,getFileHandle:async name=>({getFile:async()=>new Blob([new Uint8Array(1024).fill(31)]),createWritable:async()=>{
 const chunks=[];return {write:async blob=>chunks.push(Buffer.from(await blob.arrayBuffer())),close:async()=>{files.set(name,Buffer.concat(chunks));},abort:async()=>{}};
}})};
const entries=[];for(let i=1;i<=3;i++)for(const side of ['FRONT','BACK'])entries.push({name:side+'/'+String(i).padStart(6,'0')+'.png',path:'assets/'+side+i,label:side});
self.onmessage({data:{directory,path:'orders/test',entries}});
const result=await ready;
for(const [name,bytes] of files)await writeFile(name,bytes);
console.log(JSON.stringify(result.parts));
'''
    (tmp_path/'test.mjs').write_text(script)
    result=subprocess.run([node,'test.mjs'],cwd=tmp_path,capture_output=True,text=True,check=True,timeout=30)
    parts=json.loads(result.stdout);assert [p['count'] for p in parts]==[1,1,1]
    for index,part in enumerate(parts,1):
        assert part['zipBytes']<=3000 and part['firstCard']==part['lastCard']==index
        with zipfile.ZipFile(tmp_path/part['filename']) as z:
            assert z.testzip() is None and z.namelist()==[f'{side}/{index:06d}.png' for side in ['FRONT','BACK']]
