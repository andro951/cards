"""Bounded direct browser downloads preserve bytes and never publish missing files."""
import base64,hashlib,json,shutil,subprocess,time
from pathlib import Path
import pytest
from foundry.domain import ValidationError
from foundry.network import Network
from foundry.storage import Store

ROOT=Path(__file__).resolve().parents[1]


def test_direct_prefetch_concurrency_identical_bytes_and_validation():
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/workspace-files.js').read_bytes()).decode()
    code='''
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
let active=0,peak=0,writes=0;
globalThis.fetch=async()=>{
 active++;peak=Math.max(peak,active);await new Promise(resolve=>setTimeout(resolve,15));active--;
 return new Response(new Uint8Array([0,128,255]),{headers:{'Content-Type':'image/png','Content-Length':'3'}});
};
class Directory {
 constructor(){this.directories=new Map();this.files=new Map();}
 async getDirectoryHandle(name){if(!this.directories.has(name))this.directories.set(name,new Directory());return this.directories.get(name);}
 async getFileHandle(name){const files=this.files;return {async createWritable(){writes++;const chunks=[];return new WritableStream({write(data){chunks.push(data);},close(){files.set(name,new Blob(chunks));}});}};}
}
const {WorkspaceFiles}=await import(MODULE),root=new Directory(),files=new WorkspaceFiles(root);
const encode=value=>new TextEncoder().encode(JSON.stringify(value));
const urls=Array.from({length:6},(_,i)=>'https://raw.githubusercontent.com/o/r/'+'a'.repeat(40)+'/'+i+'.png');
const rows=await files.prefetch(encode(urls));
assert.equal(peak,6);assert.equal(rows.length,6);assert.equal(writes,1,'Identical images share one write.');
const row=rows[0],folder=root.directories.get('assets').directories.get(row.id.slice(0,2));
assert.deepEqual([...new Uint8Array(await folder.files.get(row.id).arrayBuffer())],[0,128,255]);
for(const bad of [Array(7).fill(urls[0]),['https://example.com/a'],['https://raw.githubusercontent.com/o/r/main/a']])await assert.rejects(()=>files.prefetch(encode(bad)),/Invalid/);
await assert.rejects(()=>files.putAsset('assets/../workspace.sqlite3',new Blob(['bad'])),/Invalid/);
'''.replace('MODULE',json.dumps(module))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_prefetch_registers_only_complete_files_and_reuses_the_normal_cache(tmp_path):
    store=Store(tmp_path);raw=b'\x00\x80\xff';ident=hashlib.sha256(raw).hexdigest()
    url='https://raw.githubusercontent.com/o/r/'+'a'*40+'/art.png';calls=[]
    def transport(url):raise AssertionError('A cached image must not download again.')
    def prefetch(urls):
        calls.extend(urls);path=store.asset_path(ident);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return [{'id':ident,'mime':'image/png','bytes':len(raw)}]
    transport.prefetch=prefetch;net=Network(store,transport=transport)
    net.prefetch_immutable([url]);assert calls==[url]
    assert net.fetch(url,immutable=True)[0]==raw
    other=url+'bad';transport.prefetch=lambda urls:[{'id':ident,'mime':'image/png','bytes':999}]
    with pytest.raises(ValidationError):net.prefetch_immutable([other])
    assert not store.cache_get(other)


def test_prefetch_transport_failure_keeps_per_card_fallback_available(tmp_path):
    def transport(url):return b'normal fallback','image/png',{}
    def prefetch(urls):raise RuntimeError('Offline batch')
    transport.prefetch=prefetch;net=Network(Store(tmp_path),transport=transport)
    url='https://raw.githubusercontent.com/o/r/'+'a'*40+'/art.png'
    with pytest.raises(ValidationError,match='Offline batch'):net.prefetch_immutable([url])
    assert net.fetch(url,immutable=True)[0]==b'normal fallback'


def test_validated_png_preparation_reuses_asset_without_reading_or_decoding(tmp_path,monkeypatch):
    from test_art_cache import make_workspace
    ws,sf,calls,raw=make_workspace(tmp_path)
    asset=ws.store.add_asset(raw,'image/png',600,840)
    url='https://raw.githubusercontent.com/owner/repo/'+'a'*40+'/art/one_card.png'
    ws.store.cache_put(url,asset,time.time())
    settings=ws.validate_settings({'source':{'mode':'github','githubFolder':'owner/repo/art'}})
    monkeypatch.setattr('foundry.workspace.ingest_image',lambda *args,**kwargs:pytest.fail('Validated bytes must not be decoded again.'))
    result=ws._art(sf,sf,{},settings,{'one_card':{'url':url}})
    assert result==(asset['id'],'GitHub folder',url)
    assert not calls


def test_async_prefetch_yields_while_downloads_are_pending():
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/workspace-files.js').read_bytes()).decode()
    code=r'''import assert from 'node:assert/strict';
    const {WorkspaceFiles}=await import(MODULE);const files=new WorkspaceFiles({});let complete;
    files.prefetch=async (body,signal,onResult)=>{await new Promise(resolve=>{complete=resolve;});const urls=JSON.parse(new TextDecoder().decode(body));const rows=urls.map(()=>({id:'a'.repeat(64),mime:'image/png',bytes:20}));urls.forEach((url,index)=>onResult(url,rows[index]));return rows;};
    const urls=['https://raw.githubusercontent.com/o/r/'+'a'.repeat(40)+'/one.png'];
    const task=await files.execute('start-artwork','assets',new URLSearchParams(),new TextEncoder().encode(JSON.stringify(urls)));
    const first=await files.execute('poll-artwork',task.id);assert.equal(first.pending,1);assert.equal(first.rows.length,0);
    complete();await files.downloads.get(task.id).finished;
    const last=await files.execute('poll-artwork',task.id);assert.equal(last.pending,0);assert.equal(last.rows[0].url,urls[0]);assert.equal(files.downloads.size,0);
    '''.replace('MODULE',json.dumps(module))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('finish',['success','failure','cancel'])
def test_streaming_downloads_publish_ready_files_without_waiting_for_slow_one(finish):
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/workspace-files.js').read_bytes()).decode()
    code=r'''import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
    Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
    const {WorkspaceFiles}=await import(MODULE),files=new WorkspaceFiles({}),encode=value=>new TextEncoder().encode(JSON.stringify(value));
    let release,started=0,active=0,peak=0;
    globalThis.fetch=async(url,{signal})=>{
        started++;active++;peak=Math.max(peak,active);
        try {
            if(url.endsWith('/0.png'))await new Promise((resolve,reject)=>{
                release=()=>FINISH==='failure'?reject(new Error('slow download failed')):resolve();
                signal.addEventListener('abort',()=>reject(signal.reason),{once:true});
            });
            return new Response(new Uint8Array([0,128,255]),{headers:{'Content-Length':'3'}});
        }finally{active--;}
    };
    files.putAsset=async()=>({ok:true});
    const urls=Array.from({length:19},(_,i)=>'https://raw.githubusercontent.com/o/r/'+'a'.repeat(40)+'/'+i+'.png');
    const task=await files.execute('start-artwork','assets',new URLSearchParams(),encode(urls));
    const state=files.downloads.get(task.id);
    const deadline=Date.now()+2000;
    while(state.ready.length<18&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,1));
    const progress=await files.execute('poll-artwork',task.id);
    assert.equal(progress.pending,1);assert.equal(progress.rows.length,18);
    assert.equal(started,19);assert.ok(peak<=6);assert.ok(progress.rows.every(row=>row.id&&!row.error));
    if(FINISH==='cancel') {
        await files.execute('cancel-artwork',task.id);await state.finished;
        assert.equal(files.downloads.size,0);assert.equal(active,0);
    }
    else {
        release();await state.finished;const final=await files.execute('poll-artwork',task.id);
        assert.equal(final.pending,0);assert.equal(final.rows.length,1);assert.equal(final.rows[0].url,urls[0]);
        assert.equal(Boolean(final.rows[0].error),FINISH==='failure');assert.equal(files.downloads.size,0);
    }
    '''.replace('MODULE',json.dumps(module)).replace('FINISH',json.dumps(finish))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('failed',[False,True])
def test_preparation_publishes_cards_with_ready_art_before_stalled_first_card(tmp_path,monkeypatch,failed):
    from foundry.workspace import Workspace
    from foundry.domain import uid
    from test_pipeline import sf
    from foundry.images import ingest_image
    from test_art_cache import png
    store=Store(tmp_path);art=ingest_image(store,png())['id'];raw={}
    for name in ['Slow first','Ready second','Ready third']:
        card={**sf('Creature — Human'),'id':uid(),'name':name};raw[card['id']]=card
    def transport(url):return json.dumps(raw[url.rsplit('/',1)[-1]]).encode(),'application/json',{}
    ws=Workspace(store,Network(store,transport=transport,sleeper=lambda _:None));deck=ws.new_deck('Ready artwork')
    deck['cards']=[ws.sources.entry(card) for card in raw.values()]
    for card in deck['cards']:card['faces'][0]['artOverride']=art
    deck=store.put('decks',deck,deck['revision'])
    urls={card['id']:'https://raw.githubusercontent.com/o/r/'+('a'*40)+'/'+str(i)+'.png' for i,card in enumerate(deck['cards'])}
    queries=[]
    def art_urls(cards,*args):queries.extend(card['id'] for card in cards);return [urls[card['id']] for card in cards]
    monkeypatch.setattr(ws,'_github_art_urls',art_urls)
    transport.start_prefetch=lambda values:'downloads'
    completions=iter([urls[card['id']] for card in [deck['cards'][1],deck['cards'][2],deck['cards'][0]]])
    def poll(task):
        url=next(completions)
        return {'rows':[{'url':url,**({'error':'HTTP 503'} if failed and url==urls[deck['cards'][0]['id']] else {})}],'pending':1}
    transport.poll_prefetch=poll
    transport.cancel_prefetch=lambda task:None
    monkeypatch.setattr(ws.net,'register_prefetch',lambda *args:None)
    store.generation={'faceCounts':{},'readyFaces':{},'targets':{},'errors':[],'preparedDeckIds':set(),'timings':{}}
    prepared=[];compile_face=ws.compiler.compile_face
    def compile(sf,*args,**kwargs):prepared.append(sf['name']);return compile_face(sf,*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',compile)
    result=ws.prepare(deck['id'])
    assert prepared==(['Ready second','Ready third'] if failed else ['Ready second','Ready third','Slow first'])
    assert [card['name'] for card in result['cards']]==['Slow first','Ready second','Ready third']
    assert len(store.generation['targets'])==(2 if failed else 3)
    assert bool(store.generation['errors'])==failed
    if failed:assert 'HTTP 503' in result['cards'][0]['faces'][0]['error']
    assert len(queries)==3,'Plan artwork once instead of rescanning the deck on every download poll.'
