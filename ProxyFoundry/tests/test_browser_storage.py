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
def static_browser(tmp_path):
    from playwright.sync_api import sync_playwright
    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py'),'--output',str(tmp_path/'built')],cwd=ROOT,check=True,capture_output=True)
    directory=tmp_path/'site';shutil.copytree(tmp_path/'built',directory)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(directory)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True);context=browser.new_context()
        yield directory,context,f'http://127.0.0.1:{server.server_port}'
        context.close();browser.close()
    server.shutdown();server.server_close();thread.join(timeout=5)


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
    first.evaluate("async()=>{const ui=await import('/site/ui.js');await ui.api('/api/decks/new',{name:'Saved once'});}")
    second=context.new_page();second.goto(origin,wait_until='domcontentloaded')
    second.get_by_role('button',name='Retry opening workspace').wait_for(timeout=15000)
    assert not second.locator('#import-deck').is_visible()
    first.close();second.get_by_role('button',name='Retry opening workspace').click()
    second.get_by_text('Saved once',exact=True).wait_for(timeout=90000)


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
    source=source.replace("const metadata=response.toJs({dict_converter:Object.fromEntries});", "const metadata=response.toJs({dict_converter:Object.fromEntries});\n    if(url.startsWith('/api/__test__/storage')){\n      const node=python.FS.lookupPath('/workspace/tmp/storage-stress/80.bin').node;\n      metadata.headers['X-Test-Cached-Bytes']=String(node.contents?.byteLength||node.contents?.length||0);\n    }")
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
    assert saved['job']['state']=='failed' and 'interrupted' in saved['job']['error']
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
    assert result['failed']['status']==500 and result['failed']['body']['error']
    assert result['retry']=={'width':120,'height':160} and result['bytes']>0
    page.get_by_role('link',name='Settings',exact=True).click()
    page.get_by_role('button',name='Download Diagnostics',exact=True).wait_for(timeout=30000)
    entries=page.evaluate("async()=>{const diagnostics=await import('/site/diagnostics.js');return JSON.parse(localStorage.getItem('bulk-proxy-forge-browser-diagnostics'));}")
    assert any('QuotaExceededError' in row['detail'] for row in entries['entries'])



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
