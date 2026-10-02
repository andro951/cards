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

def build_site(tmp_path,base_path='/'):
    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py'),'--base-path',base_path,'--output',str(tmp_path/'built')],cwd=ROOT,check=True,capture_output=True)

def copy_site(tmp_path):
    import shutil
    site=tmp_path/'site';shutil.copytree(tmp_path/'built',site)
    return site


def test_static_engine_releases_image_responses_and_error_diagnostics(tmp_path):
    """Exercise real Pyodide proxy lifetimes without rendering a whole deck."""
    from playwright.sync_api import sync_playwright
    import shutil

    build_site(tmp_path)
    shutil.copytree(tmp_path/'built',tmp_path/'site')
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
    if str(url)=='/api/__test__/large-json':return {'status':200,'mime':'application/json','body':json.dumps({'value':'é🔥'*250000}).encode(),'headers':{}}
    if str(url)=='/api/__test__/malformed-json':return {'status':200,'mime':'application/json','body':b'broken{','headers':{}}
    if str(url).startswith('/api/__test__/image'):
        return {'status':200,'mime':'image/png','body':bytes([int(str(url).split('=')[1])])*1024*1024,'headers':{}}
    return original_request(app, method, url, body, headers)
'''
    source=source.replace('def browser_request(method, url, body, headers):',tracking+'\ndef browser_request(method, url, body, headers):')
    source=source.replace("const encoded=response.toJs({dict_converter:Object.fromEntries});","if(url==='/api/__test__/large-json')python.runPython('heap_probe=bytearray(128*1024*1024)');const encoded=response.toJs({dict_converter:Object.fromEntries});")
    source=source.replace("if(method==='POST')await mount.syncfs();","metadata.headers['X-Test-Body-Type']=typeof responseBody;if(method==='POST')await mount.syncfs();")
    source=source.replace('if(Uint8Array.fromBase64)return','if(false&&Uint8Array.fromBase64)return')
    source=source.replace('last_response = request(app, str(method), str(url), buffer_bytes(body), dict(headers.to_py()))',
                          "last_response = TrackedResponse(request(app, str(method), str(url), buffer_bytes(body), dict(headers.to_py())))\n    last_response['headers']['X-Test-Live'] = str(live_responses)\n    if str(url) == '/api/__test__/fail':\n        raise ValueError('Injected request failure')")
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
                large=page.evaluate('''async()=>{
                  const rows=[];
                  for(let i=0;i<8;i++){
                    const response=await fetch('/api/__test__/large-json',{method:i%2?'POST':'GET'});
                    const data=await response.json();rows.push({type:response.headers.get('X-Test-Body-Type'),length:data.value.length,start:data.value.slice(0,3)});
                  }
                  const broken=await fetch('/api/__test__/malformed-json');
                  return {rows,broken:{status:broken.status,error:(await broken.json()).error}};
                }''')
                assert large['rows']==[{'type':'string','length':750000,'start':'é🔥'}]*8
                assert large['broken']['status']==500 and 'Invalid engine JSON' in large['broken']['error']
                assert len(result)==120
                for i,row in enumerate(result):
                    assert row=={'live':'1','status':200,'length':1024*1024,'first':i,'last':i},row
                page.get_by_role('link',name='Settings',exact=True).click()
                page.get_by_role('button',name='Download Diagnostics',exact=True).wait_for(timeout=30000)
                #Simulate the unreadable HTTP response after generation, with no API available.
                page.evaluate('''async()=>{
                  const ui=await import((window.__pfBasePath||'')+'/site/ui.js');
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


@pytest.mark.skipif(os.environ.get('PF_HEAP_BOUNDARY')!='1',reason='Opt-in browser heap above 2 GiB')
def test_static_engine_high_address_binary_uploads_files_and_ascii_json(tmp_path):
    """Cross the signed-pointer boundary with real Pyodide and browser files."""
    from playwright.sync_api import sync_playwright
    build_site(tmp_path);site=copy_site(tmp_path)
    worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if not str(url).startswith('/api/__test__/boundary/'):
        return original_request(app,method,url,body,headers)
    import hashlib
    global boundary_blocks, boundary_parent
    if 'boundary_blocks' not in globals():
        boundary_blocks=[bytearray(20*1024*1024) for index in range(110)]
        boundary_parent=bytes(range(256))*(20*4096)
    kind=str(url).rsplit('/',1)[-1]
    if kind=='binary':
        raw=memoryview(boundary_parent)[-1024*1024:]
        return {'status':200,'mime':'application/octet-stream','body':raw,
            'headers':{'X-Expected':hashlib.sha256(raw).hexdigest(),'X-Test-Address':str(id(boundary_parent)),'X-Test-Metadata':'x'*(20*1024*1024)}}
    if kind=='files':
        original=app.store.home/'tmp'/'boundary.bin';saved=original.with_suffix('.renamed')
        original.write_bytes(boundary_parent);original.replace(saved)
        result={'expected':hashlib.sha256(boundary_parent).hexdigest(),
            'actual':hashlib.sha256(saved.read_bytes()).hexdigest(),'bytes':saved.stat().st_size}
        saved.unlink()
    elif kind=='input':
        result={'bytes':len(body),'hash':hashlib.sha256(body).hexdigest()}
    elif kind=='job':
        text='x'*(20*1024*1024)
        publishJob('\u0100'+json.dumps({'id':'11111111-1111-4111-8111-111111111111','kind':'test','state':'running','message':'High-address event','done':0,'total':1,'probe':text}))
        result={'address':id(text)}
    elif kind=='ascii':
        text='x'*(20*1024*1024)
        return {'status':200,'mime':'application/json','body':json.dumps({'value':text}).encode(),
            'headers':{'X-Test-Address':str(id(text))}}
    else:raise ValueError('Unknown boundary probe')
    return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
"""
    source=source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):')
    worker.write_text(source,encoding='utf-8')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True);page=browser.new_page()
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                result=page.evaluate("""async()=>{
                  const hash=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
                  const binary=await fetch('/api/__test__/boundary/binary');
                  const bytes=await binary.arrayBuffer();
                  const files=await (await fetch('/api/__test__/boundary/files')).json();
                  const payload=new Uint8Array(20*1024*1024);
                  for(let i=0;i<payload.length;i++)payload[i]=i%256;
                  const ui=await import('/site/ui.js');
                  const input=await ui.blobRequest('/api/__test__/boundary/input',payload,'application/octet-stream');
                  const event=await (await fetch('/api/__test__/boundary/job')).json();
                  const job=await (await fetch('/api/jobs/11111111-1111-4111-8111-111111111111')).json();
                  const ascii=await fetch('/api/__test__/boundary/ascii'),data=await ascii.json();
                  return {binary:{status:binary.status,address:Number(binary.headers.get('X-Test-Address')),bytes:bytes.byteLength,expected:binary.headers.get('X-Expected'),actual:await hash(bytes),metadata:binary.headers.get('X-Test-Metadata')==='x'.repeat(20*1024*1024)},
                    files,input:{...input,expected:await hash(payload)},event:{address:event.address,matches:job.probe==='x'.repeat(20*1024*1024)},ascii:{address:Number(ascii.headers.get('X-Test-Address')),matches:data.value==='x'.repeat(20*1024*1024)}};
                }""")
                assert result['binary']['status']==200 and result['binary']['address']>2**31,result
                assert result['binary']['bytes']==1024*1024 and result['binary']['actual']==result['binary']['expected'] and result['binary']['metadata'],result
                assert result['files']['bytes']==20*1024*1024 and result['files']['actual']==result['files']['expected'],result
                assert result['input']['bytes']==20*1024*1024 and result['input']['hash']==result['input']['expected'],result
                assert result['event']['address']>2**31 and result['event']['matches'],result
                assert result['ascii']['address']>2**31 and result['ascii']['matches'],result
                #Keep the high-address allocations live through a real metadata/art/frame/render cycle.
                page.click('#import-deck');page.locator('.modal-body summary').click()
                page.locator('.modal-body textarea').fill('1 Command Tower')
                page.click('#do-import');page.get_by_role('button',name='Normal Look',exact=True).click(timeout=90000)
                page.locator('#save-setup').wait_for(timeout=90000)
                page.click('#generate-deck')
                page.wait_for_function("() => document.querySelector('.badge.ready') || document.querySelector('.toast.error')",timeout=180000)
                failure=page.locator('.toast.error').all_text_contents()
                data=page.evaluate("async()=>{const ui=await import('/site/ui.js');return ui.api('/api/decks/'+ui.state.activeDeck.id);}")
                assert data['status']=='ready' and data['summary']['rendered']==1,failure
                page.get_by_role('button',name='View deck',exact=True).click()
                page.wait_for_function("()=>document.querySelector('.card-grid img')?.naturalWidth>0",timeout=90000)
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.screenshot(path=str(evidence/'high-address-native-render.png'),full_page=True)
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_token_styles_and_upstream_assets(tmp_path):
    from playwright.sync_api import sync_playwright
    build_site(tmp_path)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(copy_site(tmp_path))))
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


def test_static_website_fetches_pinned_station_script(tmp_path):
    from playwright.sync_api import sync_playwright

    build_site(tmp_path)
    with zipfile.ZipFile(tmp_path/'built'/'web'/'runtime.zip') as archive:
        assert 'vendor/cardconjurer/versionStation.js' not in archive.namelist()
        assert "ingest.MAIN_TYPES.add('Emblem')" in archive.read('foundry/legacy.py').decode()
        assert "ingest.MAIN_TYPES.add('Card')" in archive.read('foundry/legacy.py').decode()
        assert 'def build_emblem_data(' in archive.read('foundry/compiler.py').decode()
        assert 'def build_art_series_data(' in archive.read('foundry/compiler.py').decode()
        assert "pt.setdefault('text','')" in archive.read('foundry/compiler.py').decode()
        assert 'def build_station_land_data(' in archive.read('foundry/compiler.py').decode()
        assert "'helper_scan' if group=='helper'" in archive.read('foundry/compiler.py').decode()
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(copy_site(tmp_path)))
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


def test_static_website_prepare_frames_load_from_pinned_fallback(tmp_path):
    from playwright.sync_api import sync_playwright

    build_site(tmp_path)
    assert '<body hidden>' in (tmp_path/'built'/'index.html').read_text(encoding='utf-8')
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(copy_site(tmp_path)))
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


@pytest.mark.parametrize(('look','base_path'),[('Normal Look','/'),('Customize Look','/'),('Normal Look','/cards/')])
def test_static_website_import_frame_review_and_zip(tmp_path,look,base_path):
    from playwright.sync_api import sync_playwright

    build_site(tmp_path,base_path)
    import shutil
    deployed=tmp_path/'deployed';deployed.mkdir()
    shutil.copytree(tmp_path/'built',deployed/base_path.strip('/') if base_path!='/' else deployed,dirs_exist_ok=True)
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(deployed))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin=f'http://127.0.0.1:{server.server_port}'+base_path
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            page=context.new_page();errors=[];generation=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:generation.append(request.url) if request.method=='POST' and ('/prepare' in request.url or '/render-sessions' in request.url) else None)
            try:
                page.goto(origin,wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                assert page.locator('#deck-search').evaluate('(input)=>parseFloat(getComputedStyle(input).paddingLeft)')>=33
                if look=='Normal Look':
                    page.evaluate("async()=>{const ui=await import((window.__pfBasePath||'')+'/site/ui.js');await ui.api('/api/settings',{defaults:{artist:'Inherited artist',disableAutofit:true,showFlavorText:false,allCardsTokens:true,tokenOptions:{power:'7',toughness:'7'},templateRules:{standard:'land',land:'land'}}});}")
                page.click('#import-deck')
                page.locator('.modal-body summary').click()
                page.locator('.modal-body textarea').fill('1 Syr Gwyn, Hero of Ashvale')
                page.click('#do-import')
                page.get_by_role('button',name=look,exact=True).click(timeout=90000)
                page.locator('#save-setup').wait_for(timeout=90000)
                if look=='Normal Look':
                    normal=page.evaluate("async()=>{const ui=await import((window.__pfBasePath||'')+'/site/ui.js');return (await ui.api('/api/decks/'+ui.state.activeDeck.id)).settings;}")
                    assert normal['source']['mode']=='scryfall' and normal['artist']==''
                    assert not normal['disableAutofit'] and not normal['allCardsTokens'] and normal['showFlavorText']
                    assert normal['templateRules']['land']=='normal' and not normal['tokenOptions']['power']
                data={'version':1,'cards':[{'name':'Syr Gwyn, Hero of Ashvale',
                                            'nickname':'Test Commander Nickname'}]}
                page.locator('#data-json-file').set_input_files({
                    'name':'data.json','mimeType':'application/json',
                    'buffer':json.dumps(data).encode()})
                page.locator('#activity').wait_for(state='hidden',timeout=180000)
                page.click('[data-frame-group=legendary]')
                page.locator('#modal-host img:visible').first.wait_for(timeout=240000)
                page.locator('#activity').wait_for(state='hidden',timeout=240000)
                sources=page.locator('#modal-host img:visible').evaluate_all('(images)=>images.map(image=>image.getAttribute("src"))')
                assert len(sources)>=3 and len(set(sources))==1,'Picker samples must be static shared card backs.'
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.screenshot(path=str(evidence/'static-frame-picker.png'))
                page.locator('#modal-host button[aria-label="Select Godzilla full art · non-land"]').click()
                page.click('#save-setup')
                page.get_by_text('Deck setup saved.').wait_for(timeout=30000)
                assert not generation,'Setup must not generate images: '+repr(generation)
                page.click('#generate-deck')
                page.locator('.badge.ready').wait_for(timeout=180000)
                page.get_by_role('dialog',name='Your deck is ready').wait_for(timeout=30000)
                page.get_by_role('button',name='View deck').click()
                assert page.locator('#card-search').evaluate('(input)=>parseFloat(getComputedStyle(input).paddingLeft)')>=33
                page.screenshot(path=str(evidence/'ready-deck-search.png'))
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
                diagnostic_bytes=page.evaluate("async()=>[...new Uint8Array(await (await fetch((window.__pfBasePath||'')+'/api/diagnostics.zip')).arrayBuffer())]")
                import io
                with zipfile.ZipFile(io.BytesIO(bytes(diagnostic_bytes))) as diagnostics:
                    log=diagnostics.read('app.log').decode('utf-8')
                    assert 'TIMING ' in log and 'render.native' in log and 'network.fetch' in log and 'native.png-export' in log
                page.reload(wait_until='domcontentloaded')
                page.get_by_text('New deck',exact=True).first.wait_for(timeout=90000)
                assert not errors,errors
            finally:
                context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_browser_job_progress_cancellation_and_reload(tmp_path):
    from playwright.sync_api import sync_playwright
    import shutil
    build_site(tmp_path)
    shutil.copytree(tmp_path/'built',tmp_path/'site')
    worker=tmp_path/'site/web/engine-worker.js'
    source=worker.read_text()
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if str(url) == '/api/__test__/slow-job':
        import time
        def operation(update, cancel):
            for i in range(40):
                if cancel():raise ValueError('Cancelled at checkpoint')
                time.sleep(.1)
                update(i+1,40,'Saved item '+str(i+1))
            return {'saved':40}
        result=app.jobs.start('Slow browser test',operation)
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_request(app, method, url, body, headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(tmp_path/'site')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True);page=browser.new_page()
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                result=page.evaluate("""async()=>{
                  const ui=await import((window.__pfBasePath||'')+'/site/ui.js');
                  const {id}=await ui.api('/api/__test__/slow-job',{});
                  const rows=[];
                  for(let i=0;i<100;i++){
                    const job=await ui.api('/api/jobs/'+id);rows.push({state:job.state,done:job.done});
                    if(job.state==='running'&&job.done>=2)await ui.api('/api/jobs/'+id+'/cancel',{});
                    if(['done','cancelled','failed'].includes(job.state))return {id,job,rows};
                    await new Promise(resolve=>setTimeout(resolve,50));
                  }
                  throw new Error('Browser job never finished');
                }""")
                assert any(row['state']=='running' and 0<row['done']<40 for row in result['rows'])
                assert result['job']['state']=='cancelled' and result['job']['done']<40
                page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
                previous=page.evaluate("async id=>(await fetch('/api/jobs/'+id)).json()",result['id'])
                assert previous['state']=='cancelled' and previous['done']==result['job']['done']
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_static_template_editor_generates_only_on_request_and_saves_validated_model(tmp_path):
    from playwright.sync_api import sync_playwright
    build_site(tmp_path)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(copy_site(tmp_path))))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                generated=[]
                page.on('request',lambda request:generated.append(request.url) if request.method=='POST' and '/render-sessions' in request.url else None)
                page.get_by_role('link',name='Templates',exact=True).click()
                page.get_by_role('button',name='Use as starting point').first.click()
                page.get_by_role('dialog',name='Create Template').wait_for(timeout=30000)
                assert not generated
                page.get_by_label('Template name',exact=True).fill('Validated browser template')
                page.get_by_label('Legendary cards',exact=True).check()
                page.get_by_label('This frame supports legendary cards').check()
                page.click('#preview-template')
                page.locator('#save-template:enabled').wait_for(timeout=240000)
                assert page.get_by_label('Template validation sample').locator('option').count()==2
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.get_by_label('Template validation sample').scroll_into_view_if_needed()
                page.screenshot(path=str(evidence/'validated-template-editor.png'),full_page=True)
                page.click('#save-template')
                page.get_by_text('Validated browser template',exact=True).wait_for(timeout=30000)
                saved=page.evaluate("async()=>{const templates=await (await fetch('/api/templates')).json();return templates.find(template=>template.name==='Validated browser template');}")
                assert saved['schemaVersion']==3 and set(saved['groups'])=={'standard','legendary'}
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


@pytest.mark.skipif(os.environ.get('PF_DECK_STRESS')!='1',reason='Affected full-deck browser rendering stress run')
def test_published_deck_100_image_browser_generation_and_reload(tmp_path):
    from playwright.sync_api import sync_playwright
    build_site(tmp_path)
    #Repeat actual imported printings with fresh face identities to exercise 100 uncached outputs.
    #The injection exists only in this isolated test build, never in the distribution.
    import shutil
    site=tmp_path/'site';shutil.copytree(tmp_path/'built',site)
    worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_request = request
def request(app, method, url, body, headers):
    if str(url).startswith('/api/__test__/expand-deck/'):
        import copy
        from foundry.domain import uid
        deck=app.ws.deck(str(url).rsplit('/',1)[-1]);original=deck['cards'];cards=[]
        for index in range(100):
            card=copy.deepcopy(original[index%len(original)]);card['id']=uid();card['quantity']=1
            for face in card['faces']:
                face['id']=uid()
                for key in ('compiled','lastRender','error'):face.pop(key,None)
            cards.append(card)
        deck['cards']=cards;deck['status']='draft';app.store.put('decks',deck,deck['revision'])
        return {'status':200,'mime':'application/json','body':b'{"ok":true}','headers':{}}
    return original_request(app, method, url, body, headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            context=playwright.chromium.launch_persistent_context(str(tmp_path/'profile'),headless=True,viewport={'width':1440,'height':1000});page=context.pages[0]
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                page.click('#import-deck');page.get_by_role('textbox',name='Deck link',exact=True).fill('https://scryfall.com/@andro951/decks/e18f48e7-a2b7-479e-8361-de947bc734ff')
                page.click('#do-import');page.get_by_role('button',name='Normal Look',exact=True).click()
                page.locator('#save-setup').wait_for(timeout=180000)
                original=page.evaluate("async()=>{const ui=await import((window.__pfBasePath||'')+'/site/ui.js');return ui.api('/api/decks/'+ui.state.activeDeck.id);}")
                assert original['cards'] and any(card['name']=='Syr Gwyn, Hero of Ashvale' for card in original['cards'])
                page.evaluate("async()=>{const ui=await import((window.__pfBasePath||'')+'/site/ui.js');await ui.api('/api/__test__/expand-deck/'+ui.state.activeDeck.id,{});}")
                page.reload(wait_until='domcontentloaded');page.locator('#generate-deck').wait_for(timeout=90000)
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.on('console',lambda message:print('Browser console: '+message.text,flush=True) if message.type=='error' else None)
                def capture(response):
                    if '/api/decks/' not in response.url or response.request.method!='GET':return
                    raw=b''
                    try:
                        raw=response.body();json.loads(raw)
                    except Exception as error:
                        (evidence/'full-deck-invalid-response.json').write_text(json.dumps({'url':response.url,'status':response.status,'error':str(error),'length':len(raw),'raw':raw.decode('utf-8',errors='replace')},indent=2),encoding='utf-8')
                page.on('response',capture)
                saved=[]
                def progress(response):
                    if response.request.method=='POST' and '/api/render-sessions/' in response.url and response.status==200:
                        saved.append(response.url)
                        if len(saved)%10==0:print('Full deck: '+str(len(saved))+' rendered images saved',flush=True)
                page.on('response',progress)
                page.click('#generate-deck')
                page.wait_for_function("() => document.querySelector('.badge.ready') || document.querySelector('.toast.error')",timeout=3600000)
                failure=page.locator('.toast.error').all_text_contents()
                (evidence/'full-deck-browser-terminal.json').write_text(json.dumps({'toasts':failure,'saved':len(saved),'browser':page.evaluate("()=>JSON.parse(localStorage.getItem('bulk-proxy-forge-browser-diagnostics'))")},indent=2),encoding='utf-8')
                data=page.evaluate("async()=>{const ui=await import((window.__pfBasePath||'')+'/site/ui.js');return ui.api('/api/decks/'+ui.state.activeDeck.id);}")
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                (evidence/'full-deck-browser-diagnostics.json').write_text(json.dumps({'toasts':failure,'saved':len(saved),'storage':page.evaluate('()=>navigator.storage.estimate()'),'browser':page.evaluate("()=>JSON.parse(localStorage.getItem('bulk-proxy-forge-browser-diagnostics'))")},indent=2),encoding='utf-8')
                assert data['status']=='ready',{'toasts':failure,'saved':len(saved),'faces':[(card['name'],face.get('error')) for card in data['cards'] for face in card['faces'] if face.get('error')]}
                assert data['summary']['faces']>=100 and data['summary']['rendered']==data['summary']['faces']
                assert len(saved)==100 and len({face['compiled']['renderKey'] for card in data['cards'] for face in card['faces']})==100
                page.get_by_role('button',name='View deck',exact=True).click()
                evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
                page.locator('.card-grid img').first.wait_for(timeout=90000)
                page.wait_for_function("()=>[...document.querySelectorAll('.card-grid img')].slice(0,4).every(image=>image.complete&&image.naturalWidth>0)",timeout=90000)
                page.screenshot(path=str(evidence/'full-deck-browser-grid.png'),full_page=True)
                report={'deckId':data['id'],'summary':data['summary'],'saved':len(saved),'storage':page.evaluate('()=>navigator.storage.estimate()')}
                (evidence/'full-deck-browser-summary.json').write_text(json.dumps(report,indent=2))
                page.reload(wait_until='domcontentloaded');page.locator('.badge.ready').wait_for(timeout=90000)
                previous=page.evaluate("async()=>{const ui=await import((window.__pfBasePath||'')+'/site/ui.js');return ui.api('/api/decks/'+ui.state.activeDeck.id);}")
                assert previous['summary']['rendered']==data['summary']['rendered']
            finally:context.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)



def test_static_cardconjurer_source_choices_are_immediate_without_generation(tmp_path):
    from playwright.sync_api import sync_playwright
    build_site(tmp_path)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(copy_site(tmp_path))))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.locator('#import-deck').wait_for(timeout=90000)
                entries=page.evaluate("async()=>{const cards=[];for(const kind of ['normal','land'])cards.push(await (await fetch('/api/templates/seed?kind='+kind)).json());return cards;}")
                generated=[];page.on('request',lambda request:generated.append(request.url) if request.method=='POST' and '/render-sessions' in request.url else None)
                page.get_by_role('link',name='Templates',exact=True).click()
                with page.expect_file_chooser() as chooser:
                    page.get_by_role('button',name='Import Card Conjurer File',exact=True).click()
                chooser.value.set_files({'name':'cards.cardconjurer','mimeType':'application/json','buffer':json.dumps(entries).encode()})
                page.get_by_role('dialog',name='Choose a source card').wait_for(timeout=30000)
                assert not generated
                images=page.locator('.modal-body .printing-option img').evaluate_all('(images)=>images.map(image=>image.src)')
                assert len(images)==2 and len(set(images))==1
                page.get_by_label('Card layout',exact=True).select_option('land')
                page.locator('.modal-body .printing-option').nth(1).click()
                page.get_by_role('dialog',name='Create Template').wait_for(timeout=30000)
                assert page.get_by_label('Base layout',exact=True).input_value()=='land'
                assert not generated
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)



def test_mixed_website_engine_version_stops_with_saved_workspace_guidance(tmp_path):
    from playwright.sync_api import sync_playwright
    build_site(tmp_path)
    site=copy_site(tmp_path);worker=site/'web/engine-worker.js'
    worker.write_text(worker.read_text(encoding='utf-8').replace("self.postMessage({type:'ready',buildId});","self.postMessage({type:'ready',buildId:'older-build'});"),encoding='utf-8')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True);page=browser.new_page()
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
                page.get_by_text('The website and card engine are different versions.',exact=False).wait_for(timeout=90000)
                assert not page.locator('#import-deck').is_visible()
                assert page.get_by_role('button',name='Download browser diagnostics').is_visible()
                error=page.evaluate("async()=>{const response=await fetch('/api/settings');return {status:response.status,data:await response.json()};}")
                assert error['status']==500 and 'saved decks stay' in error['data']['error']
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
