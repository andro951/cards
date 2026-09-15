"""Actual shipped content-script in a controlled browser DOM, not live checkout.

Chrome messaging is a fixture. The activation query is explicit because this test
uses about:blank; all ZIP transfer, choice, deletion and upload code is unmodified.
"""
import base64
import io
import os
import zipfile
from pathlib import Path
import pytest
from PIL import Image
pytestmark=pytest.mark.skipif(not (os.environ.get('PF_DOM')=='1' or os.environ.get('PF_BROWSER')=='1'),reason='Opt-in Chromium component tests')
ROOT=Path(__file__).resolve().parents[1]
def fixture_zip():
    b=io.BytesIO();im=io.BytesIO();Image.new('RGB',(20,28),'#773355').save(im,'PNG')
    with zipfile.ZipFile(b,'w') as z:
        for i in (1,2):
            z.writestr(f'FRONT/{i:06d}.png',im.getvalue());z.writestr(f'BACK/{i:06d}.png',im.getvalue())
    return b.getvalue()
@pytest.fixture
def bridge_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        executable=os.environ.get('PF_BROWSER_EXECUTABLE')
        if not executable and os.environ.get('PF_DOM')=='1':executable='/usr/bin/chromium'
        browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
        page=browser.new_page(viewport={'width':1280,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        yield page,errors
        browser.close()
def start(page,existing=0,bad_chunk=False):
    data=fixture_zip()
    page.set_content('''<!doctype html><html><body>
      <h1>Card editor</h1><div id="counter">0 Cards</div>
      <section><label>Upload Front<input id="front" type="file" accept="image/*"></label></section>
      <section><label>Upload Deck ZIP<input id="zip" type="file" accept="application/zip,.zip"></label></section>
      <div id="cards"></div>
      <button id="next-back">Next — Customize Back</button>
      <button id="next-preview" style="display:none">Next — Preview</button>
      <button id="checkout">Checkout</button>
      <style>button{min-width:30px;min-height:30px} [data-card-index]{width:100px;height:140px;display:inline-block;margin:8px;background:#ddd} [role=dialog]{position:fixed;left:400px;top:250px;background:white;padding:30px}</style>
      </body></html>''')
    page.evaluate('''({count,b64,bad})=>{
      const raw=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
      window.tc={count,deleted:0,uploaded:null,finished:0,preview:0,checkout:0};
      function draw(){
        document.querySelector('#counter').textContent=tc.count+' Cards';
        const cards=document.querySelector('#cards');cards.replaceChildren();
        for(let i=0;i<tc.count;i++){
          const div=document.createElement('div');div.dataset.cardIndex=i;
          const button=document.createElement('button');button.textContent='×';button.setAttribute('aria-label','Remove card');
          button.onclick=()=>{
            const dialog=document.createElement('div');dialog.setAttribute('role','dialog');dialog.innerHTML='<h2>Delete this card?</h2><p>Card will be removed from this deck.</p><button class="keep">Keep card</button><button class="delete">Delete card</button>';
            dialog.querySelector('.keep').onclick=()=>dialog.remove();
            dialog.querySelector('.delete').onclick=()=>{tc.count--;tc.deleted++;dialog.remove();draw();};
            document.body.append(dialog);
          };div.append(button);cards.append(div);
        }
      }draw();
      document.querySelector('#zip').onchange=async e=>{
        tc.uploaded=[...new Uint8Array(await e.target.files[0].arrayBuffer())];tc.count+=2;draw();
        const busy=document.createElement('div');busy.textContent='Processing card';document.body.append(busy);setTimeout(()=>busy.remove(),500);
      };
      document.querySelector('#next-back').onclick=()=>{document.querySelector('#next-preview').style.display='block';};
      document.querySelector('#next-preview').onclick=()=>tc.preview++;
      document.querySelector('#checkout').onclick=()=>tc.checkout++;
      window.chrome={runtime:{sendMessage:async msg=>{
        if(msg.type==='PF_ORDER_METADATA')return {ok:true,count:2,zipBytes:raw.length,filename:'Paired.zip'};
        if(msg.type==='PF_ORDER_CHUNK')return {ok:true,offset:bad?99:msg.offset,total:raw.length,length:raw.length,base64:b64};
        if(msg.type==='PF_ORDER_FINISHED'){tc.finished++;return {ok:true};}
        throw new Error('Unexpected message '+msg.type);
      }}};
    }''',{'count':existing,'b64':base64.b64encode(data).decode(),'bad':bad_chunk})
    script=(ROOT/'extension/bridge.js').read_text()
    assert script.count('new URLSearchParams(location.search)')==1
    script=script.replace('new URLSearchParams(location.search)',"new URLSearchParams('?proxyFoundryOrder=fixture')")
    page.add_script_tag(content=script)
    return data
@pytest.mark.parametrize('existing,action,expected,deleted',[(0,None,2,0),(2,'add',4,0),(2,'replace',2,2)])
def test_paired_zip_empty_add_replace(bridge_page,existing,action,expected,deleted):
    from playwright.sync_api import expect
    page,errors=bridge_page;data=start(page,existing)
    if action:
        page.locator('#pph-'+action).wait_for()
        assert page.evaluate('tc.uploaded===null&&tc.deleted===0'),'Mutation before user choice'
        page.click('#pph-'+action)
    expect(page.locator('#pph-line')).to_contain_text('Uploaded 2 paired cards',timeout=25000)
    result=page.evaluate('tc')
    assert bytes(result['uploaded'])==data
    assert result['count']==expected and result['deleted']==deleted
    assert result['preview']==1 and result['checkout']==0 and result['finished']==1
    assert not errors,errors
def test_close_before_choice_does_not_upload_or_delete(bridge_page):
    page,errors=bridge_page;start(page,2);page.locator('#pph-replace').wait_for();page.click('#pph-close');page.wait_for_timeout(1000)
    assert page.evaluate('tc.uploaded===null&&tc.deleted===0&&tc.checkout===0')
    assert page.locator('#proxy-print-helper-status').count()==0
    assert not errors,errors
def test_corrupt_chunk_stops_before_upload(bridge_page):
    from playwright.sync_api import expect
    page,errors=bridge_page;start(page,0,bad_chunk=True)
    expect(page.locator('#pph-line')).to_contain_text('FAILED',timeout=15000)
    assert page.evaluate('tc.uploaded===null&&tc.deleted===0&&tc.checkout===0')
    assert not errors,errors
