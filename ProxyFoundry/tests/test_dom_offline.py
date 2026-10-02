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
    for name in ['diagnostics','work','ui','deletion','credits','backs','github-setup','artwork-files','artwork-review','render','frame-picker','setup','orders','templates','settings','deck','app']:
        text=(ROOT/'site'/(name+'.js')).read_text(encoding='utf-8')
        exports=re.findall(r'export\s+(?:async\s+)?(?:function|const|let|class)\s+([$\w]+)',text)
        text=re.sub(r"import\s+\{([^}]+)\}\s+from\s+'\./([^']+)\.js';",lambda m:'const {'+m[1]+'}=__mod_'+m[2].replace('-','_')+';',text)
        text=text.replace("await import('./ui.js')",'__mod_ui')
        text=re.sub(r'(?m)^export[ \t]+','',text)
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
        page.on('pageerror',lambda e:errors.append(str(e)));page.route('http://fixture.test/**',lambda route:route.fulfill(body=html,content_type='text/html'));page.goto('http://fixture.test/');page.add_style_tag(content=(ROOT/'site/styles.css').read_text(encoding='utf-8'))
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
          else if(path==='/api/setup/artwork-review')value={id:'artwork-fixture'};
          else if(path==='/api/jobs/artwork-fixture')value={state:'done',result:{needsReview:false,signature:'matched',items:[],inventory:[]}};
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


def artwork_helper(page,count=2,images=2,fallback=False):
    page.evaluate('''({count,images,fallback})=>{
      const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      window.review={signature:'fixture',items:Array.from({length:count},(_,i)=>({id:'card'+i,name:'Spirit '+i,selector:{name:'Spirit '+i},image,status:'missing',key:null,reason:'Missing artwork'})),inventory:Array.from({length:images},(_,i)=>({key:'file'+i,filename:'custom_'+i+'.png',image}))};
      window.openHelper=()=>__mod_artwork_review.openArtworkHelper(review,{deckId:__fixture.deck.id,settings:{source:{mode:'local',fallback}}});
      window.helperPromise=openHelper().then(result=>window.helperResult=result);
    }''',{'count':count,'images':images,'fallback':fallback})
    page.locator('#artwork-counts').wait_for()


def test_artwork_pairing_undo_finish_and_no_rendering(dom_page):
    page,errors=dom_page;artwork_helper(page)
    assert page.locator('#artwork-finish').is_disabled()
    assert not page.locator('#artwork-default-rest').is_visible()
    assert not page.locator('iframe').count()
    assert page.locator('[aria-label="Cards needing artwork"]').inner_text()=='Cards needing artwork'
    page.locator('[data-artwork-card="card0"]').click();page.locator('[data-artwork-file="file1"]').click()
    assert page.locator('[data-artwork-pair]').count()==1
    page.get_by_role('button',name='Undo artwork pairing for Spirit 0').click()
    assert page.locator('[data-artwork-pair]').count()==0
    for card,file in [('card0','file1'),('card1','file0')]:
        page.locator('[data-artwork-card="'+card+'"]').click();page.locator('[data-artwork-file="'+file+'"]').click()
    assert page.locator('#artwork-finish').is_enabled()
    page.screenshot(path=str(ROOT/'test-results/artwork-helper-desktop.png'))
    page.click('#artwork-finish');page.wait_for_function('window.helperResult!==undefined')
    assert page.evaluate('helperResult.changes')==[{'name':'Spirit 0','art':'custom_1.png'},{'name':'Spirit 1','art':'custom_0.png'}]
    assert not errors,errors


def test_artwork_cancel_resume_defaults_and_mobile(dom_page):
    page,errors=dom_page;artwork_helper(page,count=3,images=2,fallback=True)
    page.locator('[data-artwork-card="card0"]').click();page.locator('[data-artwork-file="file0"]').click()
    page.get_by_role('button',name='Back to setup',exact=True).click()
    page.wait_for_function('helperResult===null')
    page.evaluate('()=>{window.helperResult=undefined;window.helperPromise=openHelper().then(result=>window.helperResult=result);}')
    page.locator('[data-artwork-pair]').wait_for()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path=str(ROOT/'test-results/artwork-helper-mobile.png'))
    page.click('#artwork-default-rest');page.wait_for_function('helperResult!==undefined')
    assert page.evaluate('helperResult.defaults')==['card1','card2']
    assert not errors,errors


def test_artwork_large_inventory_limits_dom_and_search(dom_page):
    page,errors=dom_page;artwork_helper(page,count=100,images=5000)
    assert page.locator('[data-artwork-card]').count()==80
    assert page.locator('[data-artwork-file]').count()==60
    started=page.evaluate('performance.now()');page.get_by_role('searchbox',name='Find an artwork filename').fill('custom_4999')
    assert page.locator('[data-artwork-file]').count()==1
    assert page.evaluate('performance.now()')-started<1000
    assert not errors,errors


def test_artwork_file_merge_permissions_and_github_sha(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,original={version:1,cards:[{name:'Spirit',nickname:'Ghost',artist:'Me'}]},changes=[{name:'Spirit',art:'custom.png'}];
      let text=JSON.stringify(original),writes=0,permissions=0;
      const handle={queryPermission:async()=> 'prompt',requestPermission:async()=>{permissions++;return 'granted';},getFile:async()=>({text:async()=>text}),createWritable:async()=>({write:async value=>{text=typeof value==='string'?value:await value.text();writes++;},close:async()=>{},abort:async()=>{}})};
      await m.saveLocalData({file:handle,document:original},changes);
      let denied=false;try{await m.saveLocalData({file:{...handle,requestPermission:async()=> 'denied'}},changes);}catch(e){denied=true;}
      const calls=[],fetcher=async(url,opts)=>{calls.push({url,...opts});return opts.method==='PUT'?{ok:true}:{ok:true,status:200,json:async()=>({sha:'current',encoding:'base64',content:btoa(JSON.stringify(original))})};};
      const location=m.githubDataLocation('https://github.com/owner/cards/tree/main/deck');
      await m.saveGithubData(location,'private-test-token',changes,original,fetcher);
      let conflict=false;try{m.mergeDataDocument({version:1,cards:[{name:'Spirit',art:'changed.png'}]},changes,original);}catch(e){conflict=true;}
      await m.connectGithub(location.repo,'once',false);const onceStored=await m.sourceRecord('github:'+location.repo);await m.disconnectGithub(location.repo);
      const originalFetch=window.fetch;let uploads=0;const source={},progress=[];
      window.fetch=async()=>({ok:true,json:async()=>({stem:'spirit',id:'asset-'+(++uploads)})});
      const files=[new File(['a'],'Spirit.png'),new File(['b'],'spirit.jpg')];Object.defineProperty(files[0],'artworkPath',{value:'folder/Spirit.png'});
      const imported=await __mod_ui.uploadFolder(files,(done,total)=>progress.push([done,total]),source);window.fetch=originalFetch;
      let shaConflict=false;try{await m.saveGithubData(location,'test',changes,original,async(url,opts)=>opts.method==='PUT'?{ok:false,status:409}:{ok:true,status:200,json:async()=>({sha:'changed',encoding:'base64',content:btoa(JSON.stringify(original))})});}catch(error){shaConflict=error.message.includes('changed on GitHub');}
      return {local:JSON.parse(text),writes,permissions,denied,conflict,shaConflict,imported,names:source.localNames,progress,onceStored:!!onceStored,put:JSON.parse(calls[1].body),location,raw:m.githubDataLocation('https://raw.githubusercontent.com/owner/cards/main/deck/data.json')};
    }''')
    assert report['local']['cards'][0]=={'name':'Spirit','nickname':'Ghost','artist':'Me','art':'custom.png'}
    assert report['writes']==1 and report['permissions']==1 and report['denied'] and report['conflict']
    assert not report['onceStored'] and report['put']['sha']=='current'
    assert report['location']==report['raw']=={'repo':'owner/cards','branch':'main','path':'deck/data.json'}
    assert report['imported']=={'spirit':'asset-1','spirit__2':'asset-2'}
    assert report['names']=={'spirit':'folder/Spirit.png','spirit__2':'spirit.jpg'}
    assert report['progress']==[[1,2],[2,2]] and report['shaConflict']
    assert not errors,errors


def test_artwork_github_save_ui_remember_and_one_update(dom_page):
    page,errors=dom_page
    page.route('**/site/github-token-step-*.png',lambda route:route.fulfill(path=str(ROOT/'site'/route.request.url.rsplit('/',1)[-1]),content_type='image/png'))
    page.add_style_tag(content=(ROOT/'site/forge-theme.css').read_text(encoding='utf-8'))
    page.evaluate('''async()=>{
      window.savedGithub={version:1,cards:[{name:'Spirit',nickname:'Ghost'}]};window.githubWrites=0;
      const original=window.fetch;
      window.fetch=async(url,options={})=>{
        if(!String(url).startsWith('https://api.github.com/'))return original(url,options);
        if(options.method==='PUT'){window.savedGithub=JSON.parse(atob(JSON.parse(options.body).content));githubWrites++;return {ok:true};}
        return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'version-'+githubWrites,content:btoa(JSON.stringify(savedGithub))})};
      };
      await __mod_artwork_files.rememberGithub(__fixture.deck.id,'https://github.com/owner/cards/tree/main/deck',savedGithub);
      window.exportCards=[{name:'Spirit',scryfall:{id:'dc4e2134-f0c2-49aa-9ea3-ebf83af1445c',oracle_id:'6a7a9dff-ff9e-4005-a17f-6ea0c11c1d5a',scryfall_uri:'https://scryfall.com/card/tst/1/spirit'},faces:[{index:0,name:'Spirit'}]},{name:'Test creature',scryfall:{oracle_id:'b9ad70d0-7e71-4ec1-a39e-7d9363501322',scryfall_uri:'https://scryfall.com/card/tst/2/test-creature'},faces:[{index:0,name:'Test creature'}]}];
      window.openSave=art=>{window.savePromise=__mod_artwork_review.offerDataSave(__fixture.deck.id,[{name:'Spirit',art}],savedGithub,'',exportCards);};
      openSave('first.png');
    }''')
    page.get_by_role('button',name='Update data.json on GitHub',exact=True).wait_for()
    screenshot_dir=ROOT/'test-results';screenshot_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot_dir/'artwork-save-options-desktop.png'))
    page.get_by_role('button',name='Update data.json on GitHub',exact=True).click()
    guide=page.get_by_role('link',name='Open GitHub token setup')
    from urllib.parse import urlparse,parse_qs
    assert parse_qs(urlparse(guide.get_attribute('href')).query)=={'name':['BulkProxyForge'],'description':['Update data.json artwork choices'],'target_name':['owner'],'contents':['write'],'expires_in':['90']}
    assert guide.get_attribute('target')=='_blank'
    assert page.locator('.modal-body ol li').count()==5
    assert page.locator('.modal-body ol img').count()==5
    page.wait_for_function("[...document.querySelectorAll('.modal-body ol img')].every(image=>image.complete&&image.naturalWidth>0)")
    assert page.locator('.modal-body').get_by_text('Check owner/cards is listed',exact=True).count()==1
    assert page.get_by_text('Expiration: choose 90 days. Click an image to enlarge.',exact=True).is_visible()
    assert page.locator('.modal-body ol img').evaluate_all("images=>images.every((image,index)=>image.src.endsWith(`/site/github-token-step-${index+1}.png`))")
    assert page.get_by_role('button',name='Connect and update data.json',exact=True).is_disabled()
    page.screenshot(path=str(screenshot_dir/'artwork-github-guide-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('''()=>[...document.querySelectorAll('.modal-body input,.modal-body img,.modal-body .button')].filter(x=>x.getClientRects().length).every(x=>{const r=x.getBoundingClientRect(),p=x.closest('.modal-body').getBoundingClientRect();return r.left>=p.left&&r.right<=p.right+1;})''')
    page.screenshot(path=str(screenshot_dir/'artwork-github-guide-mobile.png'))
    page.locator('.modal-body ol img').first.click()
    enlarged=page.get_by_role('dialog',name='Choose Only select repositories, search for your repository, and check its box.',exact=True)
    assert enlarged.is_visible()
    assert enlarged.locator('img').get_attribute('src').endswith('/site/github-token-step-1.png')
    enlarged.get_by_role('button',name='Close',exact=True).click()
    assert not enlarged.count()
    page.get_by_role('button',name='Back to save options',exact=True).click()
    assert page.get_by_role('button',name='Download data.json',exact=True).is_visible()
    assert not guide.is_visible()
    page.get_by_role('button',name='Update data.json on GitHub',exact=True).click()
    page.get_by_role('textbox',name='GitHub connection token').fill('one-use-token')
    page.get_by_role('button',name='Connect and update data.json',exact=True).click()
    page.wait_for_function('githubWrites===1 && !document.querySelector(".modal")')
    assert page.get_by_text('Updated owner/cards/deck/data.json on main.',exact=True).is_visible()
    assert page.evaluate('async()=>!!await __mod_artwork_files.githubCredential("owner/cards")') is False
    page.evaluate('()=>{openSave("second.png");}')
    page.get_by_role('button',name='Update data.json on GitHub',exact=True).click()
    page.get_by_role('textbox',name='GitHub connection token').fill('remembered-token')
    page.get_by_role('checkbox',name='Remember access to update').check()
    page.get_by_role('button',name='Connect and update data.json',exact=True).click()
    page.wait_for_function('githubWrites===2 && !document.querySelector(".modal")')
    assert page.evaluate('async()=>await __mod_artwork_files.sourceRecord("github:owner/cards")')=='remembered-token'
    page.evaluate('()=>{openSave("third.png");}')
    page.get_by_role('button',name='Forget GitHub connection',exact=True).click()
    page.wait_for_function('document.querySelector("[role=status]")?.textContent==="GitHub connection forgotten." || [...document.querySelectorAll("[role=status]")].some(node=>node.textContent==="GitHub connection forgotten.")')
    assert page.evaluate('async()=>!!await __mod_artwork_files.githubCredential("owner/cards")') is False
    assert page.evaluate('savedGithub.cards[0]')=={'name':'Spirit','nickname':'Ghost','art':'second.png','oracle_id':'6a7a9dff-ff9e-4005-a17f-6ea0c11c1d5a','scryfall_url':'https://scryfall.com/card/tst/1/spirit'}
    assert page.evaluate('savedGithub.cards[1]')=={'name':'Test creature','oracle_id':'b9ad70d0-7e71-4ec1-a39e-7d9363501322','scryfall_url':'https://scryfall.com/card/tst/2/test-creature'}
    with page.expect_download() as download:page.get_by_role('button',name='Download data.json',exact=True).click()
    exported=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
    assert exported['cards'][0]['art']=='third.png'
    assert all(row.get('oracle_id') and row.get('scryfall_url') for row in exported['cards'])
    assert not errors,errors


def test_delete_cancels_generation_once_and_uses_latest_revision(dom_page):
    page,errors=dom_page
    page.evaluate('''()=>{
      const ui=__mod_ui,deck=__fixture.deck;window.deletionCalls=[];window.confirmations=0;
      __mod_deletion.resumeDeletions();window.addEventListener('pf-library-deletion',()=>__mod_app.route());
      const original=window.fetch;window.fetch=async(path,options={})=>{
        if(path.endsWith('/orders'))return {ok:true,text:async()=> '[]'};
        if(path.endsWith('/delete')){deletionCalls.push(JSON.parse(options.body));return {ok:true,text:async()=> '{}'};}
        return original(path,options);
      };
      window.generation=ui.work.begin({label:'Generate this deck',kind:'generation',resources:['deck:'+deck.id]});
      window.otherGeneration=ui.work.begin({label:'Other deck',kind:'generation',resources:['deck:other']});
      window.deletePromise=__mod_deletion.deleteDeck(deck);
    }''')
    page.get_by_role('button',name='Delete permanently',exact=True).click()
    page.wait_for_function('generation.controller.signal.aborted')
    assert page.evaluate('deletionCalls.length')==0
    assert not page.evaluate('otherGeneration.controller.signal.aborted')
    assert not page.get_by_text('Test deck',exact=True).count()
    assert page.get_by_role('button',name='Delete permanently',exact=True).count()==0
    page.evaluate('''()=>{__fixture.deck.revision=17;__mod_ui.work.finish(generation);}''')
    page.wait_for_function('deletionCalls.length===1')
    assert page.evaluate('deletionCalls[0].revision')==17
    page.evaluate('()=>__mod_ui.work.finish(otherGeneration)')
    assert not errors,errors


def test_general_browser_diagnostics_include_messages_and_download_snapshot(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      __mod_ui.toast('Saved deck');
      await __mod_ui.attempt(()=>{throw new Error('Deletion blocked example');});
      __mod_ui.errorBox(document.querySelector('#main'),'Missing custom image');
      const status=document.createElement('p');status.setAttribute('role','status');status.textContent='GitHub update failed example';document.querySelector('#main').append(status);
      console.warn('Warning example');await new Promise(resolve=>setTimeout(resolve,0));
      __mod_diagnostics.recordDiagnostic('example','github_pat_secretExample Bearer hiddenToken');
      const original=window.fetch;window.fetch=async(path,options)=>{window.diagnosticRequest={path,options};return {ok:true};};
      await __mod_diagnostics.diagnosticZipRequest('test-csrf');window.fetch=original;
      return {request:diagnosticRequest,stored:JSON.parse(localStorage.getItem('bulk-proxy-forge-browser-diagnostics'))};
    }''')
    payload=json.loads(report['request']['options']['body'])['browser']
    assert report['request']['path']=='/api/diagnostics.zip'
    assert report['request']['options']['headers']['X-Proxy-CSRF']=='test-csrf'
    assert report['request']['options']['method']=='POST'
    entries=payload['entries']
    assert any(e['kind']=='notification' and e['detail']=='Saved deck' for e in entries)
    assert any(e['kind']=='caught error' and 'Deletion blocked example' in e['detail'] for e in entries)
    assert any(e['kind']=='error notification' and e['detail']=='Deletion blocked example' for e in entries)
    assert any(e['kind']=='form error' and e['detail']=='Missing custom image' for e in entries)
    assert any(e['kind']=='console warn' and e['detail']=='Warning example' for e in entries)
    assert any(e['kind']=='displayed status' and e['detail']=='GitHub update failed example' for e in entries)
    assert entries[-1]['detail']=='[redacted credential] [redacted credential]'
    assert report['stored']['entries']==entries
    assert not errors,errors


@pytest.mark.parametrize('look',['Normal Look','Customize Look'])
def test_choose_look_routes_without_generating(dom_page,look):
    page,errors=dom_page
    page.evaluate('''()=>{
      window.importSettings=null;window.prematureGeneration=[];const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path==='/api/decks/import'){
          importSettings=JSON.parse(options.body).settings;
          __fixture.deck.settings={...__fixture.deck.settings,...importSettings};
          return {ok:true,text:async()=>JSON.stringify({id:'import-fixture'})};
        }
        if(path==='/api/jobs/import-fixture')return {ok:true,text:async()=>JSON.stringify({state:'done',kind:'Import deck',result:__fixture.deck})};
        if(path.includes('/prepare')||path.includes('/render-sessions'))prematureGeneration.push(path);
        return original(path,options);
      };
    }''')
    page.click('#import-deck');page.locator('.modal-body summary').click()
    page.locator('.modal-body textarea').fill('1 Test creature');page.click('#do-import')
    page.get_by_role('button',name=look,exact=True).click()
    if look=='Normal Look':
        page.locator('#card-search').wait_for()
        assert page.url.endswith('/cards') and page.locator('#save-setup').count()==0
        settings=page.evaluate('importSettings')
        assert settings['source']['mode']=='scryfall'
        assert all(value=='normal' for value in settings['templateRules'].values())
        assert settings['artist']=='' and not settings['allCardsTokens']
        assert page.locator('#generate-deck').is_visible()
    else:
        page.locator('#setup-state').wait_for()
        assert page.url.endswith('/setup')
    assert not page.evaluate('prematureGeneration')
    assert not errors,errors


@pytest.mark.parametrize('button',['generate-deck','save-generate'])
def test_setup_generation_buttons_persist_latest_changes_first(dom_page,button):
    page,errors=dom_page
    page.evaluate('''()=>{
      __fixture.deck.settings.symbols=Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)]));
      window.setupCalls=[];const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path.endsWith('/save')){setupCalls.push({kind:'save',artist:JSON.parse(options.body).settings.artist});await new Promise(resolve=>setTimeout(resolve,100));}
        if(path.endsWith('/prepare')){setupCalls.push({kind:'prepare',artist:__fixture.deck.settings.artist});return {ok:true,text:async()=>JSON.stringify({id:'prepare-fixture'})};}
        if(path==='/api/jobs/prepare-fixture')return {ok:true,text:async()=>JSON.stringify({state:'done',kind:'Prepare deck',result:__fixture.deck})};
        if(path==='/api/render-sessions'){setupCalls.push({kind:'render'});return {ok:true,text:async()=>JSON.stringify({targets:[],errors:[],cached:1})};}
        return original(path,options);
      };
      location.hash='#deck/'+__fixture.deck.id+'/setup';
    }''')
    page.locator('#deck-artist').fill('Latest edit')
    assert page.locator('#save-setup').count()==0
    assert page.locator('#save-generate').inner_text()=='Generate images'
    page.click('#'+button)
    page.wait_for_function('setupCalls.some(call=>call.kind==="render")')
    calls=page.evaluate('setupCalls')
    assert calls[0]=={'kind':'save','artist':'Latest edit'}
    assert next(call for call in calls if call['kind']=='prepare')['artist']=='Latest edit'
    assert not page.locator('.toast.error').count()
    assert not errors,errors



def test_setup_save_failure_blocks_generation_and_allows_retry(dom_page):
    page,errors=dom_page
    page.evaluate("""()=>{
      __fixture.deck.settings.symbols=Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)]));
      window.failSetupSave=true;window.prepareAttempts=0;const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path.endsWith('/save')&&failSetupSave)return {ok:false,status:500,text:async()=>JSON.stringify({error:'Test storage failure'})};
        if(path.endsWith('/prepare')){prepareAttempts++;return {ok:true,text:async()=>JSON.stringify({id:'retry-prepare'})};}
        if(path==='/api/jobs/retry-prepare')return {ok:true,text:async()=>JSON.stringify({state:'done',kind:'Prepare deck',result:__fixture.deck})};
        if(path==='/api/render-sessions')return {ok:true,text:async()=>JSON.stringify({targets:[],errors:[],cached:1})};
        return original(path,options);
      };
      location.hash='#deck/'+__fixture.deck.id+'/setup';
    }""")
    page.locator('#deck-artist').fill('Retry edit');page.click('#generate-deck')
    page.wait_for_function("document.querySelector('#setup-state')?.textContent.includes('Test storage failure')")
    assert page.evaluate('prepareAttempts')==0
    assert page.locator('#generate-deck').is_enabled() and page.locator('#save-generate').is_enabled()
    page.evaluate('failSetupSave=false');page.click('#save-generate')
    page.wait_for_function('prepareAttempts===1')
    assert page.evaluate('__fixture.deck.settings.artist')=='Retry edit'
    assert not errors,errors


def test_setup_navigation_persists_edits_without_confirmation(dom_page):
    page,errors=dom_page
    page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
    page.locator('#deck-artist').fill('Keep this edit')
    page.click('.topbar [data-nav=decks]');page.locator('#deck-search').wait_for()
    assert page.evaluate('__fixture.deck.settings.artist')=='Keep this edit'
    assert not errors,errors


def test_artwork_refresh_does_not_reuse_stale_images_or_pairs(dom_page):
    page,errors=dom_page;artwork_helper(page,count=1,images=1)
    page.get_by_role('button',name='Back to setup',exact=True).click()
    page.evaluate('''()=>{
      window.helperResult=undefined;
      window.helperPromise=__mod_artwork_review.openArtworkHelper(review,{deckId:__fixture.deck.id,settings:{source:{mode:'github',fallback:false}},onAdd:async()=>{
        review={...review,signature:'changed',inventory:[{...review.inventory[0],filename:'changed.png',identity:'new-image'}]};return review;
      }}).then(result=>window.helperResult=result);
    }''')
    page.locator('[data-artwork-card]').click();page.locator('[data-artwork-file]').click()
    page.get_by_role('button',name='Refresh GitHub folder',exact=True).click()
    page.locator('[data-artwork-file]').filter(has_text='changed.png').wait_for()
    assert page.locator('[data-artwork-pair]').count()==0
    assert page.locator('#artwork-finish').is_disabled()
    page.locator('[data-artwork-card]').click();page.locator('[data-artwork-file]').click();page.click('#artwork-finish')
    page.wait_for_function('helperResult!==undefined')
    assert page.evaluate('helperResult.changes[0].art')=='changed.png'
    assert not errors,errors

def test_offline_settings_and_mobile(dom_page):
    page,errors=dom_page
    page.click('.topbar [data-nav=settings]');page.check('#global-refresh')
    page.wait_for_function('window.__fixture.settings.refreshData === true')
    assert page.evaluate('window.__fixture.settings.refreshData') is True
    page.set_viewport_size({'width':390,'height':844});page.click('.topbar [data-nav=decks]');page.locator('.deck-tile').wait_for()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    assert not errors,errors


def test_library_initial_covers_and_backs_use_small_previews(dom_page):
    page,errors=dom_page
    page.evaluate("()=>{const deck=window.__fixture.deck;deck.cover='/api/assets/'+'a'.repeat(64);deck.settings.backAsset='b'.repeat(64);}")
    page.click('.topbar [data-nav=settings]');page.locator('#global-refresh').wait_for()
    page.click('.topbar [data-nav=decks]');page.locator('.deck-cover img').first.wait_for()
    assert page.locator('.deck-cover a img').get_attribute('src')=='/api/assets/'+'a'*64+'/thumbnail'
    assert page.locator('.deck-back-thumb').get_attribute('src')=='/api/assets/'+'b'*64+'/thumbnail'
    assert page.locator('.deck-back-thumb').get_attribute('loading')=='lazy'
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


@pytest.mark.parametrize('leave_during_import',[False,True],ids=['stay','navigate'])
def test_one_click_github_updates_source_choices_and_restores_on_reopen(dom_page,leave_during_import):
    page,errors=dom_page
    page.evaluate("""()=>{
      const fetch=window.fetch;
      window.fetch=async(path,opts={})=>{
        let value;
        if(path==='/api/setup/github-import')value={id:'github-fixture'};
        else if(path==='/api/jobs/github-fixture'){await new Promise(resolve=>setTimeout(resolve,200));value={state:'done',kind:'GitHub setup',message:'Done',done:1,total:1,result:{
          settings:{source:{mode:'github',githubFolder:'https://github.com/owner/cards/tree/main/deck/art',localFiles:{},fallback:false},
            symbols:Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)])),
            symbolsSource:{kind:'github',value:'https://github.com/owner/cards/tree/main/deck/set_symbols'},
            dataJsonSource:{kind:'github',value:'deck/data.json'},backAsset:null,backDesign:{mode:'default'},
            githubSetupFolder:'https://github.com/owner/cards/tree/main/deck'},
          cardData:[{name:'Test creature',nickname:'New name'}],summary:{art:'github',symbols:'folder',back:'default',data:1},warnings:[]}};}
        else return fetch(path,opts);
        return {ok:true,status:200,text:async()=>JSON.stringify(value)};
      };
      location.hash='#deck/'+window.__fixture.deck.id+'/setup';
    }""")
    page.locator('#github-setup-folder').fill('https://github.com/owner/cards/tree/main/deck')
    page.click('#github-setup-button')
    if leave_during_import:
        page.click('.topbar [data-nav=decks]');page.locator('#deck-search').wait_for()
        page.wait_for_function("window.__fixture.deck.settings.symbolsSource?.kind==='github'")
        page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
        page.locator('#setup-state').wait_for()
    else:
        page.wait_for_function("document.querySelector('#github-setup-status')?.classList.contains('success')")
    symbols=page.locator('#symbol-grid').locator('xpath=..')
    data=page.locator('#data-json-section')
    for panel in [symbols,data]:
        assert 'selected' in panel.get_by_role('button',name='From GitHub',exact=True).get_attribute('class')
        assert 'selected' not in panel.get_by_role('button',name='From Computer',exact=True).get_attribute('class')
    page.wait_for_function("() => document.querySelector('#setup-state')?.textContent==='Changes saved'")
    page.wait_for_function("window.__fixture.deck.settings.symbolsSource?.kind==='github'")
    page.evaluate("()=>{const root=document.querySelector('#setup-fields').parentElement;__mod_setup.renderSetup(root,window.__fixture.deck,()=>{});}")
    for panel in [symbols,data]:
        assert 'selected' in panel.get_by_role('button',name='From GitHub',exact=True).get_attribute('class')
    assert page.locator('#symbol-github-folder').input_value().endswith('/set_symbols')
    assert not errors,errors


def test_browser_diagnostics_include_image_timing_and_pending_previews(dom_page):
    import time
    page,errors=dom_page
    from test_browser import png
    def delayed_image(route):
        time.sleep(.2)
        route.fulfill(body=png(),content_type='image/png')
    page.route('http://fixture.test/slow-preview.png',delayed_image)
    page.evaluate("()=>{const image=document.createElement('img');image.src='/slow-preview.png';document.body.append(image);}")
    page.wait_for_function("__mod_diagnostics.browserDiagnosticReport().entries.some(entry=>entry.kind==='timing'&&entry.detail.includes('preview.image-request'))")
    timing=page.evaluate("JSON.parse(__mod_diagnostics.browserDiagnosticReport().entries.find(entry=>entry.kind==='timing'&&entry.detail.includes('slow-preview.png')).detail)")
    assert timing['seconds']>=.1 and timing['source']=='workspace'
    assert timing['detailedTimingAvailable'] and timing['transferBytes']>0
    page.evaluate("()=>{const image=document.createElement('img');image.src='/not-visible.png';image.loading='lazy';image.alt='Waiting art';image.style.marginTop='100000px';document.body.append(image);}")
    pending=page.evaluate('__mod_diagnostics.browserDiagnosticReport().pendingImages')
    assert any(image['label']=='Waiting art' and image['loading']=='lazy' for image in pending)
    assert not errors,errors


def test_export_references_cover_cards_token_variants_faces_and_printings(dom_page):
    page,errors=dom_page
    report=page.evaluate("""async()=>{
      const m=__mod_artwork_files,ids=['dc4e2134-f0c2-49aa-9ea3-ebf83af1445c','6a7a9dff-ff9e-4005-a17f-6ea0c11c1d5a','b9ad70d0-7e71-4ec1-a39e-7d9363501322','2bb2f9ed-6378-40c9-9170-976711919014'];
      const card=(name,id,url)=>({name,scryfall:{name,id,oracle_id:id,scryfall_uri:url},faces:[{index:0,name}]});
      const normal=card('Normal card',ids[0],'https://scryfall.com/card/tst/1/normal');
      const secondPrinting=structuredClone(normal);secondPrinting.scryfall.id=ids[3];secondPrinting.scryfall.scryfall_uri='https://scryfall.com/card/tst/2/normal';
      const cards=[normal,structuredClone(normal),secondPrinting,card('Spirit',ids[1],'https://scryfall.com/card/tst/3/spirit'),card('Spirit',ids[2],'https://scryfall.com/card/tst/4/spirit'),
        {name:'Day // Night',scryfall:{id:ids[3],oracle_id:ids[3],scryfall_uri:'https://scryfall.com/card/tst/5/day-night',card_faces:[{name:'Day'},{name:'Night'}]},faces:[{index:0,name:'Day'},{index:1,name:'Night'}]},
        {name:'Reference card',scryfall:{id:ids[3],scryfall_uri:'https://scryfall.com/card/tst/6/reference'},faces:[{index:0,name:'Reference card'}]}];
      const original={version:1,cards:[{name:'Normal card',nickname:'Hero',artist:'Me',flavor_text:'Keep this.'},{name:'Spirit',nickname:'Ghost'},{name:'Spirit',oracle_id:ids[1],art:'first.png'},{name:'Day',artist:'Day artist'},{name:'Other deck card',artist:'Someone'}]};
      const changes=[{name:'Spirit',oracle_id:ids[2],art:'second.png'}];
      const result=m.enrichDataDocument(m.mergeDataDocument(original,changes),cards,changes);
      let saved;
      const file={queryPermission:async()=> 'granted',getFile:async()=>({text:async()=>JSON.stringify(original)}),createWritable:async()=>({write:async text=>{saved=JSON.parse(text);},close:async()=>{},abort:async()=>{}})};
      await m.saveLocalData({file,document:original},changes,cards);
      return {result,saved,again:m.enrichDataDocument(result,cards)};
    }""")
    result=report['result'];assert result==report['saved']==report['again']
    assert len(result['cards'])==8
    normal=[row for row in result['cards'] if row['name']=='Normal card']
    assert len(normal)==2 and all(row['nickname']=='Hero' and row['artist']=='Me' and row['flavor_text']=='Keep this.' for row in normal)
    assert len({row['scryfall_id'] for row in normal})==2 and len({row['scryfall_url'] for row in normal})==2
    spirits=[row for row in result['cards'] if row['name']=='Spirit']
    assert len(spirits)==2 and {row['art'] for row in spirits}=={'first.png','second.png'}
    assert all(row['nickname']=='Ghost' and row['oracle_id'] for row in spirits)
    day=next(row for row in result['cards'] if row['name']=='Day');night=next(row for row in result['cards'] if row['name']=='Night')
    assert day['oracle_id']==night['oracle_id'] and day['artist']=='Day artist'
    reference=next(row for row in result['cards'] if row['name']=='Reference card')
    assert reference['scryfall_id'] and 'oracle_id' not in reference
    assert result['cards'][0]=={'name':'Other deck card','artist':'Someone'}
    from foundry.card_data import parse_document
    assert parse_document(json.dumps(result).encode())==result['cards']
    assert not errors,errors


def test_export_reference_enrichment_uses_indexed_lookup(dom_page):
    page,errors=dom_page
    report=page.evaluate("""()=>{
      const cards=Array.from({length:5000},(_,index)=>({name:'Card '+index,scryfall:{oracle_id:'00000000-0000-4000-8000-'+String(index).padStart(12,'0'),scryfall_uri:'https://scryfall.com/card/tst/'+index},faces:[{index:0,name:'Card '+index}]}));
      const original={version:1,cards:cards.map(card=>({name:card.name,artist:'Artist'}))};
      const start=performance.now(),result=__mod_artwork_files.enrichDataDocument(original,cards);
      return {seconds:(performance.now()-start)/1000,count:result.cards.length,last:result.cards.at(-1)};
    }""")
    assert report['count']==5000 and report['last']['oracle_id'].endswith('000000004999')
    assert report['last']['artist']=='Artist' and report['seconds']<3
    assert not errors,errors