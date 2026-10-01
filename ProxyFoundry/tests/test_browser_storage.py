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
    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py')],cwd=ROOT,check=True,capture_output=True)
    directory=tmp_path/'site';shutil.copytree(ROOT/'dist',directory)
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
