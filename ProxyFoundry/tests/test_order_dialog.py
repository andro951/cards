"""Real order-review UI handlers and modal CSS, with packaging job held pending."""
import os
from pathlib import Path
import pytest
from test_print_bridge import bridge_page
from ui_component import ui_source
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(not(os.environ.get('PF_DOM')=='1' or os.environ.get('PF_BROWSER')=='1'),reason='Opt-in Chromium component tests')


def mount(page):
    import io
    from PIL import Image
    origin=page.url if page.url.startswith('http') else 'http://order.test/'
    raw=io.BytesIO();Image.new('RGB',(30,42),'gold').save(raw,'PNG')
    page.route('http://order.test/api/assets/**',lambda route:route.fulfill(body=raw.getvalue(),content_type='image/png'))
    page.set_content('<html><body><button id="launch">Open</button><div id="modal-host"></div><div id="toast-host"></div></body></html>')
    page.evaluate("url=>{const base=document.createElement('base');base.href=url;document.head.append(base);}",origin)
    for name in ('styles.css','forge-theme.css'):page.add_style_tag(content=(ROOT/'site'/name).read_text(encoding='utf-8'))
    page.add_script_tag(content=ui_source())
    script='\n'.join(line for line in (ROOT/'site/orders.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export ','')
    page.add_script_tag(content=script)
    page.evaluate('''()=>{
      window.tc={payload:null,visibleAtJobStart:null};
      job=async(url,payload)=>{tc.payload=payload;tc.visibleAtJobStart=!!document.querySelector('.modal');return new Promise((resolve,reject)=>{window.finishJob=resolve;window.failJob=reject})};
      reviewPlan({count:1,bytes:2345,decks:[{id:'deck1',name:'Deck'}],warnings:['Crop review required'],cards:[{deckId:'deck1',cardId:'card1',name:'Card',deckName:'Deck',frontAsset:'a',backAsset:'b'}]},['deck1']);
    }''')


def test_order_build_closes_before_job_and_keeps_acknowledgement(bridge_page):
    from playwright.sync_api import expect
    page,errors=bridge_page;mount(page)
    expect(page.locator('#build-order')).to_be_disabled()
    page.check('#ack-order-warnings');page.click('#build-order')
    assert page.locator('.modal').count()==0
    assert page.evaluate('tc')=={'payload':{'deckIds':['deck1'],'acknowledge':True},'visibleAtJobStart':False}
    page.evaluate("finishJob({id:'order1',count:1,decks:[{name:'Deck'}],zipBytes:2345,download:'/zip'})")
    expect(page.locator('#modal-title')).to_have_text('Your print package is ready')
    assert not errors


def test_order_build_failure_uses_toast_not_detached_dialog(bridge_page):
    from playwright.sync_api import expect
    page,errors=bridge_page;mount(page)
    page.check('#ack-order-warnings');page.click('#build-order')
    page.evaluate("failJob(new Error('Packaging failed test'))")
    expect(page.locator('.toast.error')).to_contain_text('Packaging failed test')
    assert page.locator('.modal').count()==0 and not errors


@pytest.mark.parametrize('width,height',[(1440,1000),(390,844)])
def test_large_order_modal_has_clipped_rounded_header_and_scrollable_body(bridge_page,width,height):
    page,errors=bridge_page;page.set_viewport_size({'width':width,'height':height});mount(page)
    props=page.evaluate('''()=>{
      const m=document.querySelector('.modal'),h=m.querySelector('.modal-header'),f=m.querySelector('.modal-footer');
      const r=m.getBoundingClientRect(),s=getComputedStyle(m),hs=getComputedStyle(h),fs=getComputedStyle(f);
      const hit=document.elementFromPoint(r.x+1,r.y+1);
      return {clip:s.overflow,radius:parseFloat(s.borderTopLeftRadius),header:parseFloat(hs.borderTopLeftRadius),footer:parseFloat(fs.borderBottomLeftRadius),body:getComputedStyle(m.querySelector('.modal-body')).overflowY,cornerInHeader:h.contains(hit),overflow:document.documentElement.scrollWidth>innerWidth};
    }''')
    assert props['clip']=='hidden' and props['header']==props['radius']-1
    assert props['footer']==props['radius']-1 and props['body']=='auto'
    assert not props['cornerInHeader'] and not props['overflow'] and not errors


@pytest.mark.parametrize('browser',[False,True],ids=['local-order','browser-order'])
def test_order_tiles_use_thumbnails_and_enlargement_uses_original(bridge_page,browser):
    page,errors=bridge_page;mount(page)
    if browser:
        script='\n'.join(line for line in (ROOT/'web/review-browser.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export ','')
        page.add_script_tag(content=script)
    page.evaluate('''browser=>{
        closeModal();
        const plan={id:'order',count:1,bytes:100,decks:[{id:'deck',name:'Deck',backAsset:'b'.repeat(64)}],cards:[{deckId:'deck',cardId:'card',name:'Preview card',deckName:'Deck',frontAsset:'a'.repeat(64),backAsset:'b'.repeat(64)}]};
        if(browser)showReview(plan,['deck'],true,()=>{},()=>{});
        else reviewPlan(plan,['deck'],true);
    }''',browser)
    images=page.locator('.modal-body img')
    assert images.count()==2
    assert all(source.endswith('/thumbnail') for source in images.evaluate_all('(items)=>items.map(image=>image.getAttribute("src"))'))
    if browser:
        page.get_by_title('Enlarge Preview card front').click()
        assert page.get_by_role('dialog',name='Preview card front',exact=True).locator('img').get_attribute('src')=='/api/assets/'+'a'*64
        page.get_by_role('button',name='Close image').click()
    else:
        assert page.locator('.pair-images a').first.get_attribute('href')=='/api/assets/'+'a'*64
    assert not errors,errors


def test_large_browser_order_search_retains_images_and_input(bridge_page):
    page,errors=bridge_page;mount(page)
    script='\n'.join(line for line in (ROOT/'web/review-browser.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export ','')
    page.add_script_tag(content=script)
    page.evaluate('''()=>{
        closeModal();
        const cards=Array.from({length:400},(_,index)=>({deckId:'deck',cardId:String(index),name:'Card '+String(index).padStart(3,'0'),deckName:'Deck',frontAsset:index.toString(16).padStart(64,'0'),backAsset:'b'.repeat(64)}));
        showReview({id:'order',count:400,bytes:100,decks:[{id:'deck',name:'Deck',backAsset:'b'.repeat(64)}],cards},['deck'],true,()=>{},()=>{});
        window.originalImage=document.querySelector('#browser-pair-grid img');
        window.originalOrderSearch=document.querySelector('.modal-body input');
    }''')
    page.locator('.modal-body input').fill('Card 00')
    assert page.locator('#browser-pair-grid article:visible').count()==10
    page.locator('.modal-body input').press('ArrowLeft')
    caret=page.locator('.modal-body input').evaluate('(input)=>input.selectionStart')
    report=page.evaluate('''()=>{
        const grid=document.querySelector('#browser-pair-grid');let mutations=0;
        const observer=new MutationObserver(rows=>{mutations+=rows.length;});observer.observe(grid,{childList:true,subtree:true});
        const start=performance.now();
        for(let index=0;index<40;index++)originalOrderSearch.dispatchEvent(new Event('input'));
        mutations+=observer.takeRecords().length;observer.disconnect();
        return {seconds:(performance.now()-start)/1000,mutations,sameImage:originalImage===grid.querySelector('img'),focused:document.activeElement===originalOrderSearch};
    }''')
    assert report['mutations']==0 and report['sameImage'] and report['focused'],report
    assert page.locator('.modal-body input').evaluate('(input)=>input.selectionStart')==caret
    assert all(source.endswith('/thumbnail') for source in page.locator('#browser-pair-grid img').evaluate_all('(images)=>images.map(image=>image.getAttribute("src"))'))
    page.locator('.modal-body input').fill('No such card');assert page.locator('#browser-pair-grid article:visible').count()==0
    page.locator('.modal-body input').fill('');assert page.locator('#browser-pair-grid article:visible').count()==400
    assert not errors,errors


@pytest.mark.parametrize('dismiss',['escape','x'])
def test_browser_image_lightbox_ignores_outside_click_and_keeps_review(bridge_page,dismiss):
    page,errors=bridge_page;mount(page)
    script='\n'.join(line for line in (ROOT/'web/review-browser.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export ','')
    page.add_script_tag(content=script)
    page.evaluate("lightbox('a'.repeat(64),'Preview test')")
    enlarged=page.get_by_role('dialog',name='Preview test',exact=True)
    enlarged.dispatch_event('click')
    assert enlarged.is_visible()
    if dismiss=='escape':page.keyboard.press('Escape')
    else:enlarged.get_by_role('button',name='Close image',exact=True).click()
    enlarged.wait_for(state='detached')
    assert not enlarged.count()
    assert page.get_by_role('dialog',name='Review your paired order').count()==1
    assert not errors,errors


def browser_review(page):
    mount(page)
    script='\n'.join(line for line in (ROOT/'web/review-browser.js').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export ','')
    page.add_script_tag(content=script)
    page.evaluate('''()=>{
      closeModal();window.builtOrder=null;
      window.job=async(url,payload,options)=>{
        window.buildProgress=options.onProgress;window.buildSignal=options.signal;
        return new Promise((resolve,reject)=>{
          window.finishBuild=resolve;window.failBuild=reject;
          options.signal.addEventListener('abort',()=>reject(new Error('Order packaging cancelled.')),{once:true});
        });
      };
      showReview({count:108,bytes:1200000000,decks:[{id:'deck',name:'Wrath of the Gods',backAsset:'b'.repeat(64)}],
        cards:[{deckId:'deck',cardId:'one',name:'One-sided card',deckName:'Wrath of the Gods',frontAsset:'a'.repeat(64),backAsset:'b'.repeat(64)},
               {deckId:'deck',cardId:'two',name:'Esika',deckName:'Wrath of the Gods',frontAsset:'c'.repeat(64),backAsset:'d'.repeat(64)}]},
        ['deck'],false,order=>window.builtOrder=order,()=>{});
    }''')


@pytest.mark.parametrize('outcome',['done','failed','cancelled'])
@pytest.mark.parametrize('width',[1336,390],ids=['desktop','mobile'])
def test_browser_zip_progress_is_visible_inside_review_and_recovers(bridge_page,outcome,width):
    from playwright.sync_api import expect
    page,errors=bridge_page;page.set_viewport_size({'width':width,'height':900});browser_review(page)
    build=page.get_by_role('button',name='Build paired ZIP',exact=True)
    build.click()
    progress=page.get_by_role('progressbar',name='Paired ZIP build progress')
    expect(progress).to_be_visible();assert progress.get_attribute('value') is None
    expect(page.locator('#modal-close')).to_be_disabled();expect(build).to_be_disabled()
    page.evaluate("buildProgress({state:'running',done:35,total:108,message:'Packaging Esika'})")
    assert progress.get_attribute('value')=='32'
    expect(page.locator('#order-build-progress')).to_contain_text('32% · 35 / 108 cards packaged')
    expect(page.locator('#order-build-progress')).to_contain_text('Packaging Esika')
    bounds=progress.bounding_box()
    assert bounds['x']>=0 and bounds['y']>=0 and bounds['x']+bounds['width']<=width and bounds['y']+bounds['height']<=900
    page.keyboard.press('Escape');expect(progress).to_be_visible()
    if outcome=='done':
        page.evaluate("buildProgress({state:'running',done:108,total:108,message:'Saving ZIP'})")
        assert progress.get_attribute('value')=='99','Do not finish the bar before the ZIP is saved.'
        page.evaluate("finishBuild({id:'ready-order'})")
    else:
        if outcome=='cancelled':page.get_by_role('button',name='Cancel build',exact=True).click()
        else:page.evaluate("failBuild(new Error('Disk full test'))")
        expect(page.locator('#order-build-progress')).to_contain_text('ZIP build '+('cancelled.' if outcome=='cancelled' else 'failed.'))
        expect(build).to_be_enabled();expect(page.locator('#modal-close')).to_be_enabled()
        if outcome=='cancelled':assert page.evaluate('buildSignal.aborted')
        build.click();assert progress.get_attribute('value') is None
        page.evaluate("finishBuild({id:'ready-order'})")
    page.wait_for_function("builtOrder?.id==='ready-order'")
    assert not page.locator('#modal-host .modal').count() and not errors,errors


def test_browser_back_previews_fall_back_to_print_images_and_retry(bridge_page):
    import io
    from PIL import Image
    page,errors=bridge_page
    page.route('http://review.test/',lambda route:route.fulfill(body='<html><body></body></html>',content_type='text/html'))
    page.goto('http://review.test/')
    buffer=io.BytesIO();Image.new('RGB',(30,42),'gold').save(buffer,'PNG');raw=buffer.getvalue()
    requests=[];missing=[False]
    def image_request(route):
        url=route.request.url;requests.append(url)
        back=any('/'+letter*64 in url for letter in ['b','d'])
        if back and ('/thumbnail' in url or missing[0]):route.fulfill(status=404,body='Missing thumbnail')
        else:route.fulfill(body=raw,content_type='image/png')
    page.route('http://review.test/api/assets/**',image_request)
    browser_review(page)
    page.wait_for_function("[...document.querySelectorAll('.modal-body img')].length===4&&[...document.querySelectorAll('.modal-body img')].every(image=>image.complete&&image.naturalWidth>0)")
    for letter,label in [('b','Common back'),('d','Esika back')]:
        image=page.get_by_title('Enlarge '+label).locator('img')
        assert image.get_attribute('loading')=='eager'
        assert image.get_attribute('src')=='/api/assets/'+letter*64
        assert any('/'+letter*64+'/thumbnail' in url for url in requests)
    #A missing original stays actionable and can be retried after storage recovers.
    missing[0]=True
    page.get_by_title('Enlarge Esika back').locator('img').evaluate("image=>image.dispatchEvent(new Event('error'))")
    retry=page.get_by_title('Retry Esika back');retry.wait_for()
    assert 'Image unavailable. Click to retry.' in retry.inner_text()
    missing[0]=False;retry.click()
    page.wait_for_function("document.querySelector('img[alt=\"Esika back\"]').naturalWidth>0&&document.querySelector('img[alt=\"Esika back\"]').style.visibility==='visible'")
    assert not errors,errors
