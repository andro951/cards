"""Five real Supernatural cards in the production static browser renderer."""
import base64
import functools
import http.server
import json
import os
import threading
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace
from test_website import build_site,copy_site

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',reason='Real Supernatural artwork and native full-art rendering')
EXAMPLES=[('Syr Gwyn, Hero of Ashvale','001_syr_gwyn_hero_of_ashvale.png'),
          ('Orzhov Basilica','073_orzhov_basilica.png'),
          ('Savai Triome','103_savai_triome.png'),
          ('Takenuma, Abandoned Mire','095_takenuma_abandoned_mire.png'),
          ('Command Tower','102_command_tower.png')]


def example_art(repo,filename):
    numbered=repo/'art'/filename
    return numbered if numbered.is_file() else repo/'art'/filename.split('_',1)[1]


def test_supernatural_full_card_art_and_downloaded_reviews(tmp_path):
    repo=ROOT.parent/'supernatural'
    if not repo.is_dir():
        repo=tmp_path/'supernatural';(repo/'art').mkdir(parents=True)
        network=Network(Store(tmp_path/'source-cache'))
        for filename in ['data.json',*['art/'+filename for _,filename in EXAMPLES]]:
            raw,_,_=network.fetch('https://raw.githubusercontent.com/andro951/cards/main/supernatural/'+filename)
            (repo/filename).write_bytes(raw)
    output=ROOT/'test-results'/'supernatural-full-art';output.mkdir(parents=True,exist_ok=True)
    source=Workspace(Store(tmp_path/'metadata'))
    deck=source.create({'name':'Supernatural full-card art verification','source':'\n'.join('1 '+name for name,_ in EXAMPLES)})
    metadata=json.loads((repo/'data.json').read_text(encoding='utf-8'))['cards']
    rows=[row for row in metadata if row['name'] in {name for name,_ in EXAMPLES}]
    images={filename:base64.b64encode(example_art(repo,filename).read_bytes()).decode() for _,filename in EXAMPLES}
    build_site(tmp_path);site=copy_site(tmp_path)
    worker=site/'web/engine-worker.js'
    injected='''
original_request = request
def request(app, method, url, body, headers):
    if str(url)=='/api/__test__/full-art-seed':
        import base64
        from foundry.images import ingest_image
        payload=json.loads(body)
        images={name.removesuffix('.png'):ingest_image(app.store,base64.b64decode(raw))['id'] for name,raw in payload['images'].items()}
        deck=payload['deck']
        deck['settings']=app.ws.validate_settings({'source':{'mode':'local','localFiles':images},'artist':'ChatGPT','templateRules':{}})
        for card in deck['cards']:
            if card['name']=='Syr Gwyn, Hero of Ashvale':card['faces'][0]['templateOverride']='godzilla-card'
        app.ws._apply_card_data(deck,payload['metadata'])
        saved=app.store.put('decks',deck)
        return {'status':200,'mime':'application/json','body':json.dumps({'id':saved['id']}).encode(),'headers':{}}
    return original_request(app,method,url,body,headers)
'''
    worker.write_text(worker.read_text(encoding='utf-8').replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page(accept_downloads=True);errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='domcontentloaded')
            page.locator('#import-deck').wait_for(timeout=90000)
            ident=page.evaluate("async payload=>(await (await import('/site/ui.js')).api('/api/__test__/full-art-seed',payload)).id",{'deck':deck,'metadata':rows,'images':images})
            page.evaluate('id=>location.hash="deck/"+id',ident)
            page.locator('#generate-deck').wait_for(timeout=30000)
            page.click('#generate-deck')
            try:
                page.locator('.badge.ready,.toast.error').first.wait_for(timeout=240000)
                page.get_by_role('dialog',name='Your deck is ready').wait_for(timeout=30000)
            except Exception:
                page.screenshot(path=str(output/'browser-failure.png'),full_page=True)
                (output/'browser-failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
                raise
            page.get_by_role('button',name='View deck',exact=True).click()
            current=page.evaluate("async id=>(await import('/site/ui.js')).api('/api/decks/'+id)",ident)
            assert current['summary']['rendered']==5 and not errors,errors
            recipes=[]
            for card in current['cards']:
                compiled=card['faces'][0]['compiled'];data=compiled['data'];recipes.append(compiled['recipe'])
                assert data['artBounds']=={'x':0,'y':0,'width':1,'height':1}
                filename=next(filename for name,filename in EXAMPLES if name==card['name'])
                original=Image.open(example_art(repo,filename)).convert('RGB')
                zoom=max(2010/original.width,2814/original.height)
                assert data['artZoom']==pytest.approx(zoom)
                assert data['artX']*2010==pytest.approx((2010-original.width*zoom)/2)
                assert data['artY']*2814==pytest.approx((2814-original.height*zoom)/2)
                (output/(filename.removesuffix('.png')+'_original.png')).write_bytes(example_art(repo,filename).read_bytes())
            assert 'land_full_legendary' in recipes,recipes
            page.evaluate('window.showSaveFilePicker=undefined')
            page.click('#deck-menu')
            with page.expect_download(timeout=240000) as download:
                page.click('#download-review-images')
            saved=output/'downloaded-reviews.zip';download.value.save_as(saved)
            with zipfile.ZipFile(saved) as archive:
                assert len(archive.namelist())==5
                for name in archive.namelist():
                    assert name.endswith('.jpg') and '/' not in name
                    (output/name).write_bytes(archive.read(name))
            checks=[]
            for card in current['cards']:
                filename=next(filename for name,filename in EXAMPLES if name==card['name'])
                from foundry.domain import slug
                review=Image.open(output/(slug(card['name'])+'_review.jpg')).convert('RGB')
                assert review.size==(2011,1407)
                original=Image.open(example_art(repo,filename)).convert('RGB')
                #Sample uncovered art on the real rendered half, using the source
                #coordinates implied by full-canvas cover fit, independently of the compiler.
                zoom=max(2010/original.width,2814/original.height)
                offset_x=(2010-original.width*zoom)/2;offset_y=(2814-original.height*zoom)/2
                points=[(500,650),(1000,950),(1500,1300)]
                differences=[]
                for x,y in points:
                    expected=original.getpixel((round((x-offset_x)/zoom),round((y-offset_y)/zoom)))
                    actual=review.getpixel((1006+x//2,y//2))
                    differences.append(max(abs(a-b) for a,b in zip(actual,expected)))
                assert max(differences)<35,(card['name'],differences)
                checks.append({'name':card['name'],'recipe':card['faces'][0]['compiled']['recipe'],'pixelDifferences':differences,'art':filename})
            (output/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
