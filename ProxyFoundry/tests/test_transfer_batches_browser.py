"""Actual MV3 helper + actual HTTP ranges; merchant DOM is a controlled fixture."""
import hashlib
import io
import os
import random
import threading
from pathlib import Path
import pytest
from PIL import Image
from foundry.domain import GENERATION_VERSION, ValidationError, uid
from foundry.images import ingest_image
from foundry.server import App, LocalServer
from foundry.storage import Store
from foundry import transfer_batches
ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.environ.get('PF_BROWSER') != '1', reason='Opt-in real MV3 transfer test')
MERCHANT = '''<!doctype html><html><body>
<h1>Paired batch editor fixture</h1><div id="counter">2 Cards</div>
<label>Upload Front<input type="file" accept="image/*"></label>
<label>Upload Deck ZIP<input id="zip" type="file" accept="application/zip,.zip"></label>
<button id="clear">Clear all cards</button>
<button id="next-back">Next — Customize Back</button><button id="next-preview" hidden>Next — Preview</button>
<button id="checkout">Checkout</button><div id="processing"></div><div id="tiles"></div>
<script>
window.tc={count:2,uploads:[],done:0,concurrent:false,processing:false,preview:0,checkout:0,cleared:0};
const draw=()=>{document.querySelector('#counter').textContent=tc.count+' Cards';
 document.querySelector('#tiles').innerHTML=tc.count?'<button aria-label="Remove card">×</button>':'';};draw();
document.querySelector('#clear').onclick=()=>{
  const d=document.createElement('dialog');d.innerHTML='<p>Clear all cards?</p><button>Confirm</button>';
  d.querySelector('button').onclick=()=>{tc.cleared++;tc.count=0;draw();d.remove();};document.body.append(d);d.showModal();
};
document.querySelector('#zip').onchange=async e=>{
  if(tc.processing)tc.concurrent=true;
  tc.processing=true;document.querySelector('#processing').textContent='Processing card';
  const file=e.target.files[0];const data=await file.arrayBuffer();const v=new DataView(data);
  let offset=0;const names=[];
  while(v.getUint32(offset,true)===0x04034b50){
    const size=v.getUint32(offset+18,true),len=v.getUint16(offset+26,true),extra=v.getUint16(offset+28,true);
    names.push(new TextDecoder().decode(new Uint8Array(data,offset+30,len)));
    offset+=30+len+extra+size;
  }
  const digest=await crypto.subtle.digest('SHA-256',data);
  tc.uploads.push({size:file.size,names,sha:Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('')});
  tc.count+=names.filter(n=>n.startsWith('FRONT/')).length;draw();
  // Counter updates before processing finishes: the next batch must still wait.
  setTimeout(()=>{tc.processing=false;tc.done++;document.querySelector('#processing').textContent='';},1700);
};
document.querySelector('#next-back').onclick=()=>document.querySelector('#next-preview').hidden=false;
document.querySelector('#next-preview').onclick=()=>tc.preview++;
document.querySelector('#checkout').onclick=()=>tc.checkout++;
</script></body></html>'''

@pytest.mark.parametrize('action,stop', [('add',None), ('replace',None), ('add','failure'), ('add','cancel')])
def test_sequential_paired_zip_batches(tmp_path, monkeypatch, action, stop):
    from playwright.sync_api import sync_playwright, expect
    store = Store(tmp_path/'workspace'); app = App(store)
    server = LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    image=io.BytesIO();Image.frombytes('RGB',(600,840),random.Random(9).randbytes(600*840*3)).save(image,'PNG')
    asset=ingest_image(store,image.getvalue());store.render_put('fixture',asset)
    entry={'id':uid(),'name':'Batch fixture','quantity':3,'faces':[{'id':uid(),'name':'Batch fixture',
           'compiled':{'renderKey':'fixture','generationVersion':GENERATION_VERSION}}]}
    deck=store.put('decks',{'name':'Batch test','status':'prepared','settings':{'backAsset':asset['id']},'cards':[entry]})
    order=app.orders.build([deck['id']],True)
    path=store.home/'orders'/(order['id']+'.zip')
    # >1 MB messages and one full pair per batch, without a multi-GB CI upload.
    monkeypatch.setattr(transfer_batches,'HELPER_ZIP_LIMIT',4*1024**2)
    batches=transfer_batches.plan_batches(path,3)
    assert len(batches)==3 and all(b.size>2*1024**2 for b in batches)
    digests=[]
    for b in batches:
        h=hashlib.sha256()
        for off in range(0,b.size,1024**2):h.update(b.read_range(off,min(1024**2,b.size-off)))
        digests.append(h.hexdigest())
    requested=[];read=transfer_batches.ZipBatch.read_range
    def instrument(batch,start,length):
        requested.append(batch.index)
        if stop=='failure' and batch.index==1:raise ValidationError('Deliberate second-batch fixture failure')
        return read(batch,start,length)
    monkeypatch.setattr(transfer_batches.ZipBatch,'read_range',instrument)
    with sync_playwright() as p:
        ext=str(ROOT/'extension');exe=os.environ.get('PF_BROWSER_EXECUTABLE')
        ctx=p.chromium.launch_persistent_context(str(tmp_path/'browser'),headless=True,channel='chromium',
              **({'executable_path':exe} if exe else {}),
              args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'])
        ctx.route('https://www.tcgplaytest.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=MERCHANT))
        page=ctx.pages[0]
        try:
            page.goto(server.origin+'/#orders')
            expect(page.locator('#helper-state b')).to_have_text('connected',timeout=15000)
            with ctx.expect_page() as opened:page.locator('[data-open-order]').first.click()
            merchant=opened.value
            merchant.locator('#pph-'+action).wait_for(timeout=15000)
            assert merchant.evaluate('tc.uploads.length===0&&tc.cleared===0')
            merchant.click('#pph-'+action)
            if stop=='cancel':
                merchant.wait_for_function('tc.uploads.length===1')
                merchant.click('#pph-close');merchant.wait_for_timeout(4000)
                assert merchant.evaluate('tc.uploads.length===1&&tc.preview===0&&tc.checkout===0')
                assert set(requested)=={0}
            elif stop=='failure':
                expect(merchant.locator('#pph-line')).to_contain_text('FAILED',timeout=30000)
                assert merchant.evaluate('tc.uploads.length===1&&tc.preview===0&&tc.checkout===0')
                assert set(requested)=={0,1}
                expect(merchant.locator('#pph-sub')).to_contain_text('1 batches (1 cards) confirmed')
            else:
                expect(merchant.locator('#pph-line')).to_contain_text('Uploaded 3 paired cards',timeout=55000)
                result=merchant.evaluate('tc')
                assert result['count']==(5 if action=='add' else 3)
                assert result['cleared']==(0 if action=='add' else 1)
                assert result['done']==3 and not result['concurrent']
                assert result['preview']==1 and result['checkout']==0
                assert [u['sha'] for u in result['uploads']]==digests
                assert [u['names'] for u in result['uploads']]==[
                    [f'FRONT/{i:06d}.png',f'BACK/{i:06d}.png'] for i in (1,2,3)]
                assert merchant.locator('#zip').evaluate('(el)=>el.files.length')==0
                assert requested==sorted(requested)
            assert not page.is_closed()
        finally:
            ctx.close();server.shutdown();server.server_close();app.close()
