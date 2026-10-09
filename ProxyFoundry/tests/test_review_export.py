"""Review plans and actual browser JPEG/ZIP exports."""
import functools,http.server,io,json,threading,time,zipfile
from pathlib import Path
import pytest
from PIL import Image
from test_job_families import app

ROOT=Path(__file__).resolve().parents[1]

def test_review_plan_uses_cached_renders_and_unique_jpeg_names(app):
    deck=app.fixture_deck
    deck['cards'][1]['faces'][0]['name']=deck['cards'][0]['faces'][0]['name']
    app.store.put('decks',deck,deck['revision'])
    plan=app.ws.review_plan(deck['id'])
    assert len(plan['items'])==3
    assert len({row['filename'] for row in plan['items']})==3
    assert all(row['filename'].endswith('.jpg') and row['assetId'] for row in plan['items'])
    single=app.ws.review_plan(deck['id'],deck['cards'][0]['id'],deck['cards'][0]['faces'][0]['id'])
    assert len(single['items'])==1 and single['filename'].endswith('.jpg')
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
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            super().do_GET()
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            names=['normal_review.jpg'] if data.get('cardId') else ['normal_review.jpg','transform_back_review.jpg','normal_other_review.jpg']
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
def test_browser_downloads_half_size_jpeg_and_valid_zip(review_browser,single):
    page,_=review_browser
    with page.expect_download() as event:page.evaluate("single=>review.downloadReview('deck',single?{cardId:'card',faceId:'face'}:{})",single)
    download=event.value;raw=Path(download.path()).read_bytes()
    if single:
        assert download.suggested_filename=='normal_review.jpg';files=[raw]
    else:
        assert download.suggested_filename=='deck_reviews.zip'
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist())=={'normal_review.jpg','transform_back_review.jpg','normal_other_review.jpg'}
            files=[archive.read(name) for name in archive.namelist()]
    for data in files:
        image=Image.open(io.BytesIO(data));image.load()
        assert image.format=='JPEG' and image.size==(201,140)
        assert max(abs(a-b) for a,b in zip(image.getpixel((20,20)),(225,170,25)))<5
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
