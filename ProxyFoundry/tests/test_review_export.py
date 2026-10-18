"""Review plans and actual browser PNG/ZIP exports."""
import functools,http.server,io,json,threading,time,zipfile
from pathlib import Path
import pytest
from PIL import Image
from test_job_families import app

ROOT=Path(__file__).resolve().parents[1]

def test_review_plan_uses_cached_renders_and_unique_png_names(app):
    deck=app.fixture_deck
    deck['cards'][1]['faces'][0]['name']=deck['cards'][0]['faces'][0]['name']
    app.store.put('decks',deck,deck['revision'])
    plan=app.ws.review_plan(deck['id'])
    assert len(plan['items'])==3
    assert len({row['filename'] for row in plan['items']})==3
    assert all(row['filename'].endswith('.png') and row['assetId'] for row in plan['items'])
    single=app.ws.review_plan(deck['id'],deck['cards'][0]['id'],deck['cards'][0]['faces'][0]['id'])
    assert len(single['items'])==1 and single['filename'].endswith('.png')
    from foundry.browser import request
    response=request(app,'POST','/api/decks/'+deck['id']+'/review-plan',b'{}')
    assert response['status']==200 and len(json.loads(response['body'])['items'])==3
    assert not list((app.store.home/'orders').iterdir())
    with pytest.raises(ValueError):app.ws.review_plan(deck['id'],deck['cards'][0]['id'],'missing-face')

@pytest.fixture
def review_browser():
    from playwright.sync_api import sync_playwright
    raw=io.BytesIO();Image.new('RGB',(200,280),(225,170,25)).save(raw,'PNG');raw=raw.getvalue()
    control={'fail':False,'delay':0}
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/reference.png' or self.path.startswith('/api/assets/'):
                if self.path=='/reference.png':time.sleep(control['delay'])
                self.send_response(404 if control['fail'] else 200);self.send_header('Content-Type','image/png');self.end_headers()
                try:self.wfile.write(control.get('reference' if self.path=='/reference.png' else 'rendered',raw))
                except (BrokenPipeError,ConnectionResetError):pass
                return
            super().do_GET()
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            names=['normal_review.png'] if data.get('cardId') else ['normal_review.png','transform_back_review.png','normal_other_review.png']
            response={'filename':names[0] if data.get('cardId') else 'deck_reviews.zip','items':[{'filename':n,'name':n,'reference':'http://127.0.0.1:'+str(self.server.server_port)+'/reference.png','assetId':'a'*64} for n in names]}
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(response).encode())
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(accept_downloads=True)
        page.route('**/site/app.js',lambda route:route.fulfill(body='',content_type='text/javascript'))
        page.goto('http://127.0.0.1:'+str(server.server_port)+'/site/index.html')
        page.evaluate("async()=>{window.review=await import('/site/review-export.js');window.ui=await import('/site/ui.js');window.showSaveFilePicker=()=>{throw Error('Unexpected folder picker');};}")
        yield page,control
        browser.close()
    server.shutdown();server.server_close()

@pytest.mark.parametrize('single',[True,False])
def test_browser_downloads_half_size_png_and_valid_zip(review_browser,single):
    page,_=review_browser
    with page.expect_download() as event:page.evaluate("single=>review.downloadReview('deck',single?{cardId:'card',faceId:'face'}:{})",single)
    download=event.value;raw=Path(download.path()).read_bytes()
    if single:
        assert download.suggested_filename=='normal_review.png';files=[raw]
    else:
        assert download.suggested_filename=='deck_reviews.zip'
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist())=={'normal_review.png','transform_back_review.png','normal_other_review.png'}
            files=[archive.read(name) for name in archive.namelist()]
    for data in files:
        image=Image.open(io.BytesIO(data));image.load()
        assert image.format=='PNG' and image.size==(201,140)
        assert image.getpixel((20,20))[:3]==(225,170,25)
    assert page.evaluate('ui.work.busy') is False

@pytest.mark.parametrize('cancel',[False,True])
def test_review_failure_or_cancel_releases_workers_and_deck_lock(review_browser,cancel):
    page,control=review_browser;downloads=[];page.on('download',lambda d:downloads.append(d))
    control['fail']=not cancel;control['delay']=.5 if cancel else 0
    page.evaluate("()=>{window.result=review.downloadReview('deck').then(()=>'',e=>e.message);}")
    if cancel:page.evaluate("()=>[...ui.work.tasks.values()][0].controller.abort()")
    error=page.evaluate('result')
    assert ('cancelled' if cancel else 'HTTP 404') in error
    assert not downloads and page.evaluate('ui.work.busy') is False


def orientation_images(kind):
    reference=Image.new('RGB',{'landscape':(200,280),'portrait':(280,200),'square':(200,200)}[kind])
    w,h=reference.size
    for box,color in [((0,0,w//2,h//2),(230,20,20)),((w//2,0,w,h//2),(20,230,20)),
                      ((0,h//2,w//2,h),(20,20,230)),((w//2,h//2,w,h),(230,230,20))]:
        reference.paste(color,box)
    rendered=Image.new('RGB',(280,200) if kind=='landscape' else (200,280),(100,100,100))
    encoded=[]
    for image in (reference,rendered):
        out=io.BytesIO();image.save(out,'PNG');encoded.append(out.getvalue())
    return encoded


def assert_review_orientation(raw,kind):
    image=Image.open(io.BytesIO(raw));image.load()
    w,h=(140,100) if kind=='landscape' else (100,140)
    assert image.size==(w*2+1,h)
    colors={'landscape':[(20,20,230),(230,20,20),(230,230,20),(20,230,20)],
            'portrait':[(20,230,20),(230,230,20),(230,20,20),(20,20,230)],
            'square':[(230,20,20),(20,230,20),(20,20,230),(230,230,20)]}[kind]
    for point,color in zip([(w//4,h//4),(w*3//4,h//4),(w//4,h*3//4),(w*3//4,h*3//4)],colors):
        assert max(abs(a-b) for a,b in zip(image.getpixel(point),color))<8
    if kind=='square':assert max(image.getpixel((w//2,5))[:3])<8


@pytest.mark.parametrize('kind',['landscape','portrait','square'])
def test_review_fallback_rotates_sideways_references_without_stretching(app,monkeypatch,kind):
    reference,rendered=orientation_images(kind)
    monkeypatch.setattr(app.ws.net,'fetch_transient',lambda url:(reference,'image/png',{}))
    asset=app.store.add_asset(rendered,'image/png')
    output=app.ws._review_composite('https://cards.scryfall.io/reference.png',{'asset_id':asset['id']})
    assert_review_orientation(output,kind)


@pytest.mark.parametrize('kind',['landscape','portrait','square'])
def test_review_worker_rotates_sideways_references_without_stretching(review_browser,kind):
    page,control=review_browser;control['reference'],control['rendered']=orientation_images(kind)
    with page.expect_download() as event:
        page.evaluate("()=>review.downloadReview('deck',{cardId:'card',faceId:'face'})")
    assert_review_orientation(Path(event.value.path()).read_bytes(),kind)


def test_png_review_worker_keeps_generated_pixels_identical_when_only_reference_changes(review_browser):
    page,control=review_browser
    def export():
        with page.expect_download() as event:
            page.evaluate("()=>review.downloadReview('deck',{cardId:'card',faceId:'face'})")
        image=Image.open(event.value.path()).convert('RGB')
        return image.crop((101,0,201,140)).tobytes()
    original=export()
    out=io.BytesIO();Image.new('RGB',(200,280),(20,50,230)).save(out,'PNG')
    control['reference']=out.getvalue()
    assert export()==original
    changed=Image.new('RGB',(200,280),(225,170,25))
    changed.putpixel((100,100),(0,0,0))
    out=io.BytesIO();changed.save(out,'PNG');control['rendered']=out.getvalue()
    assert export()!=original


def test_png_review_fallback_keeps_generated_pixels_identical_when_only_reference_changes(app,monkeypatch):
    def encoded(color):
        out=io.BytesIO();Image.new('RGB',(200,280),color).save(out,'PNG');return out.getvalue()
    asset=app.store.add_asset(encoded((225,170,25)),'image/png')
    reference=[encoded((200,20,20))]
    monkeypatch.setattr(app.ws.net,'fetch_transient',lambda url:(reference[0],'image/png',{}))
    def export():
        raw=app.ws._review_composite('https://cards.scryfall.io/reference.png',{'asset_id':asset['id']})
        image=Image.open(io.BytesIO(raw));assert image.format=='PNG'
        return image.crop((101,0,201,140)).tobytes()
    original=export();reference[0]=encoded((20,50,230))
    assert export()==original
