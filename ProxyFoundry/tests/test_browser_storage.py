"""Real static browser storage, ownership and bounded binary filesystem tests."""
import functools
import http.server
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual Chromium browser storage')


@pytest.fixture
def static_browser(tmp_path,request):
    from playwright.sync_api import sync_playwright
    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py'),'--output',str(tmp_path/'built')],cwd=ROOT,check=True,capture_output=True)
    directory=tmp_path/'site';shutil.copytree(tmp_path/'built',directory)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(directory)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as playwright:
        channel=getattr(request,'param',None)
        if channel:
            # Chromium cannot restore serialized OPFS handles in its private
            # test context. A regular profile exercises actual handle reuse.
            context=playwright.chromium.launch_persistent_context(str(tmp_path/'browser-profile'),headless=True,channel=channel);browser=context.browser
        else:
            browser=playwright.chromium.launch(headless=True);context=browser.new_context()
        yield directory,context,f'http://127.0.0.1:{server.server_port}'
        context.close();browser.close()
    server.shutdown();server.server_close();thread.join(timeout=5)


@pytest.mark.parametrize('static_browser',['chromium'],indirect=True,ids=['native-handles'])
def test_static_artwork_pairing_persists_without_rendering(static_browser):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_artwork_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/seed-artwork':
        import copy,base64
        from foundry.workspace import DEFAULT_SETTINGS
        settings=copy.deepcopy(DEFAULT_SETTINGS)
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=')
        asset=app.store.add_asset(raw,'image/png',1,1)
        settings['source'].update(mode='local',localFiles={'first':asset['id'],'second':asset['id']},localNames={'first':'112_spirit.png','second':'113_spirit.png'},fallback=False)
        cards=[]
        for oracle,color in [('dc4e2134-f0c2-49aa-9ea3-ebf83af1445c','W'),('6a7a9dff-ff9e-4005-a17f-6ea0c11c1d5a','U')]:
            sf={'id':oracle,'oracle_id':oracle,'name':'Spirit','type_line':'Token Creature — Spirit','layout':'token','colors':[color],'power':'1','toughness':'1','image_uris':{'normal':'data:image/png;base64,'+base64.b64encode(raw).decode()}}
            cards.append(app.ws.sources.entry(sf))
        deck=app.store.put('decks',{'name':'Pair spirits','id':'11111111-1111-4111-8111-111111111111','settings':settings,'status':'draft','cards':cards})
        return {'status':200,'mime':'application/json','body':json.dumps(deck).encode(),'headers':{}}
    return original_artwork_request(app,method,url,body,headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    page.evaluate("async()=>{await fetch('/api/__test__/seed-artwork');location.hash='#deck/11111111-1111-4111-8111-111111111111/setup';}")
    page.click('#review-artwork');page.locator('#artwork-counts').wait_for(timeout=30000)
    assert page.locator('[data-artwork-card]').count()==2 and page.locator('[data-artwork-file]').count()==2
    page.screenshot(path=str(ROOT/'test-results/artwork-static-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path=str(ROOT/'test-results/artwork-static-mobile.png'))
    page.set_viewport_size({'width':1280,'height':720})
    for file in ['first','second']:
        page.locator('[data-artwork-card]').first.click();page.locator('[data-artwork-file="'+file+'"]').click()
    page.click('#artwork-finish');page.wait_for_function("() => document.querySelector('#setup-state')?.textContent==='Changes saved'")
    page.get_by_role('heading',name='Save artwork choices for next time?').wait_for();page.get_by_role('button',name='Not now',exact=True).click()
    page.evaluate("""async()=>{
      const files=await import('/site/artwork-files.js'),root=await navigator.storage.getDirectory();
      const folder=await root.getDirectoryHandle('artwork-source-test',{create:true}),handle=await folder.getFileHandle('data.json',{create:true});
      const original={version:1,cards:[{name:'Spirit',nickname:'Ghost'}]},writer=await handle.createWritable();await writer.write(JSON.stringify(original));await writer.close();
      await files.rememberFile('artwork-native-file',handle,original);await files.rememberFolder('artwork-native-folder',await folder.getDirectoryHandle('new-data',{create:true}));
    }""")
    page.reload(wait_until='domcontentloaded');page.locator('#review-artwork').wait_for(timeout=90000)
    report=page.evaluate("""async()=>{const ui=await import('/site/ui.js'),files=await import('/site/artwork-files.js');const deck=await ui.api('/api/decks/11111111-1111-4111-8111-111111111111');const review=await ui.job('/api/setup/artwork-review',{deckId:deck.id});
      const retained=await files.sourceRecord('deck:artwork-native-file');
      const saved=await files.saveLocalData(retained,[{name:'Spirit',art:'spirit.png'}]);
      const folderRecord=await files.sourceRecord('deck:artwork-native-folder');
      const created=await files.saveLocalData(folderRecord,[{name:'Day',art:'day.png'}]);
      const local=JSON.parse(await (await saved.file.getFile()).text());
      return {local,created:JSON.parse(await (await created.file.getFile()).text()),data:deck.cardData,faces:deck.cards.map(c=>c.faces[0].artFilename),review,iframes:document.querySelectorAll('iframe').length};}""")
    assert set(report['faces'])=={'112_spirit.png','113_spirit.png'}
    assert len(report['data'])==2 and all(entry.get('oracle_id') for entry in report['data'])
    assert not report['review']['needsReview'] and not report['iframes']
    assert report['local']['cards']==[{'name':'Spirit','nickname':'Ghost','art':'spirit.png'}]
    assert report['created']['cards']==[{'name':'Day','art':'day.png'}]


def test_folder_permission_requires_reconnection_without_workspace_fallback(static_browser):
    directory,context,origin=static_browser
    choice=directory/'web/storage-choice.js'
    source=choice.read_text();start=source.index('export async function savedFolder()');end=source.index('\nexport async function chooseFolder',start)
    source=source[:start]+'''export async function savedFolder(){
      const root=await navigator.storage.getDirectory();
      const folder=await root.getDirectoryHandle('chosen-test-workspace',{create:true});
      folder.queryPermission=async()=>localStorage.getItem('folder-permission')||'prompt';
      folder.requestPermission=async()=>{localStorage.setItem('folder-permission','granted');return 'granted';};
      return folder;
    }
''' +source[end:];choice.write_text(source)
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded')
    page.get_by_role('button',name='Reconnect workspace folder').wait_for(timeout=15000)
    assert not page.locator('#import-deck').is_visible()
    page.get_by_role('button',name='Reconnect workspace folder').click()
    page.locator('#import-deck').wait_for(timeout=90000)
    assert page.evaluate("async()=>(await (await fetch('/api/bootstrap')).json()).storageType")== 'selected-folder'
    page.evaluate("async()=>{const ui=await import('/site/ui.js');await ui.api('/api/decks/new',{name:'Folder deck'});localStorage.setItem('folder-permission','prompt');}")
    page.reload(wait_until='domcontentloaded')
    page.get_by_role('button',name='Reconnect workspace folder').wait_for(timeout=15000)
    assert not page.locator('#import-deck').is_visible()
    page.get_by_role('button',name='Reconnect workspace folder').click()
    page.get_by_text('Folder deck',exact=True).wait_for(timeout=90000)


def test_second_tab_cannot_write_and_can_open_after_first_closes(static_browser):
    directory,context,origin=static_browser
    first=context.new_page();first.goto(origin,wait_until='domcontentloaded')
    first.locator('#import-deck').wait_for(timeout=90000)
    assert first.evaluate("async()=>(await (await fetch('/api/bootstrap')).json()).storageType")== 'browser'
    first.evaluate("async()=>{const ui=await import('/site/ui.js');await ui.api('/api/decks/new',{name:'Saved once'});}")
    second=context.new_page();second.goto(origin,wait_until='domcontentloaded')
    second.get_by_role('button',name='Retry opening workspace').wait_for(timeout=15000)
    assert not second.locator('#import-deck').is_visible()
    first.close();second.get_by_role('button',name='Retry opening workspace').click()
    second.get_by_text('Saved once',exact=True).wait_for(timeout=90000)


def test_workspace_picker_holds_exclusive_access_and_releases_on_cancel(static_browser):
    from playwright.sync_api import expect
    _,context,origin=static_browser
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded')
    page.locator('#import-deck').wait_for(timeout=90000)
    page.click('.topbar [data-nav=settings]')
    page.get_by_role('heading',name='Workspace storage',exact=True).wait_for(timeout=30000)
    page.evaluate("""async()=>{
        const ui=await import('/site/ui.js');window.__work=ui.work;
        window.__generation=ui.work.begin({label:'Generate A',resources:['deck:A']});
        window.__pickerCalls=0;
        window.showDirectoryPicker=()=>{window.__pickerCalls++;return new Promise((_,reject)=>window.__cancelPicker=reject);};
    }""")
    page.get_by_role('button',name='Choose a different location',exact=True).click()
    expect(page.locator('#toast-host')).to_contain_text('whole workspace')
    assert page.evaluate('window.__pickerCalls')==0
    page.evaluate('window.__work.finish(window.__generation)')
    page.get_by_role('button',name='Choose a different location',exact=True).click()
    page.wait_for_function('window.__pickerCalls===1')
    conflict=page.evaluate("async()=>{const ui=await import('/site/ui.js');try{await ui.api('/api/decks/new',{});return '';}catch(error){return error.message;}}")
    assert 'Move workspace is changing the workspace' in conflict
    page.evaluate("window.__cancelPicker(new DOMException('Picker cancelled','AbortError'))")
    page.wait_for_function('!window.__work.busy')
    deck=page.evaluate("async()=>{const ui=await import('/site/ui.js');return ui.api('/api/decks/new',{name:'After picker cancellation'});}")
    assert deck['name']=='After picker cancellation'


def test_binary_files_and_zip_do_not_live_in_python_memory_and_survive_reload(static_browser):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text()
    injected='''
original_request = request
def request(app, method, url, body, headers):
    if str(url) == '/api/__test__/storage-write':
        import zipfile
        root=app.store.home/'tmp'/'storage-stress'
        root.mkdir(exist_ok=True)
        for i in range(100):
            (root/(str(i)+'.bin')).write_bytes(bytes([i])*1024*1024)
        archive=app.store.home/'orders'/'storage-test.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as output:
            for i in range(100):output.write(root/(str(i)+'.bin'),str(i)+'.bin')
        result={'bytes':archive.stat().st_size,'files':len(list(root.iterdir()))}
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    if str(url) == '/api/__test__/storage-read':
        import zipfile
        archive=app.store.home/'orders'/'storage-test.zip'
        with zipfile.ZipFile(archive) as saved:
            result={'files':len(saved.namelist()),'sample':list(saved.open('80.bin').read(4))}
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_request(app, method, url, body, headers)
'''
    source=source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):')
    source=source.replace("const metadata=JSON.parse(responseText(encoded.metadata));", "const metadata=JSON.parse(responseText(encoded.metadata));\n    if(url.startsWith('/api/__test__/storage')){\n      const node=python.FS.lookupPath('/workspace/tmp/storage-stress/80.bin').node;\n      metadata.headers['X-Test-Cached-Bytes']=String(node.contents?.byteLength||node.contents?.length||0);\n    }")
    worker.write_text(source)
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded')
    page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate("""async()=>{
      const ui=await import('/site/ui.js');
      const response=await fetch('/api/__test__/storage-write',{method:'POST',headers:{'X-CSRF-Token':ui.state.bootstrap.csrf},body:'{}'});
      return {status:response.status,cached:response.headers.get('X-Test-Cached-Bytes'),data:await response.json()};
    }""")
    assert result['status']==200,result
    assert result['cached']=='0' and result['data']['files']==100
    assert result['data']['bytes']>100*1024*1024
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    saved=page.evaluate("async()=>{const response=await fetch('/api/__test__/storage-read');return {cached:response.headers.get('X-Test-Cached-Bytes'),data:await response.json()};}")
    assert saved=={'cached':'0','data':{'files':100,'sample':[80,80,80,80]}}



def test_reload_mid_job_preserves_committed_items_and_reports_interruption(static_browser):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if str(url) == '/api/__test__/checkpoint-job':
        import time
        def operation(update,cancel):
            for index in range(40):
                app.store.put('decks',{'name':'Checkpoint '+str(index),'cards':[],
                    'settings':app.ws.validate_settings({}),'status':'draft'})
                update(index+1,40,'Committed '+str(index+1))
                time.sleep(.2)
            return {'saved':40}
        result=app.jobs.start('Checkpoint recovery',operation)
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_request(app, method, url, body, headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded')
    page.locator('#import-deck').wait_for(timeout=90000)
    ident=page.evaluate("async()=>{const ui=await import('/site/ui.js');return (await ui.api('/api/__test__/checkpoint-job',{})).id;}")
    import time
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        current=page.evaluate("async id=>(await (await fetch('/api/jobs/'+id)).json())",ident)
        if current['state']=='running' and current['done']>=3:break
        time.sleep(.05)
    else:raise AssertionError('No committed job checkpoint was observed: '+str(current))
    import sqlite3
    checkpoint=directory/'checkpoint-test.sqlite3'
    raw=page.evaluate("async()=>{const root=await navigator.storage.getDirectory();const file=await (await root.getFileHandle('workspace.sqlite3')).getFile();return [...new Uint8Array(await file.arrayBuffer())];}")
    checkpoint.write_bytes(bytes(raw))
    with sqlite3.connect(checkpoint) as db:assert db.execute("select count(*) from documents where kind='decks'").fetchone()[0]>=3
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    saved=page.evaluate("async id=>({decks:await (await fetch('/api/decks')).json(),job:await (await fetch('/api/jobs/'+id)).json()})",ident)
    assert 3<=len(saved['decks'])<40
    assert saved['job'].get('state')=='failed' and 'interrupted' in saved['job'].get('error',''),saved
    assert saved['job']['done']<=len(saved['decks'])



def test_storage_quota_error_is_readable_diagnosed_and_upload_can_retry(static_browser):
    import io
    from PIL import Image
    directory,context,origin=static_browser
    files=directory/'web/workspace-files.js';source=files.read_text(encoding='utf-8')
    source=source.replace('execute = async (operation,path,query,body) => {',"execute = async (operation,path,query,body) => {\n        if(operation===`write`&&path.startsWith('assets/')&&localStorage.getItem('inject-quota')==='1')throw new DOMException('Injected storage full','QuotaExceededError');")
    files.write_text(source,encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    buffer=io.BytesIO();Image.new('RGB',(120,160),'purple').save(buffer,'PNG')
    result=page.evaluate("""async bytes=>{
      const ui=await import('/site/ui.js');localStorage.setItem('inject-quota','1');
      const first=await fetch('/api/uploads',{method:'POST',headers:{'X-Proxy-CSRF':ui.state.csrf,'Content-Type':'image/png'},body:new Uint8Array(bytes)});
      const failed={status:first.status,body:await first.json()};localStorage.removeItem('inject-quota');
      const retry=await ui.blobRequest('/api/uploads',new Uint8Array(bytes),'image/png');
      const image=await fetch('/api/assets/'+retry.id);return {failed,retry:{width:retry.width,height:retry.height},bytes:(await image.arrayBuffer()).byteLength};
    }""",list(buffer.getvalue()))
    assert result['failed']['status']==507 and 'Workspace storage is full' in result['failed']['body']['error']
    assert result['retry']=={'width':120,'height':160} and result['bytes']>0
    page.get_by_role('link',name='Settings',exact=True).click()
    page.get_by_role('button',name='Download Diagnostics',exact=True).wait_for(timeout=30000)
    entries=page.evaluate("async()=>{const diagnostics=await import('/site/diagnostics.js');return JSON.parse(localStorage.getItem('bulk-proxy-forge-browser-diagnostics'));}")
    assert any('QuotaExceededError' in row['detail'] and 'quota' in row['detail'] for row in entries['entries'])
    assert not any('NotFoundError' in row['detail'] for row in entries['entries'])



@pytest.mark.parametrize('existing_destination',[False,True])
@pytest.mark.parametrize('operation',['rename','copy'])
def test_failed_rename_preserves_source_and_destination_and_retries(static_browser,existing_destination,operation):
    directory,context,origin=static_browser
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded')
    page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate("""async ({existing,operation})=>{
      const {WorkspaceFiles}=await import('/web/workspace-files.js');
      const root=await (await navigator.storage.getDirectory()).getDirectoryHandle('rename-quota-test',{create:true});
      const assets=await root.getDirectoryHandle('assets',{create:true}),files=new WorkspaceFiles(root);
      const parameters=new URLSearchParams({offset:'0'});
      await files.execute('write','assets/source.bin',parameters,new Uint8Array([4,5,6]));await files.close('assets/source.bin');
      if(existing){await files.execute('write','assets/target.bin',parameters,new Uint8Array([1,2,3]));await files.close('assets/target.bin');}
      const getDirectory=root.getDirectoryHandle.bind(root),getFile=assets.getFileHandle.bind(assets);
      root.getDirectoryHandle=async(name,options)=>name==='assets'?assets:getDirectory(name,options);
      let fail=true;
      assets.getFileHandle=async(name,options)=>{
        const handle=await getFile(name,options);
        if(name==='target.bin'&&fail){
          const create=handle.createWritable.bind(handle);
          handle.createWritable=async options=>{
            const saved=await create(options);
            return new WritableStream({write:async()=>{await saved.abort();throw new DOMException('Injected rename quota','QuotaExceededError');}});
          };
        }
        return handle;
      };
      const rename=new URLSearchParams({destination:'assets/target.bin'});
      let error;try{await files.execute(operation,'assets/source.bin',rename);}catch(failure){error=failure.name;}
      const read=async name=>[...new Uint8Array(await (await files.file('assets/'+name)).arrayBuffer())];
      const source=await read('source.bin');let destination=null;
      try{destination=await read('target.bin');}catch(failure){if(failure.name!=='NotFoundError')throw failure;}
      fail=false;await files.execute(operation,'assets/source.bin',rename);
      let sourceRemoved=false;try{await files.file('assets/source.bin');}catch(failure){sourceRemoved=failure.name==='NotFoundError';}
      return {error,source,destination,retried:await read('target.bin'),sourceRemoved};
    }""",{'existing':existing_destination,'operation':operation})
    assert result=={'error':'QuotaExceededError','source':[4,5,6],
        'destination':[1,2,3] if existing_destination else None,'retried':[4,5,6],'sourceRemoved':operation=='rename'}


def test_open_file_reads_and_log_rotation_use_the_renamed_paths(static_browser):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if str(url) == '/api/__test__/log-rotation':
        from pathlib import Path
        root=app.store.home/'tmp'
        source=root/'before.txt';destination=root/'after.txt'
        with source.open('w',encoding='utf-8') as writer:
            writer.write('Buffered text');writer.flush()
            assert source.read_text(encoding='utf-8')=='Buffered text'
        source.replace(destination)
        assert destination.read_text(encoding='utf-8')=='Buffered text'
        assert not source.exists()
        for handler in app.log.handlers:
            handler.maxBytes=4096
        for index in range(80):app.log.info('Rotation sample %s %s',index,'x'*400)
        assert 'Rotation sample 79' in (app.store.home/'logs/app.log').read_text(encoding='utf-8')
        assert (app.store.home/'logs/app.log.1').is_file()
        return {'status':200,'mime':'application/json','body':b'{"ok":true}','headers':{}}
    return original_request(app, method, url, body, headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate("async()=>{const response=await fetch('/api/__test__/log-rotation');return {status:response.status,data:await response.json()};}")
    assert result=={'status':200,'data':{'ok':True}}



def test_repeated_asset_lookups_reuse_file_metadata_and_writes_refresh_it(static_browser):
    directory,context,origin=static_browser
    files=directory/'web/workspace-files.js';source=files.read_text(encoding='utf-8')
    files.write_text(source.replace('execute = async (operation,path,query,body) => {',"execute = async (operation,path,query,body) => {\n        if(operation===`stat`)window.testStatCalls=(window.testStatCalls||0)+1;"),encoding='utf-8')
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if str(url) == '/api/__test__/metadata-cache':
        path=app.store.home/'tmp'/'cached-stat.txt'
        path.write_bytes(b'first');assert path.stat().st_size==5
        for index in range(100):assert path.stat().st_size==5
        path.write_bytes(b'second write');assert path.stat().st_size==12
        for index in range(100):assert path.stat().st_size==12
        path.unlink();assert not path.exists()
        return {'status':200,'mime':'application/json','body':b'{"ok":true}','headers':{}}
    return original_request(app, method, url, body, headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate("async()=>{window.testStatCalls=0;const response=await fetch('/api/__test__/metadata-cache');return {status:response.status,data:await response.json(),calls:window.testStatCalls};}")
    assert result['status']==200 and result['data']=={'ok':True}
    assert result['calls']<20,'Repeated file checks must not cross the storage bridge every time.'


def test_immediate_deletion_order_guard_filter_and_recovery(static_browser,tmp_path):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if str(url)=='/api/__test__/seed-deletion':
        for ident,name in [('11111111-1111-4111-8111-111111111111','Delete me'),('22222222-2222-4222-8222-222222222222','Protected deck')]:
            app.store.put('decks',{'id':ident,'name':name,'status':'draft','summary':{'cards':0,'faces':0,'rendered':0}})
        deck='22222222-2222-4222-8222-222222222222'
        for ident,decks in [('33333333-3333-4333-8333-333333333333',[{'id':deck,'name':'Protected deck'}]),('44444444-4444-4444-8444-444444444444',[{'id':'other','name':'Other deck'}])]:
            app.store.put('orders',{'id':ident,'decks':decks,'cards':[],'count':0})
            (app.store.home/'orders'/(ident+'.zip')).write_bytes(b'zip')
        return {'status':200,'mime':'application/json','body':b'{}','headers':{}}
    if str(url)=='/api/decks':
        return {'status':200,'mime':'application/json','body':json.dumps(app.store.list('decks')).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    page.evaluate("async()=>{await fetch('/api/__test__/seed-deletion');await (await import('/site/app.js')).route();}")
    page.evaluate("""async()=>{
      const ui=await import('/site/ui.js');const deletion=await import('/site/deletion.js');
      window.backgroundTask=ui.work.begin({label:'Generate unrelated deck',resources:['deck:99999999-9999-4999-8999-999999999999'],background:true});
      const target=ui.state.decks.find(deck=>deck.name==='Delete me');
      window.targetGeneration=ui.work.begin({label:'Generate deleted deck',kind:'generation',resources:['deck:'+target.id]});
      targetGeneration.controller.signal.addEventListener('abort',()=>setTimeout(()=>ui.work.finish(targetGeneration),100),{once:true});
      const original=window.fetch;window.testFetch=original;window.journalKey='pf-pending-deck-deletions:'+ui.state.bootstrap.workspaceId;window.releaseDelete=null;
      window.fetch=async(url,options)=>{
        if(String(url).endsWith('/delete')){await new Promise(resolve=>window.releaseDelete=resolve);}
        return original(url,options);
      };
      window.deleteTask=deletion.deleteDeck(ui.state.decks.find(deck=>deck.name==='Delete me'));
    }""")
    page.get_by_role('button',name='Delete permanently',exact=True).click()
    page.wait_for_function("location.hash==='#decks'&&window.releaseDelete!==null")
    assert page.evaluate('targetGeneration.controller.signal.aborted')
    assert not page.evaluate('backgroundTask.controller.signal.aborted')
    page.get_by_role('heading',name='Deck library',exact=True).wait_for()
    assert not page.get_by_text('Delete me',exact=True).count()
    assert page.get_by_text('Protected deck',exact=True).count()
    assert page.evaluate("Object.keys(JSON.parse(localStorage.getItem(window.journalKey))).length")==1
    page.screenshot(path=str(tmp_path/'immediate-deletion.png'),full_page=True)
    page.evaluate('window.releaseDelete()')
    page.wait_for_function("localStorage.getItem(window.journalKey)==='{}'")
    assert page.evaluate("import('/site/ui.js').then(ui=>ui.state.busy)")
    #A late failure restores the deck to the visible library.
    page.evaluate("""async()=>{
      const ui=await import('/site/ui.js'),deletion=await import('/site/deletion.js');
      const original=window.fetch;window.fetch=async(url,options)=>String(url).endsWith('/delete')?Promise.reject(new Error('Injected deletion failure')):original(url,options);
      await ui.api('/api/__test__/seed-deletion');await (await import('/site/app.js')).route();
      window.deleteTask=deletion.deleteDeck(ui.state.decks.find(deck=>deck.name==='Delete me'));
    }""")
    page.get_by_role('button',name='Delete permanently',exact=True).click()
    page.get_by_text('Delete me',exact=True).wait_for()
    page.get_by_text('Deck could not be deleted: Injected deletion failure',exact=True).wait_for()
    page.evaluate("""async()=>{
      const ui=await import('/site/ui.js');window.deleteTask=(await import('/site/deletion.js')).deleteDeck(ui.state.decks.find(deck=>deck.name==='Protected deck'));
    }""")
    page.get_by_text('A print order uses this deck. Delete the print order before deleting this deck.',exact=True).wait_for()
    page.get_by_role('button',name='Show print orders').click()
    page.get_by_role('heading',name='Print orders',exact=True).wait_for()
    assert page.locator('.order-row').count()==1
    assert not page.get_by_text('Other deck',exact=True).count()
    page.evaluate("document.querySelectorAll('.toast').forEach(item=>item.remove())")
    page.screenshot(path=str(tmp_path/'filtered-orders.png'),full_page=True)
    page.get_by_text('Show all print orders',exact=True).click()
    page.wait_for_function("document.querySelectorAll('.order-row').length===2")
    page.evaluate("location.hash='orders/22222222-2222-4222-8222-222222222222'")
    page.wait_for_function("document.querySelectorAll('.order-row').length===1")
    page.evaluate("window.fetch=window.testFetch")
    page.get_by_role('button',name='Review',exact=True).click()
    page.get_by_role('heading',name='Saved order preview',exact=True).wait_for()
    page.get_by_role('button',name='Close dialog').click()
    page.get_by_role('button',name='Delete print order',exact=True).click()
    page.get_by_role('button',name='Delete print order',exact=True).last.click()
    page.get_by_text('No print orders use this deck.',exact=True).wait_for()
    assert page.evaluate("async()=>{const ui=await import('/site/ui.js');return (await ui.api('/api/decks/22222222-2222-4222-8222-222222222222/orders')).length}")==0
    #Pending deletion persists through reload; boot resends it idempotently.
    page.evaluate("""async()=>{
      const ui=await import('/site/ui.js');ui.work.finish(window.backgroundTask);await ui.api('/api/__test__/seed-deletion');
      const deck=(await ui.api('/api/decks')).find(deck=>deck.name==='Delete me');
      localStorage.setItem(window.journalKey,JSON.stringify({[deck.id]:{revision:deck.revision}}));
      location.hash='decks';
    }""")
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    page.evaluate("async()=>{window.journalKey='pf-pending-deck-deletions:'+(await import('/site/ui.js')).state.bootstrap.workspaceId;}")
    page.wait_for_function("localStorage.getItem(window.journalKey)==='{}'")
    assert not page.get_by_text('Delete me',exact=True).count()
    diagnostic_bytes=page.evaluate("""async()=>{
      const ui=await import('/site/ui.js');ui.toast('Diagnostic notification example');
      await ui.attempt(()=>{throw new Error('Diagnostic caught error example');});
      return [...new Uint8Array(await (await (await import('/site/diagnostics.js')).diagnosticZipRequest(ui.state.csrf)).arrayBuffer())];
    }""")
    import io,json,zipfile
    with zipfile.ZipFile(io.BytesIO(bytes(diagnostic_bytes))) as archive:
        report=json.loads(archive.read('browser-diagnostics.json'))
        assert any(e['detail']=='Diagnostic notification example' for e in report['entries'])
        assert any(e['kind']=='caught error' and 'Diagnostic caught error example' in e['detail'] for e in report['entries'])
        assert 'app.log' in archive.namelist()
    page.close()



def test_native_png_save_benchmark_preserves_bytes_and_survives_reload(static_browser,tmp_path):
    """Compare the previous re-encode path with validated native PNG persistence."""
    import io,json
    from PIL import Image
    directory,context,origin=static_browser
    review=ROOT/'test-results/supernatural-full-art/syr_gwyn_hero_of_ashvale_review.png'
    if review.is_file():
        with Image.open(review) as image:canvas=image.crop((2011,0,4021,2814))
    else:canvas=Image.effect_noise((2010,2814),100).convert('RGBA')
    raw=io.BytesIO();canvas.save(raw,'PNG',compress_level=1)
    (directory/'benchmark.png').write_bytes(raw.getvalue())
    worker=directory/'web/engine-worker.js'
    filesystem=directory/'web/workspace-fs.js'
    filesystem.write_text(filesystem.read_text(encoding='utf-8').replace('const query=new URLSearchParams',
        'if(values.buffer)self.referenceWrites=(self.referenceWrites||0)+1;\n        const query=new URLSearchParams'),encoding='utf-8')
    bootstrap=directory/'web/bootstrap.js'
    bootstrap.write_text(bootstrap.read_text(encoding='utf-8').replace('const pending=new Map();','window.testInputBuffers=files.inputBuffers;\n  const pending=new Map();'),encoding='utf-8')
    injection="""
original_request = request
def request(app, method, url, body, headers):
    if str(url).startswith('/api/__test__/save-benchmark/'):
        from foundry.images import ingest_image
        import time, hashlib
        mode=str(url).rsplit('/',1)[1]
        started=time.perf_counter()
        target={'key':hashlib.sha256((mode+str(time.time())).encode()).hexdigest(),'name':'Benchmark '+mode}
        if mode=='old':
            asset=ingest_image(app.store,body)
            result=app.store.render_put(target['key'],asset,face_name=target['name'])
        else:result=app.ws.save_render(target,body,[2010,2814])
        saved=app.store.asset_path(result['asset_id']).read_bytes()
        response={'seconds':time.perf_counter()-started,'asset':result['asset_id'],'sameBytes':saved==body,'size':len(saved)}
        return {'status':200,'mime':'application/json','body':json.dumps(response).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
"""
    source=worker.read_text(encoding='utf-8').replace('def browser_request(method, url, body, headers):',injection+'\ndef browser_request(method, url, body, headers):')
    source=source.replace("if(method==='POST')await mount.syncfs();", "if(method==='POST')await mount.syncfs();\n    if(url.startsWith('/api/__test__/save-benchmark/')){const result=JSON.parse(responseBody);result.referenceWrites=self.referenceWrites||0;responseBody=JSON.stringify(result);}")
    worker.write_text(source,encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    results=page.evaluate("""async()=>{
      const png=await (await fetch('/benchmark.png')).blob(),rows=[];
      for(const mode of ['old','new','old','new']){
        const started=performance.now();
        const response=await fetch('/api/__test__/save-benchmark/'+mode,{method:'POST',headers:{'Content-Type':'image/png'},body:png});
        const result=await response.json();if(!response.ok)throw new Error(JSON.stringify(result));
        rows.push({mode,...result,totalSeconds:(performance.now()-started)/1000});
      }
      return rows;
    }""")
    assert all(row['sameBytes'] for row in results if row['mode']=='new')
    assert all(not row['sameBytes'] for row in results if row['mode']=='old')
    assert results[0]['referenceWrites']==0
    assert results[1]['referenceWrites']>=1
    assert page.evaluate('window.testInputBuffers.size')==0
    failed=page.evaluate("""async()=>{
      const png=await (await fetch('/benchmark.png')).blob();
      const response=await fetch('/api/__test__/save-benchmark/new',{method:'POST',headers:{'Content-Type':'image/png'},body:png.slice(0,png.size-32)});
      await response.text();
      return {ok:response.ok,buffers:window.testInputBuffers.size};
    }""")
    assert failed=={'ok':False,'buffers':0}
    asset=results[-1]['asset']
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    restored=page.evaluate("""async asset=>{
      const raw=await (await fetch('/api/assets/'+asset)).arrayBuffer();
      const digest=await crypto.subtle.digest('SHA-256',raw);
      return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
    }""",asset)
    import hashlib
    assert restored==hashlib.sha256(raw.getvalue()).hexdigest()
    evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
    (evidence/'render-save-benchmark.json').write_text(json.dumps({'bytes':len(raw.getvalue()),'source':'Syr Gwyn review render' if review.is_file() else 'high-detail texture','runs':results},indent=2),encoding='utf-8')


@pytest.mark.parametrize('failure',['fail','pause'])
def test_render_checkpoint_failure_after_write_restores_previous_image_on_reload(static_browser,failure):
    import io
    from PIL import Image
    directory,context,origin=static_browser
    for name,color in [('first','blue'),('second','red')]:
        raw=io.BytesIO();Image.new('RGBA',(40,56),color).save(raw,'PNG')
        (directory/(name+'.png')).write_bytes(raw.getvalue())
    worker=directory/'web/engine-worker.js'
    injected="""
original_request=request
test_deck=None
def request(app,method,url,body,headers):
    global test_deck
    if str(url).startswith('/api/__test__/atomic-save/'):
        if test_deck is None:test_deck=app.ws.new_deck('Atomic save')['id']
        mode=str(url).rsplit('/',1)[-1]
        original_persist=app.store.persist
        calls=[]
        def persist(path):
            calls.append(path)
            if mode=='pause' and len(calls)==1:
                import time
                time.sleep(20)
            original_persist(path)
            if mode=='fail' and len(calls)==1:raise OSError('Injected checkpoint after acceptance')
        app.store.persist=persist
        try:
            target={'key':('a' if mode=='seed' else 'b')*64,'name':'Card','deckId':test_deck,'faceId':'face'}
            result=app.ws.save_render(target,body,[40,56])
            result['checkpoints']=len(calls)
        finally:app.store.persist=original_persist
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    if str(url)=='/api/__test__/atomic-state':
        return {'status':200,'mime':'application/json','body':json.dumps({'old':app.store.render_get('a'*64),'new':app.store.render_get('b'*64)}).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
"""
    worker.write_text(worker.read_text(encoding='utf-8').replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    seeded=page.evaluate("""async()=>{const png=await (await fetch('/first.png')).blob();return (await (await fetch('/api/__test__/atomic-save/seed',{method:'POST',headers:{'Content-Type':'image/png'},body:png})).json());}""")
    assert seeded['checkpoints']==1
    if failure=='fail':
        error=page.evaluate("""async()=>{const png=await (await fetch('/second.png')).blob();const response=await fetch('/api/__test__/atomic-save/fail',{method:'POST',headers:{'Content-Type':'image/png'},body:png});return {ok:response.ok,text:await response.text()};}""")
        assert not error['ok'] and 'checkpoint after acceptance' in error['text']
    else:
        page.evaluate("""()=>{window.pendingSave=fetch('/second.png').then(response=>response.blob()).then(png=>fetch('/api/__test__/atomic-save/pause',{method:'POST',headers:{'Content-Type':'image/png'},body:png}));}""")
        import time
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            files=page.evaluate("""async path=>{let folder=await navigator.storage.getDirectory();for(const part of path.split('/').slice(0,-1))folder=await folder.getDirectoryHandle(part);const names=[];for await(const name of folder.keys())if(name.endsWith('.png'))names.push(name);return names;}""",seeded['file_path'])
            if len(files)>=2:break
            time.sleep(.05)
        else:raise AssertionError('No replacement file was committed before the checkpoint.')
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    state=page.evaluate("async()=> (await (await fetch('/api/__test__/atomic-state')).json())")
    assert state['old']['asset_id']==seeded['asset_id'] and state['new'] is None
    matches=page.evaluate("""async path=>{const root=await navigator.storage.getDirectory();let handle=root;const parts=path.split('/');for(const part of parts.slice(0,-1))handle=await handle.getDirectoryHandle(part);const file=await (await handle.getFileHandle(parts.at(-1))).getFile();const actual=await file.arrayBuffer(),expected=await (await fetch('/first.png')).arrayBuffer();return [...new Uint8Array(actual)].join(',')===[...new Uint8Array(expected)].join(',');}""",seeded['file_path'])
    assert matches



def test_repeated_database_reads_keep_browser_heap_bounded(static_browser):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js'
    worker.write_text(worker.read_text(encoding='utf-8').replace('initialized=true;','self.testPython=python;initialized=true;'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded')
    page.locator('#import-deck').wait_for(timeout=90000)
    engine=next(worker for worker in page.workers if 'engine-worker' in worker.url)
    def reads():
        engine.evaluate("()=>testPython.runPython('for index in range(2000):app.store.list(\"settings\")')")
        return engine.evaluate('testPython._module.HEAPU8.byteLength')
    warmed=reads();later=reads()
    assert later-warmed<=32*1024*1024,{'warmHeap':warmed,'laterHeap':later}
    mode=engine.evaluate('(code)=>testPython.runPython(code)', 'with app.store.connect() as db:mode=db.execute("PRAGMA journal_mode").fetchone()[0]\nmode')
    assert mode=='delete'
    import json
    evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
    (evidence/'database-read-heap.json').write_text(json.dumps({'warmHeap':warmed,'laterHeap':later,'reads':4000,'journal':mode},indent=2),encoding='utf-8')
