"""Native range assembly avoids Wasm payloads; failed synchronous IO stays an errno."""
import base64,json,shutil,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

def run_node(code):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js')
    result=subprocess.run([node,'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr

def module(path):return json.dumps('data:text/javascript;base64,'+base64.b64encode((ROOT/path).read_bytes()).decode())

def test_native_ranges_preserve_headers_and_offsets_above_two_gibibytes():
    code=r'''
import assert from 'node:assert/strict';
const {WorkspaceFiles}=await import(MODULE),files=new WorkspaceFiles({});
const signature={size:13_399_146_949,modified:1234567890000};
let reads=0,offset;
files.file=async()=>({size:signature.size,lastModified:signature.modified,
    slice:(start,end)=>{reads++;offset=start;return new Blob([new Uint8Array(end-start).fill(23)]);}});
const path='orders/6afeb729-b352-412b-b750-7c55f4e95e00.zip';
const blob=await files.readSpans(path,[{base64:btoa('HEADER')},{offset:2429384400,length:1048576}],signature);
const bytes=new Uint8Array(await blob.arrayBuffer());
assert.equal(offset,2429384400);assert.equal(reads,1);assert.equal(bytes.length,1048582);
assert.equal(new TextDecoder().decode(bytes.subarray(0,6)),'HEADER');assert.equal(bytes.at(-1),23);
await assert.rejects(files.readSpans(path,[{offset:0,length:10}],{...signature,size:1}),/changed/);
await assert.rejects(files.readSpans(path,[{offset:-1,length:10}],signature),/Invalid/);
await assert.rejects(files.readSpans('../workspace.sqlite3',[{offset:0,length:10}],signature),/Invalid/);
await assert.rejects(files.readSpans(path,[{offset:0,length:9*1024*1024}],signature),/Oversized/);
'''.replace('MODULE',module('web/workspace-files.js'))
    run_node(code)

def test_network_exception_in_filesystem_becomes_recoverable_errno():
    code=r'''
import assert from 'node:assert/strict';
const {mountWorkspaceFiles}=await import(MODULE);let fail=false;
globalThis.XMLHttpRequest=class {
    open(method,url){this.query=new URL(url,'http://test').searchParams;}
    send(){if(fail&&this.query.get('operation')==='read')throw new DOMException('Injected connection interruption','NetworkError');
        this.status=200;this.response=new TextEncoder().encode(JSON.stringify({directory:false,size:4,modified:0})).buffer;}
};
const roots={};let ident=0;
const FS={ErrnoError:class extends Error{constructor(errno){super('errno '+errno);this.errno=errno;}},
    createNode:(parent,name,mode)=>{const node={parent,name,mode,id:++ident};if(!parent)node.parent=node;return node;},
    mkdirTree:()=>{},mount:(kind,options,path)=>roots[options.path]=kind.mount({opts:options}),isDir:()=>false};
mountWorkspaceFiles(FS,'owner');const file=roots.orders.node_ops.lookup(roots.orders,'saved.zip');
fail=true;
assert.throws(()=>file.stream_ops.read({node:file},new Uint8Array(4),0,4,2429384400),error=>error instanceof FS.ErrnoError&&error.errno===29);
fail=false;assert.doesNotThrow(()=>file.node_ops.getattr(file));
'''.replace('MODULE',module('web/workspace-fs.js'))
    run_node(code)
