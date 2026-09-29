"""Real MV3 extension and local ZIP transfer; the merchant page is a fixture.
No login, real order, checkout or payment is performed by this test.
"""
import io,json,os,random,threading,hashlib,re,time,http.server
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

@pytest.mark.skipif(os.environ.get('PF_LIVE_DECK_SITES')!='1',reason='Opt-in live public deck sites')
def test_installed_helper_fetches_public_decks_without_a_server_function(tmp_path):
    from playwright.sync_api import sync_playwright

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'<!doctype html><meta name="proxy-foundry" content="workspace-v1"><title>Helper fixture</title>'
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args):pass

    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Page)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            ext=str(ROOT/'extension')
            ctx=p.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'])
            try:
                page=ctx.pages[0] if ctx.pages else ctx.new_page()
                page.add_init_script("window.__helperConnected=false;window.addEventListener('message',event=>{if(event.data?.source==='proxy-foundry-helper'&&event.data.type==='PF_WORKSPACE_PONG')window.__helperConnected=true})")
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                page.wait_for_function('window.__helperConnected===true',timeout=15000)
                for url,site in [('https://archidekt.com/decks/21700272/cycle_of_the_five_dragon_stars','archidekt'),
                                 ('https://www.mtggoldfish.com/deck/4492960','mtggoldfish')]:
                    response=page.evaluate('''url=>new Promise((resolve,reject)=>{
                      const requestId=crypto.randomUUID();
                      const timer=setTimeout(()=>reject(new Error('Deck helper timed out')),45000);
                      const receive=event=>{
                        if(event.data?.source!=='proxy-foundry-helper'||event.data.type!=='PF_DECK_IMPORT_REPLY'||event.data.requestId!==requestId)return;
                        clearTimeout(timer);window.removeEventListener('message',receive);resolve(event.data);
                      };
                      window.addEventListener('message',receive);
                      window.postMessage({source:'proxy-foundry-workspace',type:'PF_DECK_IMPORT_REQUEST',requestId,url},location.origin);
                    })''',url)
                    assert response['ok'],response.get('error')
                    assert response['deck']['site']==site
                    assert len(response['deck']['body'])>1000
                    if site=='archidekt':assert len(json.loads(response['deck']['body'])['cards'])>50
                    else:assert 'Sideboard' in response['deck']['body'] or len(response['deck']['body'].splitlines())>50
            finally:ctx.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)

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
        ctx=p.chromium.launch_persistent_context(str(tmp_path/'browser'),channel='chromium',headless=True,args=[f'--disable-extensions-except={ext}',f'--load-extension={ext}'])
        events=[]
        ctx.on('request',lambda request:events.append(('request',request.url)))
        ctx.on('requestfailed',lambda request:events.append(('failed',request.url,request.failure)))
        ctx.on('page',lambda tab:events.append(('page',tab.url)))
        def merchant_route(route):
            events.append(('route',route.request.url))
            route.fulfill(status=200,content_type='text/html',body=MERCHANT)
        ctx.route('https://www.tcgplaytest.com/**',merchant_route)
        page=ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.add_init_script("window.__helperConnected=false;window.addEventListener('message',event=>{if(event.data?.source==='proxy-foundry-helper'&&event.data.type==='PF_WORKSPACE_PONG')window.__helperConnected=true})")
            page.goto(server.origin+'/#orders')
            page.wait_for_function('window.__helperConnected===true',timeout=15000)
            # The click opens a tab whose extension starts a ZIP transfer.
            # Drive the DOM click without Playwright waiting for that new tab's
            # network load; the explicit assertions below own its readiness.
            page.locator('[data-open-order]').first.evaluate('(button)=>button.click()')
            deadline=time.monotonic()+45
            merchant=None
            observed=[]
            while time.monotonic()<deadline:
                merchant=next((tab for tab in ctx.pages if re.match(r'^https://www\.tcgplaytest\.com/',tab.url)),None)
                if merchant:break
                message=page.locator('#toast-host').inner_text()
                if message and message not in observed:observed.append(message)
                time.sleep(.1)
            if not merchant:
                (ROOT/'test-results').mkdir(exist_ok=True)
                (ROOT/'test-results'/'extension-debug.json').write_text(json.dumps({'pages':[tab.url for tab in ctx.pages],'toasts':observed,'events':events},indent=2))
            assert merchant,{'pages':[tab.url for tab in ctx.pages],'toasts':observed,'events':events[-20:]}
            expect(merchant.get_by_text('TCG editor fixture')).to_be_visible(timeout=15000)
            expect(merchant.locator('#pph-line')).to_contain_text('Uploaded 2 paired cards',timeout=45000)
            assert merchant.evaluate('tc.sha')==expected
            assert merchant.evaluate('tc.preview===1&&tc.checkout===0')
            assert not page.is_closed() and page.url.startswith(server.origin)
            assert 'secret' not in merchant.url
            unauthorized=ctx.new_page();unauthorized.goto('https://www.tcgplaytest.com/?view=design&proxyFoundryOrder=unauthorized')
            expect(unauthorized.locator('#pph-line')).to_contain_text('FAILED',timeout=15000)
            assert unauthorized.evaluate('tc.sha===null&&tc.checkout===0')
            (ROOT/'test-results').mkdir(exist_ok=True);merchant.screenshot(path=str(ROOT/'test-results/extension-paired-transfer.png'))
        finally:
            ctx.close()
            server.shutdown();server.server_close();app.close()
