"""Real Edge extension and cross-origin native File handoff; no live printer uploads."""
import functools
import hashlib
import http.server
import os
from pathlib import Path
import threading

import pytest
from test_print_bridge import fixture_zip,ROOT

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Real extension native-file handoff')


@pytest.mark.parametrize('scenario',['small','large','add','replace','cancel','unavailable'])
def test_real_extension_uploads_one_unchanged_native_file_without_chunks(tmp_path,scenario):
    from playwright.sync_api import sync_playwright,expect
    large=scenario=='large'
    existing=2 if scenario in {'add','replace','cancel','unavailable'} else 0
    if large:
        setting=os.environ.get('PF_NATIVE_REAL_FILE')
        if not setting:pytest.skip('Set PF_NATIVE_REAL_FILE for a read-only multi-GB saved order test.')
        source=Path(setting);assert source.stat().st_size>2**32
        count=1110
    else:
        source=tmp_path/'paired.zip';source.write_bytes(fixture_zip());count=2
    size=source.stat().st_size
    offsets=[0,size-32]+([2429384400] if large else [])
    with source.open('rb') as f:
        samples=[]
        for offset in offsets:f.seek(offset);samples.append(list(f.read(32)))
    original=source.stat()
    directory=tmp_path/'site';directory.mkdir()
    (directory/'native-print.js').write_bytes((ROOT/'site/native-print.js').read_bytes())
    (directory/'index.html').write_text('''<!doctype html><meta name="proxy-foundry" content="workspace-v1">
    <input type="file" id="file"><button id="start">Print Cards</button><p id="status"></p>
    <script type="module">
    import {openNativePrint} from './native-print.js';
    const id='c19329f1-200c-4ba4-b06c-bb1ed4af9af8',secret='native_test_secret_12345678901234567890';
    window.addEventListener('message',event=>{
      const d=event.data;
      if(event.source!==window||event.origin!==location.origin||d?.type!=='PF_TRANSFER_REQUEST')return;
      if(d.kind!=='metadata')throw Error('ZIP bytes must never use extension messages');
      window.postMessage({source:'proxy-foundry-workspace',type:'PF_TRANSFER_REPLY',requestId:d.requestId,
        ok:true,data:{count:CARD_COUNT,zipBytes:document.querySelector('#file').files[0].size,protocolVersion:3,filename:'Paired.zip'}},location.origin);
    });
    document.querySelector('#start').onclick=async()=>{
      try{
        await openNativePrint({
          createTransfer:async()=>({id,secret,origin:location.origin}),
          getFile:async()=>{window.fileRequests=(window.fileRequests||0)+1;FILE_ERROR return document.querySelector('#file').files[0];},
          register:transfer=>new Promise((resolve,reject)=>{
            const requestId=crypto.randomUUID();
            const listener=e=>{
              if(e.source!==window||e.data?.source!=='proxy-foundry-helper'||e.data.requestId!==requestId)return;
              if(e.data.type==='PF_WORKSPACE_OPENED'){window.removeEventListener('message',listener);resolve(e.data);}
              if(e.data.type==='PF_WORKSPACE_ERROR'){window.removeEventListener('message',listener);reject(Error(e.data.error));}
            };
            window.addEventListener('message',listener);
            window.postMessage({source:'proxy-foundry-workspace',type:'PF_WORKSPACE_OPEN',requestId,transfer},location.origin);
          })
        });document.querySelector('#status').textContent='Connected';
      }catch(e){document.querySelector('#status').textContent=e.stack;}
    };
    </script>'''.replace('CARD_COUNT',str(count)).replace('FILE_ERROR',"throw Error('Saved order changed');" if scenario=='unavailable' else ''),encoding='utf-8')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(directory)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    target='''<!doctype html><html><meta charset="utf-8"><body><h1>Fixture printer</h1><div id="counter">EXISTING Cards</div>
    <label>Upload Front<input type="file" accept="image/*"></label>
    <label>Upload Deck ZIP<input id="zip" type="file" accept=".zip"></label>
    <button id="clear">Clear all cards</button><button id="preview">Next Preview</button><button id="checkout">Checkout</button>
    <script>
    window.tc={uploads:0,preview:0,checkout:0,cleared:0,count:EXISTING};
    document.querySelector('#clear').onclick=()=>{tc.cleared++;tc.count=0;document.querySelector('#counter').textContent='0 Cards';};
    document.querySelector('#preview').onclick=()=>tc.preview++;
    document.querySelector('#checkout').onclick=()=>tc.checkout++;
    document.querySelector('#zip').onchange=async e=>{
      const file=e.target.files[0];tc.uploads++;tc.bytes=file.size;tc.name=file.name;
      tc.samples=[];for(const offset of OFFSETS)tc.samples.push([...new Uint8Array(await file.slice(offset,offset+32).arrayBuffer())]);
      if(file.size<1024*1024)tc.digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))].map(b=>b.toString(16).padStart(2,'0')).join('');
      tc.count+=CARD_COUNT;document.querySelector('#counter').textContent=tc.count+' Cards';
      const busy=document.createElement('p');busy.textContent='Preparing card 1 of CARD_COUNT';document.body.append(busy);
      setTimeout(()=>busy.remove(),700);
    };
    </script></body></html>'''.replace('OFFSETS',str(offsets)).replace('CARD_COUNT',str(count)).replace('EXISTING',str(existing))
    try:
        with sync_playwright() as p:
            ext=str(ROOT/'extension')
            context=p.chromium.launch_persistent_context(str(tmp_path/'profile'),channel='msedge',headless=True,
                args=['--disable-extensions-except='+ext,'--load-extension='+ext])
            try:
                context.route('https://www.tcgplaytest.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=target))
                worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker',timeout=20000)
                page=context.new_page()
                page.add_init_script("window.addEventListener('message',e=>{if(e.source===window&&e.data?.source==='proxy-foundry-helper'&&e.data.type==='PF_WORKSPACE_PONG')window.helperReady=e.data;})")
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.wait_for_function("window.helperReady?.capabilities.includes('native-whole-zip')")
                page.locator('#file').set_input_files(str(source))
                with page.expect_popup() as popup:page.click('#start')
                printer=popup.value
                expect(page.locator('#status')).to_have_text('Connected',timeout=20000)
                if scenario=='unavailable':
                    expect(printer.locator('#pph-line')).to_contain_text('Saved order changed',timeout=15000)
                    assert printer.evaluate('tc.uploads===0&&tc.cleared===0&&tc.count===2&&tc.checkout===0')
                    return
                if existing:
                    printer.locator('#pph-add').wait_for(state='visible',timeout=15000)
                    assert printer.evaluate('tc.uploads===0&&tc.cleared===0')
                    if scenario=='cancel':
                        printer.locator('#pph-close').click()
                        assert printer.evaluate('tc.uploads===0&&tc.cleared===0&&tc.checkout===0')
                        return
                    printer.locator('#pph-'+scenario).click()
                expect(printer.locator('#pph-line')).to_contain_text(f'Uploaded {count} paired cards',timeout=25000)
                result=printer.evaluate('tc')
                assert result['uploads']==1 and result['bytes']==size and result['samples']==samples
                assert result['name']==source.name and result['checkout']==0
                if not large:assert result['digest']==hashlib.sha256(source.read_bytes()).hexdigest()
                assert result['cleared']==int(scenario=='replace')
                assert result['count']==count+(existing if scenario=='add' else 0)
                assert page.evaluate('fileRequests')==1
                assert printer.evaluate("document.querySelector('#zip').files.length")==0
                #A direct transfer has no chunk payloads and finishes its session.
                assert worker.evaluate('async()=>Object.keys(await chrome.storage.session.get(null)).filter(k=>k.startsWith("transfer:")||k.startsWith("pending:")).length')==0
            finally:context.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    assert source.stat().st_size==original.st_size and source.stat().st_mtime_ns==original.st_mtime_ns
