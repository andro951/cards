"""Offline module/DOM smoke tests, independent of browser network policies.

These do not claim to test HTTP, CardConjurer or a live printer. Real HTTP tests
are in test_browser.py and run in CI with PF_BROWSER=1.
"""
import json,os,re,shutil
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_DOM')!='1',reason='Opt-in offline browser DOM tests')

def bundle():
    out=[]
    for name in ['diagnostics','work','ui','deletion','credits','backs','github-setup','render','frame-picker','setup','orders','templates','settings','deck','app']:
        text=(ROOT/'site'/(name+'.js')).read_text(encoding='utf-8')
        exports=re.findall(r'export\s+(?:async\s+)?(?:function|const|let|class)\s+([$\w]+)',text)
        text=re.sub(r"import\s+\{([^}]+)\}\s+from\s+'\./([^']+)\.js';",lambda m:'const {'+m[1]+'}=__mod_'+m[2].replace('-','_')+';',text)
        text=text.replace("await import('./ui.js')",'__mod_ui')
        text=re.sub(r'\bexport\s+','',text)
        out.append('const __mod_'+name.replace('-','_')+'=(()=>{\n'+text+'\nreturn {'+','.join(exports)+'};})();')
    return '\n'.join(out)

@pytest.fixture
def dom_page(tmp_path):
    from playwright.sync_api import sync_playwright
    from foundry.domain import GROUP_LABELS,uid
    from foundry.compiler import BUILTINS
    from foundry.workspace import DEFAULT_SETTINGS
    from foundry.legacy import compiler as native
    ident=uid();cid=uid();fid=uid()
    deck={'id':ident,'name':'Test deck','revision':1,'status':'draft','settings':DEFAULT_SETTINGS,'notes':'','summary':{'cards':2,'faces':1,'rendered':0,'warnings':0,'errors':0},
          'cards':[{'id':cid,'name':'Test creature','quantity':2,'section':'mainboard','scryfall':{'name':'Test creature','type_line':'Creature — Elf','set':'tst','collector_number':'1','rarity':'rare','oracle_text':'Vigilance'},'faces':[{'id':fid,'index':0,'group':'standard','name':'Test creature','artistOverride':None,'artOverride':None,'templateOverride':None}]}]}
    state={'deck':deck,'templates':BUILTINS,'groups':GROUP_LABELS,'settings':{'id':'global','revision':1,'refreshData':False,'defaults':{}},'seed':native.LAYOUTS['creature']['data']}
    html=(ROOT/'site/index.html').read_text(encoding='utf-8');html=re.sub(r'<script[\s\S]*?</script>','',html);html=re.sub(r'<link[^>]*>','',html)
    with sync_playwright() as p:
        exe=os.environ.get('PF_DOM_EXECUTABLE') or shutil.which('chromium')
        b=p.chromium.launch(headless=True,**({'executable_path':exe} if exe else {}));page=b.new_page(viewport={'width':1440,'height':1024});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.set_content(html);page.add_style_tag(content=(ROOT/'site/styles.css').read_text(encoding='utf-8'))
        page.evaluate('window.__fixture='+json.dumps(state))
        page.add_script_tag(content=r'''
        window.postMessage=()=>{};
        window.fetch=async(path,opts={})=>{
          const d=opts.body?JSON.parse(opts.body):null,F=window.__fixture;let value={};
          if(path==='/api/bootstrap')value={csrf:'test',runtimeOrigin:'http://127.0.0.1:1111',groups:F.groups,settings:F.settings,stats:{},backs:{default:{id:'a'.repeat(64)},blank:{id:'b'.repeat(64)},iconBounds:{x:207,y:450,size:640},blankSize:[1055,1491]}};
          else if(path==='/api/decks')value=F.decks||[F.deck];
          else if(path==='/api/templates'&&!d)value=F.templates;
          else if(path==='/api/templates'&&d){value={...d,id:'33333333-3333-4333-8333-333333333333'};F.templates.push(value);}
          else if(path.startsWith('/api/templates/seed'))value=F.seed;
          else if(path==='/api/settings'){if(d)F.settings={...F.settings,...d,revision:F.settings.revision+1};value=F.settings;}
          else if(path==='/api/stats')value={renders:1,cacheEntries:4,assetBytes:3000,home:'local workspace'};
          else if(path==='/api/trash'||path==='/api/orders')value=[];
          else if(path.includes('/cards/')&&d){const c=F.deck.cards[0];if(d.quantity)c.quantity=Number(d.quantity);if(d.artistOverride!==undefined)c.faces[0].artistOverride=d.artistOverride;F.deck.summary.cards=c.quantity;F.deck.revision++;value=F.deck;}
          else if(path.endsWith('/save')){F.deck={...F.deck,...d,revision:F.deck.revision+1};value=F.deck;}
          else if(path.startsWith('/api/decks/'))value=F.deck;
          else if(path==='/api/client-error'){console.error(d?.error);}
          else throw new Error('Unhandled offline fixture request '+path);
          return {ok:true,status:200,text:async()=>JSON.stringify(value),json:async()=>value};
        };
        ''')
        page.add_script_tag(content=bundle())
        try:page.locator('.deck-tile').wait_for(timeout=5000)
        except Exception as exc:raise AssertionError('Offline UI did not mount: '+repr(errors)) from exc
        yield page,errors
        (ROOT/'test-results').mkdir(exist_ok=True)
        page.screenshot(path=str(ROOT/'test-results/offline-last.png'),full_page=True);b.close()

def test_offline_deck_controls_and_templates(dom_page):
    page,errors=dom_page
    page.locator('.deck-tile').click();page.locator('[data-card]').click();page.fill('#card-qty','4');page.click('#save-card')
    page.wait_for_function("document.querySelector('.quantity-pill')?.textContent==='4×'")
    page.locator('.page-head h1').click();page.locator('.page-head input').fill('Edited deck');page.locator('.page-head input').press('Enter')
    page.wait_for_function("document.querySelector('h1')?.textContent==='Edited deck'")
    page.click('.topbar [data-nav=templates]');page.click('#new-template');page.fill('#template-name','My frame');page.click('#save-template');page.get_by_text('My frame',exact=True).wait_for()
    assert not errors,errors

def test_offline_settings_and_mobile(dom_page):
    page,errors=dom_page
    page.click('.topbar [data-nav=settings]');page.check('#global-refresh')
    page.wait_for_function('window.__fixture.settings.refreshData === true')
    assert page.evaluate('window.__fixture.settings.refreshData') is True
    page.set_viewport_size({'width':390,'height':844});page.click('.topbar [data-nav=decks]');page.locator('.deck-tile').wait_for()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    assert not errors,errors


def test_offline_large_card_grid_keeps_input_and_tiles_during_progress(dom_page):
    page,errors=dom_page
    page.evaluate("""()=>{
      const deck=window.__fixture.deck,card=deck.cards[0];
      card.faces[0].selectedArtUrl='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      deck.settings.backAsset=null;
      deck.cards=Array.from({length:400},(_,index)=>({...structuredClone(card),id:`00000000-0000-4000-8000-${String(index+1).padStart(12,'0')}`,name:`Card ${String(index).padStart(3,'0')}`,quantity:1}));
      deck.summary={cards:400,faces:400,rendered:0,warnings:0,errors:0};
    }""")
    page.locator('.deck-tile').click();page.locator('#card-search').wait_for()
    page.evaluate("window.originalSearch=document.querySelector('#card-search');window.originalCard=document.querySelector('[data-card]');")
    page.locator('#card-search').fill('Card 00')
    assert page.locator('.card-item:visible').count()==10
    page.keyboard.press('ArrowLeft');caret=page.locator('#card-search').evaluate('(input)=>input.selectionStart')
    report=page.evaluate("""async()=>{
      const deck=window.__fixture.deck;deck.status='prepared';deck.settings.backAsset='b'.repeat(64);
      for(const card of deck.cards)card.faces[0].compiled={render:{url:'/api/assets/'+'a'.repeat(64)}};
      deck.summary.rendered=400;
      const started=performance.now();
      for(let index=0;index<10;index++)await __mod_deck.refreshDeckProgress(deck.id);
      return {seconds:(performance.now()-started)/1000,sameSearch:originalSearch===document.querySelector('#card-search'),
        sameCard:originalCard===document.querySelector('[data-card]'),focused:document.activeElement===originalSearch};
    }""")
    assert report['sameSearch'] and report['sameCard'] and report['focused'],report
    assert page.locator('#card-search').input_value()=='Card 00'
    assert page.locator('#card-search').evaluate('(input)=>input.selectionStart')==caret
    assert page.locator('.count-label').inner_text()=='400 cards · 400 faces · 400 rendered'
    assert page.locator('[data-card] img').first.get_attribute('src').endswith('/thumbnail')
    page.locator('[data-card]').first.evaluate("button=>button.dispatchEvent(new Event('mouseenter'))")
    assert page.locator('[data-card] img').first.get_attribute('src')=='/api/assets/'+'b'*64+'/thumbnail'
    page.locator('[data-card]').first.evaluate("button=>button.dispatchEvent(new Event('mouseleave'))")
    assert page.locator('[data-card] img').first.get_attribute('src')=='/api/assets/'+'a'*64+'/thumbnail'
    page.locator('[data-card-filter=unrendered]').click()
    assert page.locator('.card-item:visible').count()==0
    assert page.get_by_role('heading',name='No cards match',exact=True).is_visible()
    page.locator('[data-card-filter=all]').click()
    page.locator('#card-search').fill('Card 00');page.locator('[data-card]:visible').first.click()
    page.fill('#card-qty','3')
    page.evaluate('async()=>{await __mod_deck.refreshDeckProgress(window.__fixture.deck.id);}')
    assert page.locator('#card-qty').input_value()=='3'
    assert page.locator('[role=dialog]').count()==1
    assert not errors,errors


def test_offline_library_progress_keeps_search_selection_and_filters(dom_page):
    page,errors=dom_page
    page.evaluate("""async()=>{
      const fixture=window.__fixture;fixture.decks=[fixture.deck,...Array.from({length:299},(_,index)=>({...structuredClone(fixture.deck),id:`00000000-0000-4000-8000-${String(index+1).padStart(12,'0')}`,name:`Other ${index}`}))];
      await __mod_app.route();window.originalSearch=document.querySelector('#deck-search');
      window.templatesReads=0;const original=window.fetch;window.fetch=async(path,options)=>{if(path==='/api/templates')templatesReads++;return original(path,options);};
    }""")
    page.locator('#deck-search').fill('Test');page.locator('[data-select]:visible').check();page.locator('#deck-search').focus()
    page.evaluate("""async()=>{
      const deck=window.__fixture.deck;deck.status='ready';deck.summary.rendered=1;
      await __mod_app.refreshLibraryProgress();
    }""")
    assert page.evaluate('originalSearch===document.querySelector("#deck-search")&&document.activeElement===originalSearch')
    assert page.locator('#deck-search').input_value()=='Test'
    assert page.locator('[data-select]:visible').is_checked()
    assert page.locator('#select-visible-decks').inner_text()=='Deselect All'
    assert page.locator('.deck-tile:visible .deck-meta').inner_text().find('1/1 images')>=0
    assert page.evaluate('templatesReads')==0
    page.locator('[data-filter=work]').click()
    assert page.locator('.deck-tile:visible').count()==0
    assert page.get_by_text('No decks match your search.',exact=True).is_visible()
    page.locator('[data-filter=ready]').click()
    assert page.locator('.deck-tile:visible').count()==1
    assert not errors,errors
