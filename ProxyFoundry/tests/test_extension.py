"""Real MV3 extension and local ZIP transfer; the merchant page is a fixture.
No login, real order, checkout or payment is performed by this test.
"""
import io,json,os,random,threading,hashlib
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in real MV3 browser test')
ROOT=Path(__file__).resolve().parents[1]
MERCHANT='''<!doctype html><html><body><h1>TCG editor fixture</h1><div id="counter">0 Cards</div>
<label>Upload Front<input id="front" type="file" accept="image/*"></label>
<label>Upload Deck ZIP<input id="zip" type="file" accept="application/zip,.zip"></label>
<button id="next-back">Next — Customize Back</button><button id="next-preview" hidden>Next — Preview</button><button id="checkout">Checkout</button>
<script>
window.tc={count:0,sha:null,preview:0,checkout:0};
document.querySelector('#zip').onchange=async e=>{
 const data=await e.target.files[0].arrayBuffer();const digest=await crypto.subtle.digest('SHA-256',data);
 tc.sha=Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('');tc.count=2;
 document.querySelector('#counter').textContent='2 Cards';
};
document.querySelector('#next-back').onclick=()=>document.querySelector('#next-preview').hidden=false;
document.querySelector('#next-preview').onclick=()=>tc.preview++;
document.querySelector('#checkout').onclick=()=>tc.checkout++;
</script></body></html>'''
def test_installed_extension_transfers_exact_zip_to_new_tab(tmp_path):
    from playwright.sync_api import sync_playwright,expect
    s=Store(tmp_path/'workspace')
    sf={'id':'11111111-1111-4111-8111-111111111111','name':'Fixture Elf','layout':'normal','type_line':'Creature — Elf','mana_cost':'{G}','colors':['G'],'power':'1','toughness':'1','rarity':'common','oracle_text':'Vigilance','artist':'Fixture Artist','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/x.jpg'}}
    small=io.BytesIO();Image.new('RGB',(900,650),'#336699').save(small,'PNG')
    def transport(url):return (json.dumps(sf).encode(),'application/json',{}) if 'api.scryfall.com' in url else (small.getvalue(),'image/png',{})
    app=App(s,Network(s,transport=transport));server=LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    art=ingest_image(s,small.getvalue());symbols=rarity_variants(s,art['id'])
    d=app.ws.create({'name':'Extension test','source':[{'id':sf['id'],'quantity':2}],'settings':{'symbols':symbols,'backAsset':art['id']}});d=app.ws.prepare(d['id'])
    raw=io.BytesIO();Image.frombytes('RGB',(600,840),random.Random(7).randbytes(600*840*3)).save(raw,'PNG')
    render=ingest_image(s,raw.getvalue());s.render_put(d['cards'][0]['faces'][0]['compiled']['renderKey'],render)
    order=app.orders.build([d['id']],True);expected=hashlib.sha256((s.home/'orders'/(order['id']+'.zip')).read_bytes()).hexdigest()
    assert order['zipBytes']>2*1024**2
    with sync_playwright() as p:
        ext=str(ROOT/'extension')
        ctx=p.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'],**({'executable_path':os.environ['PF_BROWSER_EXECUTABLE']} if os.environ.get('PF_BROWSER_EXECUTABLE') else {}))
        ctx.route('https://www.tcgplaytest.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=MERCHANT))
        page=ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(server.origin+'/#orders')
            expect(page.locator('#helper-state b')).to_have_text('connected',timeout=15000)
            with ctx.expect_page() as opened:page.locator('[data-open-order]').first.click()
            merchant=opened.value;merchant.wait_for_url('https://www.tcgplaytest.com/**')
            expect(merchant.locator('#pph-line')).to_contain_text('Uploaded 2 paired cards',timeout=45000)
            assert merchant.evaluate('tc.sha')==expected
            assert merchant.evaluate('tc.preview===1&&tc.checkout===0')
            assert not page.is_closed() and page.url.startswith(server.origin)
            assert 'secret' not in merchant.url
            unauthorized=ctx.new_page();unauthorized.goto('https://www.tcgplaytest.com/?view=design&proxyFoundryOrder=unauthorized')
            expect(unauthorized.locator('#pph-line')).to_contain_text('FAILED',timeout=15000)
            assert unauthorized.evaluate('tc.sha===null&&tc.checkout===0')
            (ROOT/'test-results').mkdir(exist_ok=True);merchant.screenshot(path=str(ROOT/'test-results/extension-paired-transfer.png'))
        finally:ctx.close();server.shutdown();server.server_close();app.close()


BATCH_MERCHANT = '''<!doctype html><html><body><h1>TCG batch importer fixture</h1><div id="counter">0 Cards</div>
<label>Upload Front<input id="front" type="file" accept="image/*"></label>
<label>Upload Deck ZIP<input id="zip" type="file" accept="application/zip,.zip"></label>
<button id="next-back">Next — Customize Back</button><button id="next-preview" hidden>Next — Preview</button><button id="checkout">Checkout</button>
<script>
window.tc={count:0,uploads:[],preview:0,checkout:0,busy:false,overlap:0};
const hash=async raw=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),x=>x.toString(16).padStart(2,'0')).join('');
document.querySelector('#zip').onchange=async e=>{
 if(tc.busy)tc.overlap++;
 tc.busy=true;
 const raw=await e.target.files[0].arrayBuffer(),view=new DataView(raw),names=[],hashes={};let offset=0;
 while(view.getUint32(offset,true)===0x04034b50){
   const size=view.getUint32(offset+18,true),len=view.getUint16(offset+26,true),extra=view.getUint16(offset+28,true);
   const name=new TextDecoder().decode(new Uint8Array(raw,offset+30,len));
   const dataStart=offset+30+len+extra;names.push(name);hashes[name]=await hash(raw.slice(dataStart,dataStart+size));
   offset=dataStart+size;
 }
 tc.uploads.push({names,hashes,bytes:raw.byteLength});
 const busy=document.createElement('div');busy.textContent='Processing card';document.body.append(busy);
 await new Promise(resolve=>setTimeout(resolve,600));
 tc.count+=names.filter(n=>n.startsWith('FRONT/')).length;document.querySelector('#counter').textContent=tc.count+' Cards';
 busy.remove();tc.busy=false;
};
document.querySelector('#next-back').onclick=()=>document.querySelector('#next-preview').hidden=false;
document.querySelector('#next-preview').onclick=()=>tc.preview++;
document.querySelector('#checkout').onclick=()=>tc.checkout++;
</script></body></html>'''


def test_installed_extension_streams_multiple_complete_zips(tmp_path,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from foundry.domain import uid
    from foundry import transfer_zip
    from test_transfer_zip import make_zip
    s=Store(tmp_path/'workspace');app=App(s);server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    ident=uid();path=s.home/'orders'/(ident+'.zip');payloads=make_zip(path,5)
    original_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    s.put('orders',{'id':ident,'count':5,'cards':[],'decks':[{'name':'Batched order','id':uid()}]})
    monkeypatch.setattr(transfer_zip,'BATCH_LIMIT_BYTES',1000)
    with sync_playwright() as p:
        ext=str(ROOT/'extension')
        ctx=p.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'],**({'executable_path':os.environ['PF_BROWSER_EXECUTABLE']} if os.environ.get('PF_BROWSER_EXECUTABLE') else {}))
        ctx.route('https://www.tcgplaytest.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=BATCH_MERCHANT))
        page=ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(server.origin+'/#orders')
            expect(page.locator('#helper-state b')).to_have_text('connected',timeout=15000)
            with ctx.expect_page() as opened:page.locator('[data-open-order]').first.click()
            merchant=opened.value;merchant.wait_for_url('https://www.tcgplaytest.com/**')
            expect(merchant.locator('#pph-line')).to_contain_text('Uploaded 5 paired cards in 3 ZIP batches',timeout=45000)
            tc=merchant.evaluate('tc')
            assert tc['count']==5 and len(tc['uploads'])==3 and tc['overlap']==0
            assert [name for b in tc['uploads'] for name in b['names']]==list(payloads)
            for batch in tc['uploads']:
                assert batch['bytes']<=1000
                for name,digest in batch['hashes'].items():assert digest==hashlib.sha256(payloads[name]).hexdigest()
            assert tc['preview']==1 and tc['checkout']==0
            assert merchant.locator('#zip').evaluate('(el)=>el.files.length')==0
            assert not page.is_closed() and hashlib.sha256(path.read_bytes()).hexdigest()==original_hash
        finally:ctx.close();server.shutdown();server.server_close();app.close()
