"""Real order-review UI handlers and modal CSS, with packaging job held pending."""
import os
from pathlib import Path
import pytest
from test_print_bridge import bridge_page
from ui_component import ui_source
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(not(os.environ.get('PF_DOM')=='1' or os.environ.get('PF_BROWSER')=='1'),reason='Opt-in Chromium component tests')


def mount(page):
    page.set_content('<html><body><button id="launch">Open</button><div id="modal-host"></div><div id="toast-host"></div></body></html>')
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
        assert page.locator('body > div > img').last.get_attribute('src')=='/api/assets/'+'a'*64
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
