"""Regressions for runtime suspension, operation freshness and indexed generation metadata."""
import base64,copy,json,shutil,subprocess,time
from pathlib import Path
import pytest
from foundry.network import Network,PendingDownload
from foundry.storage import Store
from foundry.domain import uid,ValidationError
from foundry import token_assignments as tokens,art_variants
from test_pipeline import workspace,sf
from test_github_data_refresh import env

ROOT=Path(__file__).resolve().parents[1]


def test_deferred_runtime_get_keeps_cached_bytes_and_compatibility_fallback(tmp_path):
    from foundry.browser import create_app,request
    from foundry.domain import CC_REPO,CC_COMMIT,COMPAT_REPO,COMPAT_COMMIT
    def transport(url):pytest.fail('A cold runtime GET must suspend before a synchronous download.')
    app=create_app(tmp_path,transport,'https://forge.test')
    path='/img/frames/missing.png'
    primary='https://raw.githubusercontent.com/'+CC_REPO+'/'+CC_COMMIT+path
    compat='https://raw.githubusercontent.com/'+COMPAT_REPO+'/'+COMPAT_COMMIT+'/public'+path
    with app.runtime.net.deferred_downloads():
        with pytest.raises(PendingDownload) as pending:request(app,'GET',path)
    assert pending.value.urls==[primary]
    app.runtime.net.register_downloads([{'url':primary,'error':'Artwork download failed (HTTP 404).'}])
    with app.runtime.net.deferred_downloads():
        with pytest.raises(PendingDownload) as pending:request(app,'GET',path)
    assert pending.value.urls==[compat]
    asset=app.store.add_asset(b'unchanged runtime bytes','image/png')
    app.runtime.net.register_downloads([{'url':compat,'id':asset['id'],'bytes':len(b'unchanged runtime bytes'),'mime':'image/png'}])
    with app.runtime.net.deferred_downloads():result=request(app,'GET',path)
    assert result['status']==200 and result['body']==b'unchanged runtime bytes'


def test_frame_asset_probe_collects_all_independent_downloads(tmp_path):
    from foundry.browser import create_app
    app=create_app(tmp_path,lambda url:pytest.fail('Synchronous frame prefetch is forbidden.'),'https://forge.test')
    data={'frames':[{'src':'/img/frame-one.png','masks':[{'src':'/img/mask-two.png'}]},{'src':'/img/frame-three.png'}]}
    with app.runtime.net.deferred_downloads():
        with pytest.raises(PendingDownload) as pending:app.frame_assets(data)
    assert len(pending.value.urls)==3
    assert not getattr(app,'_frame_assets_ready',set())


def test_github_checks_are_shared_only_inside_one_operation(tmp_path):
    calls=[]
    def transport(url):calls.append(url);return json.dumps({'sha':str(len(calls))}).encode(),'application/json',{}
    net=Network(Store(tmp_path),transport=transport)
    url='https://api.github.com/repos/owner/repo/commits/main'
    def steps():
        assert net.fresh_json(url)=={'sha':'1'}
        yield
        assert net.fresh_json(url)=={'sha':'1'}
        return 'done'
    stream=net.scoped_steps('first',steps());next(stream)
    assert net.fresh_json(url)=={'sha':'2'},'A suspended job must not lend its scope to unrelated work.'
    with pytest.raises(StopIteration) as finished:next(stream)
    assert finished.value.value=='done'
    with net.freshness_scope('second'):assert net.fresh_json(url)=={'sha':'3'}
    assert len(calls)==3


def test_concurrent_checks_for_one_operation_share_the_same_response(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    calls=[]
    def transport(url):calls.append(url);time.sleep(.03);return b'{"sha":"one"}','application/json',{}
    net=Network(Store(tmp_path),transport=transport)
    def check():
        with net.freshness_scope('same-operation'):return net.fresh_json('https://api.github.com/repos/o/r/commits/main')
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:check(),range(3)))
    assert results==[{'sha':'one'}]*3 and len(calls)==1


def test_artwork_review_data_refresh_and_preparation_share_one_head_check(env):
    ws,deck,remote=env
    deck['settings']['source'].update(mode='github',githubFolder='https://github.com/owner/repo/tree/main/deck/art')
    deck=ws.store.put('decks',deck,deck['revision'])
    ws.artwork_review({'deckId':deck['id'],'freshnessScope':'generate-one'})
    stream=ws.net.scoped_steps('generate-one',ws.prepare_steps(deck['id']))
    list(stream)
    heads=[url for url in remote.calls if '/commits/' in url]
    assert len(heads)==1
    list(ws.net.scoped_steps('generate-two',ws.prepare_steps(deck['id'])))
    assert len([url for url in remote.calls if '/commits/' in url])==2


def test_token_indexes_preserve_resolution_precedence_and_ambiguity():
    cards=[{'id':uid(),'name':'Angel','scryfall':{'name':'Angel','id':uid(),'oracle_id':uid()}} for _ in range(2)]
    first,second=cards
    ref={**tokens.reference(first),'oracle_id':second['scryfall']['oracle_id']}
    assert tokens.resolve(cards,ref) is first
    ref['scryfall_id']=uid()
    assert tokens.resolve(cards,ref) is second
    assert tokens.resolve(cards,{'name':'Angel'}) is None
    duplicate=copy.deepcopy(first);duplicate['id']=uid()
    assert tokens.resolve([first,duplicate],tokens.reference(first)) is first
    duplicate['scryfall']['oracle_id']=uid()
    assert tokens.resolve([first,duplicate],{'name':'Angel','scryfall_id':first['scryfall']['id']}) is None


def test_shared_token_rows_do_not_rescan_card_references(monkeypatch):
    cards=[{'id':uid(),'name':f'Token {i}','quantity':1,'scryfall':{'name':f'Token {i}','layout':'token'},'faces':[{}]} for i in range(180)]
    rows=[{'front':{'name':f'Absent {i}'},'back':{'kind':'card-back'},'quantity':1} for i in range(10000)]
    deck={'cards':cards,'settings':{'tokenAssignments':rows}}
    original=tokens.reference;calls=[]
    def reference(card):calls.append(card['id']);return original(card)
    monkeypatch.setattr(tokens,'reference',reference)
    report=tokens.overview(deck)
    assert len(report['unused'])==180 and not report['invalid']
    assert len(calls)<180*8


def test_unrelated_art_variants_do_not_rescan_card_groups(monkeypatch):
    cards=[{'id':uid(),'name':f'Card {i}','quantity':1,'scryfall':{'name':f'Card {i}'},'faces':[{'name':f'Card {i}'}]} for i in range(180)]
    rows=[{'id':uid(),'card':{'name':f'Absent {i}'},'quantity':1,'faces':[{'name':f'Absent {i}','art':'unused.png'}]} for i in range(1000)]
    original=art_variants.reference;calls=[]
    def reference(card):calls.append(card['id']);return original(card)
    monkeypatch.setattr(art_variants,'reference',reference)
    assert not art_variants.apply({'cards':cards,'settings':{'artVariants':rows}},lambda face:pytest.fail('No unrelated face may invalidate.'))
    assert len(calls)==180


def test_token_seeds_preserve_final_output_without_building_source_frames(workspace,monkeypatch):
    from foundry.compiler import Compiler,semantic
    from foundry.workspace import Workspace
    from foundry.legacy import compiler as native
    store,art,settings=workspace;ws=Workspace(store);compiler=Compiler(store)
    for choice in ('auto','normal','godzilla-card'):
        for kind in ('Creature — Angel','Legendary Creature — Human','Artifact','Enchantment — Aura'):
            for nickname in ('','New Name'):
                card=sf(kind,['W']);options={'templateOverride':choice,'semanticOverrides':{'nickname':nickname}}
                ordinary=compiler.compile_face(card,card,0,options,settings,art)
                original=native.recipe_data
                monkeypatch.setattr(native,'recipe_data',lambda *args:pytest.fail('Discarded source frames must not be assembled.'))
                seed=compiler.compile_face(card,card,0,options,settings,art,conversion_seed=True)
                monkeypatch.setattr(native,'recipe_data',original)
                assert seed['data']['frames']==[]
                sem={**semantic(card,card),'nickname':nickname}
                for style in ('token-full-art','token-classic','token-borderless'):
                    spec={'token_frame_style':style}
                    expected=ws._apply_token_spec(copy.deepcopy(ordinary),spec,art,'Token',sem=sem)
                    actual=ws._apply_token_spec(copy.deepcopy(seed),spec,art,'Token',sem=sem)
                    assert actual['data']==expected['data'],(choice,kind,nickname,style)
                    assert actual['renderKey']==expected['renderKey']


def test_runtime_queue_releases_engine_lane_and_bounds_downloads():
    source=(ROOT/'web/runtime-downloads.js').read_text().replace("import {WorkspaceFiles} from './workspace-files.js';",'class WorkspaceFiles {}')
    module='data:text/javascript;base64,'+base64.b64encode(source.encode()).decode()
    queue='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/request-queue.js').read_bytes()).decode()
    code=r'''import assert from 'node:assert/strict';
    const {RuntimeDownloads}=await import(MODULE),{RequestQueue}=await import(QUEUE);
    let active=0,peak=0;const release=[];
    const downloads=new RuntimeDownloads(null,{files:{prefetch:async(body,signal)=>{
      active++;peak=Math.max(peak,active);
      await new Promise(resolve=>{release.push(resolve);signal.addEventListener('abort',resolve,{once:true});});
      active--;return [{id:'a'.repeat(64),bytes:3}];
    }}});
    const engine=new RequestQueue();let waiting;
    await engine.enqueue(()=>{waiting=downloads.load(Array.from({length:12},(_,i)=>String(i)));});
    let progressed=false;await engine.enqueue(()=>{progressed=true;});assert.ok(progressed);
    assert.equal(peak,6);assert.equal(downloads.get('0'),downloads.get('0'));
    while(release.length) {release.splice(0).forEach(resolve=>resolve());await new Promise(resolve=>setTimeout(resolve,0));}
    const rows=await waiting;assert.equal(rows.length,12);assert.equal(active,0);assert.equal(peak,6);
    downloads.acknowledge(rows);assert.equal(downloads.pending.size,0);
    const cancelled=downloads.load(['cancel']);downloads.cancel();await cancelled;assert.equal(downloads.pending.size,0);
    '''.replace('MODULE',json.dumps(module)).replace('QUEUE',json.dumps(queue))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_two_token_treatments_fit_only_the_final_frame(workspace,monkeypatch):
    from foundry.compiler import Compiler,semantic
    from foundry.workspace import Workspace
    import foundry.workspace as module
    store,art,settings=workspace;ws=Workspace(store);compiler=Compiler(store)
    fit=module.fit_token_art;fits=[]
    def tracked(*args,**kwargs):fits.append(1);return fit(*args,**kwargs)
    monkeypatch.setattr(module,'fit_token_art',tracked)
    for nickname in ('','New Name'):
        card=sf('Legendary Creature — Human',['G'])
        options={'semanticOverrides':{'nickname':nickname}};sem={**semantic(card,card),'nickname':nickname}
        source=compiler.compile_face(card,card,0,options,settings,art)
        seed=compiler.compile_face(card,card,0,options,settings,art,conversion_seed=True)
        first={'nonlegendary':True,'power_toughness':'7/8','replace_creature_subtypes':'Illusion'}
        for mode in ('original','legendary','nonlegendary'):
            for style in ('token-full-art','token-classic','token-borderless','godzilla-card'):
                current={**settings,'allCardsTokens':True,'templateRules':{'token':style},'tokenOptions':{'legendaryMode':mode,'power':'9'}}
                old=ws._apply_token_spec(copy.deepcopy(source),first,art,'First',sem=sem)
                old=ws._apply_token_spec(old,ws._deck_token_spec(current,old),art,'Deck-wide token',sem=sem)
                fits.clear()
                partial=ws._apply_token_spec(copy.deepcopy(seed),first,art,'First',sem=sem,finalize=False)
                assert not fits
                actual=ws._apply_token_spec(partial,ws._deck_token_spec(current,partial),art,'Deck-wide token',sem=sem)
                assert len(fits)==1
                assert actual['data']==old['data'],(nickname,mode,style)
                assert actual['renderKey']==old['renderKey']


def test_artwork_transient_retry_finishes_asynchronously_and_404_is_not_retried():
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/workspace-files.js').read_bytes()).decode()
    code=r'''import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
    Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
    const {WorkspaceFiles}=await import(MODULE),files=new WorkspaceFiles({});files.putAsset=async()=>({ok:true});
    const attempts=new Map();globalThis.fetch=async url=>{
      const count=(attempts.get(url)||0)+1;attempts.set(url,count);
      if(url.endsWith('missing.png'))return new Response('missing',{status:404});
      if(count===1)return new Response('retry',{status:503});
      return new Response(new Uint8Array([1,2,3]));
    };
    const urls=['retry.png','missing.png'].map(file=>'https://raw.githubusercontent.com/o/r/'+'a'.repeat(40)+'/'+file);
    const rows=await files.prefetch(new TextEncoder().encode(JSON.stringify(urls)));
    assert.ok(rows[0].id);assert.match(rows[1].error,/HTTP 404/);
    assert.equal(attempts.get(urls[0]),2);assert.equal(attempts.get(urls[1]),1);
    '''.replace('MODULE',json.dumps(module))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_identical_assets_from_independent_download_requests_share_the_writer():
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'web/workspace-files.js').read_bytes()).decode()
    code=r'''import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
    Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
    const {WorkspaceFiles}=await import(MODULE),files=new WorkspaceFiles({});let release,writes=0;
    const gate=new Promise(resolve=>{release=resolve;});
    files.putAsset=async()=>{writes++;await gate;return {ok:true};};
    globalThis.fetch=async()=>new Response(new Uint8Array([1,2,3]));
    const encode=file=>new TextEncoder().encode(JSON.stringify(['https://raw.githubusercontent.com/o/r/'+'a'.repeat(40)+'/'+file]));
    const a=files.prefetch(encode('white.png')),b=files.prefetch(encode('artifact.png'));
    await new Promise(resolve=>setTimeout(resolve,40));assert.equal(writes,1);
    release();const [first,second]=await Promise.all([a,b]);assert.equal(first[0].id,second[0].id);
    assert.equal(files.assetWrites.size,0);
    '''.replace('MODULE',json.dumps(module))
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr