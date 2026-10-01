"""Production static-site flow in Chromium; no local application server."""
import functools
import http.server
import json
import os
import subprocess
import threading
import zipfile
from pathlib import Path

import pytest


pytestmark=pytest.mark.skipif(
    os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',
    reason='Opt-in complete Chromium website render',
)
ROOT=Path(__file__).resolve().parents[1]


def test_static_engine_releases_image_responses_and_error_diagnostics(tmp_path):
    """Exercise real Pyodide proxy lifetimes without rendering a whole deck."""
    from playwright.sync_api import sync_playwright
    import shutil

    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py')],cwd=ROOT,check=True,capture_output=True)
    shutil.copytree(ROOT/'dist',tmp_path/'site')
    worker=tmp_path/'site/web/engine-worker.js'
    source=worker.read_text(encoding='utf-8')
    tracking='''
live_responses = 0
class TrackedResponse(dict):
    def __init__(self, value):
        global live_responses
        super().__init__(value)
        live_responses += 1
    def __del__(self):
        global live_responses
        live_responses -= 1
original_request = request
def request(app, method, url, body, headers):
    if str(url).startswith('/api/__test__/image'):
        return {'status':200,'mime':'image/png','body':bytes([int(str(url).split('=')[1])])*1024*1024,'headers':{}}
    return original_request(app, method, url, body, headers)
'''
    source=source.replace('def browser_request(method, url, body, headers):',tracking+'\ndef browser_request(method, url, body, headers):')
    source=source.replace('last_response = request(app, str(method), str(url), bytes(body.to_py()), dict(headers.to_py()))',
                          "last_response = TrackedResponse(request(app, str(method), str(url), bytes(body.to_py()), dict(headers.to_py())))\n    last_response['headers']['X-Test-Live'] = str(live_responses)\n    if str(url) == '/api/__test__/fail':\n        raise ValueError('Injected request failure')")
    source=source.replace('self.onmessage=event=>{',"self.onmessage=event=>{\n  if(event.data.url==='/api/__test__/crash')throw new Error('Injected engine crash');")
    source=source.replace('global last_response',"global last_response\n    if str(url) == '/api/__test__/early-fail':\n        raise ValueError('Injected early failure')")
    worker.write_text(source,encoding='utf-8')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(tmp_path/'site')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context(accept_downloads=True)
            page=context.new_page()
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                result=page.evaluate('''async()=>{
                  const rows=[];
                  const early=await fetch('/api/__test__/early-fail');
                  if(early.status!==500||(await early.json()).error.indexOf('Injected early failure')<0)
                    throw new Error('Expected a readable early failure');
                  for(let i=0;i<120;i++){
                    const response=await fetch('/api/__test__/image?value='+i);
                    const bytes=new Uint8Array(await response.arrayBuffer());
                    rows.push({live:response.headers.get('X-Test-Live'),status:response.status,
                      length:bytes.length,first:bytes[0],last:bytes[bytes.length-1]});
                    if(i===80){
                      const failed=await fetch('/api/__test__/fail');
                      if(failed.status!==500||(await failed.json()).error.indexOf('Injected request failure')<0)
                        throw new Error('Expected a readable engine error');
                    }
                  }
                  return rows;
                }''')
                assert len(result)==120
                for i,row in enumerate(result):
                    assert row=={'live':'1','status':200,'length':1024*1024,'first':i,'last':i},row
                page.get_by_role('link',name='Settings',exact=True).click()
                page.get_by_role('button',name='Download Diagnostics',exact=True).wait_for(timeout=30000)
                #Simulate the unreadable HTTP response after generation, with no API available.
                page.evaluate('''async()=>{
                  const ui=await import('/site/ui.js');
                  window.testOriginalFetch=window.fetch;
                  window.fetch=async()=>new Response('<html>Unavailable</html>',{status:503,headers:{'Content-Type':'text/html'}});
                  try{await ui.api('/api/settings');}
                  catch(error){ui.showWorkspaceError(error);}
                }''')
                assert page.get_by_text('HTTP 503',exact=False).is_visible()
                with page.expect_download() as download:
                    page.get_by_role('button',name='Download browser diagnostics',exact=True).click()
                report=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
                assert report['engineStatus']=='Ready'
                assert any('/api/settings: HTTP 503' in row['detail'] for row in report['entries'])
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.screenshot(path=str(evidence/'workspace-error-diagnostics.png'))
                crash=page.evaluate('''async()=>{
                  window.fetch=window.testOriginalFetch;
                  const crashed=await fetch('/api/__test__/crash');
                  const after=await fetch('/api/settings');
                  return {status:crashed.status,error:(await crashed.json()).error,
                    afterStatus:after.status,afterError:(await after.json()).error};
                }''')
                assert crash['status']==crash['afterStatus']==500
                assert 'Injected engine crash' in crash['error']
                assert 'Injected engine crash' in crash['afterError']
            finally:context.close();browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_token_styles_and_upstream_assets():
    from playwright.sync_api import sync_playwright
    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py')],cwd=ROOT,check=True,capture_output=True)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'dist')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page()
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                result=page.evaluate('''async()=>{
                  const styles=['token-classic','token-full-art','token-borderless'];
                  const templates=await (await fetch('/api/templates')).json();
                  const seeds=[];
                  for(const style of styles){
                    const seed=await (await fetch('/api/templates/seed?kind='+style)).json();
                    const paths=[...new Set(seed.frames.flatMap(frame=>[frame.src,...(frame.masks||[]).map(mask=>mask.src)]))];
                    const assets=[];
                    for(const path of paths){
                      const response=await fetch(path);const bytes=await response.arrayBuffer();
                      assets.push({path,status:response.status,size:bytes.byteLength});
                    }
                    seeds.push({style,version:seed.version,text:seed.text.rules.text,assets});
                  }
                  return {templates,seeds};
                }''')
                assert {row['id'] for row in result['templates']} >= {'token-classic','token-full-art','token-borderless'}
                assert [row['version'] for row in result['seeds']]==['tokenTextlessM15','tokenTextless','tokenTextlessBorderless']
                for seed in result['seeds']:
                    assert seed['text']=='Flying'
                    assert all(asset['status']==200 and asset['size']>0 for asset in seed['assets']),seed
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_website_fetches_pinned_station_script():
    from playwright.sync_api import sync_playwright

    subprocess.run([os.environ.get('PYTHON',os.sys.executable),str(ROOT/'scripts'/'build_web.py')],
                   cwd=ROOT,check=True,capture_output=True)
    with zipfile.ZipFile(ROOT/'dist'/'web'/'runtime.zip') as archive:
        assert 'vendor/cardconjurer/versionStation.js' not in archive.namelist()
        assert "ingest.MAIN_TYPES.add('Emblem')" in archive.read('foundry/legacy.py').decode()
        assert "ingest.MAIN_TYPES.add('Card')" in archive.read('foundry/legacy.py').decode()
        assert 'def build_emblem_data(' in archive.read('foundry/compiler.py').decode()
        assert 'def build_art_series_data(' in archive.read('foundry/compiler.py').decode()
        assert "pt.setdefault('text','')" in archive.read('foundry/compiler.py').decode()
        assert 'def build_station_land_data(' in archive.read('foundry/compiler.py').decode()
        assert "'helper_scan' if group=='helper'" in archive.read('foundry/compiler.py').decode()
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'dist'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context()
            page=context.new_page()
            page.route('https://cardconjurer.app/**',lambda route:route.abort())
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                result=page.evaluate('''async()=>{
                  const response=await fetch('/js/frames/versionStation.js');
                  return {status:response.status,source:await response.text()};
                }''')
                assert result['status']==200,result['source'][:300]
                assert 'object[key] = value' in result['source']
                assert 'eval(`${target} = value`);' not in result['source']
            finally:
                context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_website_prepare_frames_load_from_pinned_fallback():
    from playwright.sync_api import sync_playwright

    subprocess.run([os.environ.get('PYTHON',os.sys.executable),str(ROOT/'scripts'/'build_web.py')],
                   cwd=ROOT,check=True,capture_output=True)
    assert '<body hidden>' in (ROOT/'dist'/'index.html').read_text(encoding='utf-8')
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'dist'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1280,'height':800})
            page=context.new_page()
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#browser-startup').wait_for(timeout=15000)
                assert page.locator('.app-shell').is_hidden()
                assert page.locator('.sidebar').is_hidden()
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.screenshot(path=str(evidence/'website-startup.png'))
                page.locator('#import-deck').wait_for(timeout=90000)
                assert page.locator('#browser-startup').count()==0
                assert page.locator('.sidebar').is_hidden()
                paths=['b.png','u.png','m.png','a.png','pinline.png','prepare.png','preparePinline.png','rules.png','frame.png']
                results=page.evaluate('''async names=>{
                  const output=[];
                  for(const name of names){
                    const response=await fetch('/img/frames/prepare/regular/'+name);
                    const bytes=new Uint8Array(await response.arrayBuffer());
                    output.push({name,status:response.status,signature:[...bytes.slice(0,8)]});
                  }
                  return output;
                }''',paths)
                assert all(row['status']==200 and row['signature']==[137,80,78,71,13,10,26,10] for row in results),results
            finally:
                context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_website_import_frame_review_and_zip(tmp_path):
    from playwright.sync_api import sync_playwright

    subprocess.run([os.environ.get('PYTHON',os.sys.executable),str(ROOT/'scripts'/'build_web.py')],
                   cwd=ROOT,check=True,capture_output=True)
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'dist'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                page.goto(origin,wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                page.click('#import-deck')
                page.locator('.modal-body summary').click()
                page.locator('.modal-body textarea').fill('1 Syr Gwyn, Hero of Ashvale')
                page.click('#do-import')
                page.get_by_role('button',name='Customize Look').click(timeout=90000)
                page.locator('#save-setup').wait_for(timeout=90000)
                data={'version':1,'cards':[{'name':'Syr Gwyn, Hero of Ashvale',
                                            'nickname':'Test Commander Nickname'}]}
                page.locator('#data-json-file').set_input_files({
                    'name':'data.json','mimeType':'application/json',
                    'buffer':json.dumps(data).encode()})
                page.locator('#activity').wait_for(state='hidden',timeout=180000)
                page.click('[data-frame-group=legendary]')
                page.locator('#modal-host img:visible').first.wait_for(timeout=240000)
                page.locator('#activity').wait_for(state='hidden',timeout=240000)
                hashes=page.locator('#modal-host img:visible').evaluate_all('''async images=>Promise.all(images.map(async image=>{
                  const bytes=await (await fetch(image.src)).arrayBuffer();
                  const hash=await crypto.subtle.digest('SHA-256',bytes);
                  return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
                }))''')
                assert len(set(hashes))>=3,'The frame picker repeated the same card image.'
                page.locator('#modal-host button[aria-label="Select Godzilla full art · non-land"]').click()
                page.click('#save-setup')
                page.get_by_text('Deck setup saved.').wait_for(timeout=30000)
                page.click('#generate-deck')
                page.locator('.badge.ready').wait_for(timeout=180000)
                page.get_by_role('dialog',name='Your deck is ready').wait_for(timeout=30000)
                page.get_by_role('button',name='View deck').click()
                page.get_by_role('button',name='Review & Print').click()
                page.click('#order-plan')
                page.locator('#browser-pair-grid').wait_for(timeout=90000)
                page.get_by_role('button',name='Review card').click()
                page.get_by_role('button',name='It Looks Fine').click()
                page.locator('.modal-body').get_by_text('Needs Review').wait_for(state='hidden',timeout=30000)
                page.get_by_role('button',name='Build paired ZIP').click()
                page.get_by_role('button',name='Print Cards').wait_for(timeout=90000)
                page.get_by_role('button',name='Print Cards').click()
                page.get_by_text('Print once').wait_for()
                page.evaluate('window.showSaveFilePicker=undefined')
                with page.expect_download() as download:
                    page.locator('#manual-zip').click()
                saved=tmp_path/'paired.zip';download.value.save_as(saved)
                with zipfile.ZipFile(saved) as archive:
                    assert archive.namelist()==['FRONT/000001.png','BACK/000001.png']
                    assert all(archive.read(name).startswith(b'\x89PNG') for name in archive.namelist())
                assert saved.stat().st_size>1024
                page.reload(wait_until='domcontentloaded')
                page.get_by_text('New deck',exact=True).first.wait_for(timeout=90000)
                assert not errors,errors
            finally:
                context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
