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
    for name in ['diagnostics','generation-progress','work','ui','metadata','deletion','credits','backs','github-setup','artwork-files','art-variants','artwork-review','tokens','native-render-pool','review-zip','review-export','render','frame-picker','setup','orders','templates','settings','deck','batch-review-flow','batch-review','app']:
        text=(ROOT/'site'/(name+'.js')).read_text(encoding='utf-8')
        exports=re.findall(r'export\s+(?:async\s+)?(?:function|const|let|class)\s+([$\w]+)',text)
        text=re.sub(r"import\s+\{([^}]+)\}\s+from\s+'\./([^']+)\.js';",lambda m:'const {'+m[1]+'}=__mod_'+m[2].replace('-','_')+';',text)
        text=text.replace("await import('./ui.js')",'__mod_ui').replace('import.meta.url','document.baseURI')
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
          else if(path==='/api/decks/manifest')value={id:'list-fixture'};
          else if(path==='/api/jobs/list-fixture')value={state:'done',result:{name:'Test deck',rows:[{source:'Test creature',name:'Test creature',quantity:2,section:'mainboard'}]}};
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

@pytest.mark.parametrize('treatment',['card','deck','natural','ordinary'])
def test_inspector_template_choices_follow_token_treatment(dom_page,treatment):
    page,errors=dom_page
    page.evaluate('''treatment=>{
      const deck=__fixture.deck,card=deck.cards[0];
      card.scryfall.type_line='Legendary Creature — Elf';card.faces[0].group='legendary';
      if(treatment==='card')card.tokenSpec={};
      if(treatment==='deck')deck.settings.allCardsTokens=true;
      if(treatment==='natural')card.faces[0].group='token';
      card.faces[0].templateOverride='normal';
      window.templateWrites=[];const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path.includes('/cards/')&&options.body)templateWrites.push(JSON.parse(options.body));
        return original(path,options);
      };
    }''',treatment)
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    choices=page.locator('#face-template option').evaluate_all('(options)=>options.map(option=>option.value)')
    if treatment=='ordinary':
        assert 'normal' in choices and 'token-classic' not in choices
    else:
        assert {'','auto','token-classic','token-full-art','token-borderless','godzilla-card'}==set(choices)
        assert page.locator('#face-template').input_value()==''
        assert page.locator('#face-template').evaluate('select=>select.selectedIndex')==0
        page.locator('#face-template').evaluate("select=>select.closest('details').open=true")
        page.locator('#face-template').select_option('token-classic')
        page.click('#save-card')
        page.wait_for_function("templateWrites.some(patch=>patch.templateOverride==='token-classic')")
    assert not errors,errors


@pytest.mark.parametrize('failed',[False,True],ids=['complete','unavailable'])
def test_refresh_deck_cards_reloads_original_source_and_blocks_generation(dom_page,failed):
    page,errors=dom_page
    page.evaluate('''failed=>{
      __fixture.deck.importedSource='https://scryfall.com/@you/decks/33333333-3333-4333-8333-333333333333';
      __fixture.deck.includeOutside=false;window.refreshPayload=null;window.renderCalls=0;
      const original=window.fetch,reply=value=>({ok:true,text:async()=>JSON.stringify(value)});
      window.fetch=async(path,options={})=>{
        if(path.endsWith('/refresh')){refreshPayload=JSON.parse(options.body);return reply({id:'refresh-list'});}
        if(path==='/api/jobs/refresh-list'){
          await new Promise(resolve=>window.finishRefresh=resolve);
          if(failed)return reply({state:'failed',error:'Original deck unavailable',message:'Original deck unavailable'});
          __fixture.deck.cards[0].quantity=3;__fixture.deck.summary.cards=3;__fixture.deck.revision++;
          return reply({state:'done',result:{deck:__fixture.deck,changes:{added:[],removed:[],quantityChanged:[{name:'Test creature',before:2,after:3}],moved:[],retained:1,local:0}}});
        }
        if(path.startsWith('/api/render-sessions'))renderCalls++;
        return original(path,options);
      };
    }''',failed)
    page.locator('.deck-tile').click();page.click('#deck-menu');page.get_by_role('button',name='Refresh deck cards',exact=True).click()
    assert page.get_by_label('Original deck link',exact=True).input_value()==page.evaluate('__fixture.deck.importedSource')
    assert page.get_by_text('Include Outside the Game cards',exact=True).count()==0
    page.click('#refresh-deck-cards');page.wait_for_function('typeof finishRefresh==="function"')
    assert page.locator('#generate-deck').is_disabled()
    assert page.get_by_role('dialog',name='Refresh deck cards',exact=True).count()==0
    assert page.locator('#activity').is_visible()
    assert page.evaluate('refreshPayload.source')==page.evaluate('__fixture.deck.importedSource')
    assert page.evaluate('Object.hasOwn(refreshPayload,"includeOutside")') is False
    page.evaluate('finishRefresh()')
    if failed:
        page.locator('#activity-title').filter(has_text='Original deck unavailable').wait_for()
        assert page.evaluate('__fixture.deck.cards[0].quantity')==2
    else:
        page.locator('#activity-title').filter(has_text='1 matching cards kept').wait_for()
        assert page.locator('.quantity-pill').inner_text()=='3×'
    assert page.locator('#generate-deck').is_enabled()
    assert page.evaluate('renderCalls')==0 and not errors,errors


def test_make_all_tokens_unchecks_and_saves_flavor_text_without_forcing_it_off_on_reopen(dom_page):
    page,errors=dom_page
    page.locator('.deck-tile').click();page.click('[data-tab=setup]')
    assert page.locator('#show-flavor-text').is_checked()
    page.locator('#all-cards-tokens').check()
    assert not page.locator('#show-flavor-text').is_checked()
    page.wait_for_function('__fixture.deck.settings.allCardsTokens&&__fixture.deck.settings.showFlavorText===false')
    page.locator('#show-flavor-text').check()
    page.wait_for_function('__fixture.deck.settings.showFlavorText===true')
    page.click('[data-tab=cards]');page.click('[data-tab=setup]')
    assert page.locator('#all-cards-tokens').is_checked() and page.locator('#show-flavor-text').is_checked()
    assert not errors,errors


def test_individual_token_flavor_control_can_reenable_flavor_after_conversion(dom_page):
    page,errors=dom_page
    page.evaluate('''()=>{
      const card=__fixture.deck.cards[0];card.tokenSpec={nonlegendary:true};
      card.faces[0].showFlavorText=false;card.faces[0].semanticOverrides={flavor_text:'Imported flavor'};
      const original=window.fetch;window.flavorChanges=[];
      window.fetch=(path,options={})=>{
        if(path.includes('/cards/')&&options.body)flavorChanges.push(JSON.parse(options.body));
        return original(path,options);
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.locator('#remove-flavor').evaluate('input=>input.closest("details").open=true')
    assert page.locator('#remove-flavor').is_checked()
    page.locator('#remove-flavor').uncheck();page.click('#save-card')
    page.wait_for_function('flavorChanges.some(patch=>patch.showFlavorText===true)')
    assert not errors,errors


def test_offline_deck_controls_and_templates(dom_page):
    page,errors=dom_page
    page.locator('.deck-tile').click();page.locator('[data-card]').click();page.fill('#card-qty','4');page.click('#save-card')
    page.wait_for_function("document.querySelector('.quantity-pill')?.textContent==='4×'")
    page.locator('.page-head h1').click();page.locator('.page-head input').fill('Edited deck');page.locator('.page-head input').press('Enter')
    page.wait_for_function("document.querySelector('h1')?.textContent==='Edited deck'")
    page.click('.topbar [data-nav=templates]');page.click('#new-template');page.fill('#template-name','My frame');page.click('#save-template');page.get_by_text('My frame',exact=True).wait_for()
    assert not errors,errors


@pytest.mark.parametrize('flow',['artwork-cancel','artwork-finish','cached-cancel','cached-confirm','render-failure'])
def test_single_card_generation_hands_off_dialogs_and_restores_editor(dom_page,flow):
    page,errors=dom_page
    page.evaluate('''flow=>{
      const deck=__fixture.deck,card=deck.cards[0],face=card.faces[0],cached=flow.startsWith('cached');
      const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      deck.settings.source={mode:cached?'scryfall':'local',fallback:true,localFiles:{}};
      deck.status='prepared';face.compiled={renderKey:'before',render:{asset_id:'a'.repeat(64),url:image}};
      card.scryfall.image_uris={art_crop:image};
      window.singleRenderCalls=[];const original=window.fetch;
      const reply=value=>({ok:true,status:200,text:async()=>JSON.stringify(value)});
      window.fetch=async(path,options={})=>{
        const data=options.body?JSON.parse(options.body):{};
        if(path.endsWith('/cards/'+card.id+'/prepare')){
          if(!cached)delete face.compiled.render;
          return reply({id:'single-prepare'});
        }
        if(path==='/api/jobs/single-prepare')return reply({state:'done',result:deck});
        if(path.includes('/cards/')&&data.semanticOverrides)face.semanticOverrides=data.semanticOverrides;
        if(path==='/api/setup/artwork-review')return reply({id:'single-artwork'});
        if(path==='/api/jobs/single-artwork')return reply({state:'done',result:{
          needsReview:true,signature:'new-artwork',items:[{id:face.id,cardId:card.id,name:card.name,selector:{name:card.name},image,status:'missing',key:null,reason:'Choose artwork'}],inventory:[]}});
        if(path==='/api/render-sessions/card'){
          singleRenderCalls.push(data);
          if(flow==='render-failure')return {ok:false,status:500,text:async()=>JSON.stringify({error:'Card render request failed'})};
          return reply({targets:[],errors:[],cached:1});
        }
        if(path==='/api/render-diagnostic')return reply({});
        return original(path,options);
      };
    }''',flow)
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.get_by_role('button',name='Show back side').click()
    page.fill('#card-qty','3')
    page.locator('#nickname-override').evaluate("input=>input.closest('details').open=true")
    page.fill('#nickname-override','Keep this nickname')
    page.evaluate("window.originalInspector=document.querySelector('#generate-card').closest('.modal')")
    page.click('#generate-card')
    if flow.startswith('cached'):
        page.get_by_role('dialog',name='This card already matches the cached render.',exact=True).wait_for()
        if flow=='cached-cancel':page.click('#modal-close')
        else:page.click('#confirm-yes')
    else:
        page.get_by_role('dialog',name='Match your artwork',exact=True).wait_for()
        if flow=='artwork-cancel':page.click('#artwork-cancel')
        else:page.click('#artwork-default-rest')
    page.wait_for_function("!originalInspector.isConnected&&document.querySelector('#generate-card')?.disabled===false")
    assert page.locator('#card-qty').input_value()=='3'
    assert page.locator('#nickname-override').input_value()=='Keep this nickname'
    assert page.locator('#inspector-image').get_attribute('alt')=='Test creature back'
    assert page.locator('.modal').count()==1 and page.locator('#generation-screen').count()==0
    expected=0 if flow.endswith('cancel') else 1
    assert page.evaluate('singleRenderCalls.length')==expected
    if flow=='cached-confirm':assert page.evaluate('singleRenderCalls[0].force') is True
    toasts=page.locator('#toast-host').inner_text()
    assert 'Complete the current dialog' not in toasts
    if flow=='render-failure':assert 'Card render request failed' in toasts
    assert not errors,errors


def artwork_helper(page,count=2,images=2,fallback=False):
    page.evaluate('''({count,images,fallback})=>{
      const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      window.review={signature:'fixture',items:Array.from({length:count},(_,i)=>({id:'card'+i,name:'Spirit '+i,selector:{name:'Spirit '+i},image,status:'missing',key:null,reason:'Missing artwork'})),inventory:Array.from({length:images},(_,i)=>({key:'file'+i,filename:'custom_'+i+'.png',image}))};
      window.openHelper=()=>__mod_artwork_review.openArtworkHelper(review,{deckId:__fixture.deck.id,settings:{source:{mode:'local',fallback}}});
      window.helperResult=undefined;window.helperPromise=openHelper().then(result=>window.helperResult=result);
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


def test_required_artwork_pairing_rejects_dismissal_and_supports_defaults_mobile(dom_page):
    page,errors=dom_page;artwork_helper(page,count=3,images=2,fallback=True)
    page.locator('[data-artwork-card="card0"]').click();page.locator('[data-artwork-file="file0"]').click()
    assert not page.locator('#modal-close').is_visible()
    assert not page.get_by_role('button',name='Back to setup',exact=True).count()
    page.keyboard.press('Escape')
    page.locator('.modal-backdrop').dispatch_event('click')
    assert page.evaluate('window.helperResult===undefined')
    assert page.locator('[data-artwork-pair]').count()==1
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
      const m=__mod_artwork_files,original={version:1,artist:'Deck Artist',cards:[{name:'Spirit',nickname:'Ghost',artist:'Me'}]},changes=[{name:'Spirit',art:'custom.png'}];
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
      let shaConflict=false;try{await m.saveGithubData(location,'test',changes,original,async(url,opts)=>opts.method==='PUT'?{ok:false,status:409}:{ok:true,status:200,json:async()=>({sha:'changed',encoding:'base64',content:btoa(JSON.stringify(original))})});}catch(error){shaConflict=error.message.includes('kept changing on GitHub');}
      return {local:JSON.parse(text),writes,permissions,denied,conflict,shaConflict,imported,names:source.localNames,progress,onceStored:!!onceStored,put:JSON.parse(calls[1].body),location,raw:m.githubDataLocation('https://raw.githubusercontent.com/owner/cards/main/deck/data.json')};
    }''')
    assert report['local']['cards'][0]=={'name':'Spirit','nickname':'Ghost','artist':'Me','art':'custom.png'}
    assert report['local']['artist']=='Deck Artist'
    assert report['writes']==1 and report['permissions']==1 and report['denied'] and report['conflict']
    assert not report['onceStored'] and report['put']['sha']=='current'
    assert report['location']==report['raw']=={'repo':'owner/cards','branch':'main','path':'deck/data.json'}
    assert report['imported']=={'spirit':'asset-1','spirit__2':'asset-2'}
    assert report['names']=={'spirit':'folder/Spirit.png','spirit__2':'spirit.jpg'}
    assert report['progress']==[[1,2],[2,2]] and report['shaConflict']
    assert not errors,errors


def test_github_save_refreshes_sha_and_merges_unrelated_changes_on_retry(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,location=m.githubDataLocation('https://github.com/owner/cards/tree/main/deck');
      const before={version:1,cards:[{name:'Spirit',oracle_text:'Flying',art:'old.png'}]};
      const calls=[];let reads=0,writes=0,saved;
      const fetcher=async(url,opts)=>{
        calls.push({url,cache:opts.cache,method:opts.method||'GET'});
        if(opts.method==='PUT'){
          writes++;saved=JSON.parse(opts.body);
          return writes===1?{ok:false,status:409}:{ok:true,status:200};
        }
        reads++;
        const current=structuredClone(before);if(reads>1)current.cards[0].art='new.png';
        return {ok:true,status:200,json:async()=>({sha:reads===1?'stale-sha':'fresh-sha',encoding:'base64',content:btoa(JSON.stringify(current))})};
      };
      const result=await m.saveGithubData(location,'test-only',[{name:'Spirit',oracle_text:'Lifelink'}],before,fetcher);
      return {calls,reads,writes,saved,result};
    }''')
    assert report['reads']==report['writes']==2
    assert report['saved']['sha']=='fresh-sha'
    assert report['result']['cards'][0]=={'name':'Spirit','oracle_text':'Lifelink','art':'new.png'}
    reads=[call for call in report['calls'] if call['method']=='GET']
    assert all(call['cache']=='no-store' for call in reads)
    assert len({call['url'] for call in reads})==2
    assert not errors,errors


def test_github_save_retry_preserves_a_concurrent_rules_edit(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,location=m.githubDataLocation('https://github.com/owner/cards/tree/main/deck');
      const before={version:1,cards:[{name:'Spirit',oracle_text:'Flying'}]};
      let reads=0,writes=0,message='';
      const fetcher=async(url,opts)=>{
        if(opts.method==='PUT'){writes++;return {ok:false,status:409};}
        reads++;const current=structuredClone(before);
        if(reads>1)current.cards[0].oracle_text='Haste';
        return {ok:true,status:200,json:async()=>({sha:'sha-'+reads,encoding:'base64',content:btoa(JSON.stringify(current))})};
      };
      try{await m.saveGithubData(location,'test-only',[{name:'Spirit',oracle_text:'Lifelink'}],before,fetcher);}
      catch(error){message=error.message;}
      return {reads,writes,message};
    }''')
    assert report['reads']==2 and report['writes']==1
    assert 'rules text changed' in report['message']
    assert not errors,errors


def test_github_save_limits_version_retries_and_does_not_retry_other_errors(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,location=m.githubDataLocation('https://github.com/owner/cards/tree/main/deck');
      const before={version:1,cards:[]};
      const run=async status=>{
        let reads=0,writes=0,message='';
        const fetcher=async(url,opts)=>{
          if(opts.method==='PUT'){writes++;return {ok:false,status};}
          reads++;return {ok:true,status:200,json:async()=>({sha:'sha-'+reads,encoding:'base64',content:btoa(JSON.stringify(before))})};
        };
        try{await m.saveGithubData(location,'test-only',[{name:'Spirit',oracle_text:'Flying'}],before,fetcher);}
        catch(error){message=error.message;}
        return {reads,writes,message};
      };
      return {busy:await run(409),denied:await run(403)};
    }''')
    assert report['busy']['reads']==report['busy']['writes']==3
    assert 'Try Save again' in report['busy']['message']
    assert report['denied']['reads']==report['denied']['writes']==1
    assert '(403)' in report['denied']['message']
    assert not errors,errors


def test_card_rules_editor_saves_data_json_to_github(dom_page):
    page,errors=dom_page
    page.evaluate('''async()=>{
      const F=__fixture;
      F.deck.cards[0].faces[0].semanticOverrides={oracle_text:'Vigilance'};
      F.deck.settings={...F.deck.settings,dataJsonSource:{kind:'github',value:'deck/data.json'},githubSetupFolder:'https://github.com/owner/cards/tree/main/deck'};
      window.rulesDocument={version:1,artist:'Existing Artist',cards:[{name:'Test creature',nickname:'A Hero',art:'keep.png',oracle_text:'Vigilance'}]};
      window.rulesAttempts=0;
      await __mod_artwork_files.rememberGithub(F.deck.id,F.deck.settings.githubSetupFolder,rulesDocument);
      await __mod_artwork_files.connectGithub('owner/cards','test-only',false);
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(String(url).startsWith('https://api.github.com/')){
          if(opts.method==='PUT'){
            if(++rulesAttempts===1)return {ok:false,status:409};
            window.rulesPut=JSON.parse(opts.body);window.rulesDocument=JSON.parse(atob(rulesPut.content));return {ok:true};
          }
          return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'current-sha',content:btoa(JSON.stringify(rulesDocument))})};
        }
        if(String(url).includes('/cards/')&&opts.body){
          const patch=JSON.parse(opts.body);
          if(patch.semanticOverrides){
            F.deck.cards[0].faces[0].semanticOverrides=patch.semanticOverrides;
          }
        }
        return original(url,opts);
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','Flying\n{T}: Draw a card.')
    assert page.locator('#save-rules-data').count()==0
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('window.rulesPut && __fixture.deck.settings.dataJsonSource.value.startsWith("https:") && !document.querySelector(".modal")')
    data=page.evaluate('rulesDocument')
    assert data['artist']=='Existing Artist'
    assert data['cards'][0]['oracle_text']=='Flying\n{T}: Draw a card.'
    assert data['cards'][0]['nickname']=='A Hero' and data['cards'][0]['art']=='keep.png'
    assert page.evaluate('rulesPut.sha')=='current-sha'
    assert page.evaluate('__fixture.deck.settings.dataJsonSource.value')=='https://github.com/owner/cards/blob/main/deck/data.json'
    assert page.evaluate('rulesPut.branch')=='main'
    assert page.evaluate('rulesAttempts')==2
    assert not errors,errors


@pytest.mark.parametrize('target',['github','local','download'])
def test_art_approval_updates_original_data_or_offers_download(dom_page,target):
    page,errors=dom_page
    page.evaluate('''async target=>{
      const F=__fixture,face=F.deck.cards[0].faces[0],m=__mod_artwork_files;
      const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      F.deck.status='prepared';face.compiled={renderKey:'current-render',contentRenderKey:'a'.repeat(64),crop:{warning:true},render:{url:image}};
      window.approvalDocument={version:1,artist:'Keep artist',cards:[{name:'Test creature',nickname:'Keep name',art:'keep.png'},{name:'Other deck card',artist:'Other artist'}]};
      window.approvalWrites=0;window.renderRequests=0;
      const original=window.fetch;
      if(target==='github'){
        const url='https://github.com/owner/cards/blob/main/deck/data.json';F.deck.settings.dataJsonSource={kind:'github',value:url};
        await m.rememberGithub(F.deck.id,url,structuredClone(approvalDocument));await m.connectGithub('owner/cards','test-only',false);
      }
      if(target==='local'){
        const file={queryPermission:async()=> 'granted',getFile:async()=>({text:async()=>JSON.stringify(approvalDocument)}),
          createWritable:async()=>({write:async text=>{approvalWrites++;approvalDocument=JSON.parse(text);},close:async()=>{},abort:async()=>{}})};
        window.approvalRecord={file,document:structuredClone(approvalDocument)};
        const get=IDBObjectStore.prototype.get,put=IDBObjectStore.prototype.put,key='deck:'+F.deck.id;
        IDBObjectStore.prototype.get=function(name){const request=get.call(this,name);if(name===key)Object.defineProperty(request,'result',{get:()=>approvalRecord});return request;};
        IDBObjectStore.prototype.put=function(value,name){if(name===key){approvalRecord=value;return put.call(this,{document:value.document},name);}return put.call(this,value,name);};
      }
      window.fetch=async(url,options={})=>{
        if(String(url).startsWith('https://api.github.com/')){
          if(options.method==='PUT'){approvalWrites++;window.approvalPut=JSON.parse(options.body);approvalDocument=JSON.parse(atob(approvalPut.content));return {ok:true,status:200};}
          return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'current-version',content:btoa(JSON.stringify(approvalDocument))})};
        }
        if(String(url).startsWith('/api/render-sessions'))renderRequests++;
        if(String(url).includes('/cards/')&&options.body){
          const data=JSON.parse(options.body);
          if(data.acceptWarning){face.acceptedWarningKey=data.renderKey;face.acceptedArt=['a'.repeat(64)];F.deck.cardData=[{name:'Test creature',accepted_art:face.acceptedArt}];}
        }
        return original(url,options);
      };
    }''',target)
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.get_by_role('button',name='It Looks Fine',exact=True).click()
    if target=='download':
        page.get_by_role('dialog',name='Save artwork approval',exact=True).wait_for()
        with page.expect_download() as item:page.get_by_role('button',name='Download data.json',exact=True).click()
        document=json.loads(Path(item.value.path()).read_text(encoding='utf-8'))
    else:
        page.wait_for_function('approvalWrites===1&&document.querySelector("#generate-card")?.disabled===false')
        document=page.evaluate('approvalDocument')
        assert document['artist']=='Keep artist'
        current=next(entry for entry in document['cards'] if entry['name']=='Test creature')
        assert current['nickname']=='Keep name' and current['art']=='keep.png'
        assert next(entry for entry in document['cards'] if entry['name']=='Other deck card')=={'name':'Other deck card','artist':'Other artist'}
        if target=='github':assert page.evaluate('approvalPut.sha')=='current-version'
    assert next(entry for entry in document['cards'] if entry['name']=='Test creature')['accepted_art']==['a'*64]
    assert page.evaluate('renderRequests')==0
    assert not page.get_by_role('button',name='It Looks Fine',exact=True).count()
    assert not errors,errors


@pytest.mark.parametrize('target',['github','download'])
def test_bulk_art_approval_confirms_whole_deck_and_saves_once(dom_page,target):
    page,errors=dom_page
    page.evaluate('''async target=>{
      const F=__fixture,first=F.deck.cards[0],image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      const second=structuredClone(first);second.id='bulk-other-card';second.name='Other card';second.scryfall.name='Other card';
      second.faces=[0,1].map(index=>({...structuredClone(first.faces[0]),id:'bulk-face-'+index,index,name:'Other '+index}));
      const broken=structuredClone(first);broken.id='bulk-broken-card';broken.name='Broken card';broken.faces[0].id='bulk-broken-face';broken.faces[0].error='Image missing';
      F.deck.cards=[first,second,broken];F.deck.status='prepared';F.deck.summary={cards:3,faces:4,rendered:3,warnings:3,errors:1};
      let index=0;
      for(const card of [first,second])for(const face of card.faces){index++;face.compiled={renderKey:'render-'+index,contentRenderKey:String(index).repeat(64),crop:{warning:true},render:{url:image}};}
      window.bulkCalls=0;window.bulkWrites=0;window.bulkDocument={version:1,artist:'Keep artist',cards:[{name:'Test creature',nickname:'Keep name'}]};
      if(target==='github'){
        const url='https://github.com/owner/cards/blob/main/deck/data.json';F.deck.settings.dataJsonSource={kind:'github',value:url};
        await __mod_artwork_files.rememberGithub(F.deck.id,url,structuredClone(bulkDocument));await __mod_artwork_files.connectGithub('owner/cards','test-only',false);
      }
      const original=window.fetch;
      window.fetch=async(url,options={})=>{
        if(String(url).endsWith('/accept-art')){
          bulkCalls++;window.bulkPatch=JSON.parse(options.body);await new Promise(resolve=>window.releaseBulk=resolve);
          const changes=[];
          for(const row of bulkPatch.faces){
            const card=F.deck.cards.find(card=>card.id===row.cardId),face=card.faces.find(face=>face.id===row.faceId);
            face.acceptedWarningKey=row.renderKey;face.acceptedArt=[face.compiled.contentRenderKey];changes.push({name:face.name,accepted_art:face.acceptedArt});
          }
          F.deck.cardData=changes;F.deck.summary.warnings=0;F.deck.revision++;
          return {ok:true,status:200,text:async()=>JSON.stringify({deck:F.deck,changes})};
        }
        if(String(url).startsWith('https://api.github.com/')){
          if(options.method==='PUT'){bulkWrites++;bulkDocument=JSON.parse(atob(JSON.parse(options.body).content));return {ok:true,status:200};}
          return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'current-version',content:btoa(JSON.stringify(bulkDocument))})};
        }
        return original(url,options);
      };
    }''',target)
    page.locator('.deck-tile').click()
    assert page.locator('#approve-all-art').count()==0
    page.locator('[data-card-filter=attention]').click()
    page.locator('#card-search').fill('Test creature')
    page.locator('#approve-all-art').click()
    confirmation=page.get_by_role('dialog',name='Approve all flagged artwork?',exact=True)
    assert 'looked at every card in this deck' in confirmation.inner_text()
    assert '3 flagged card faces' in confirmation.inner_text()
    assert 'hidden by your search' in confirmation.inner_text()
    page.locator('#modal-close').click()
    assert page.evaluate('bulkCalls')==0
    page.locator('#approve-all-art').click();page.locator('#confirm-yes').click()
    page.wait_for_function('typeof releaseBulk==="function"')
    assert page.locator('#approve-all-art').is_disabled()
    assert page.locator('#approve-all-art').get_attribute('aria-pressed')=='true'
    assert page.locator('#generate-deck').is_disabled()
    page.evaluate('releaseBulk()')
    if target=='download':
        page.get_by_role('dialog',name='Save artwork approvals',exact=True).wait_for()
        with page.expect_download() as download:page.get_by_role('button',name='Download data.json',exact=True).click()
        document=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
    else:
        page.wait_for_function('bulkWrites===1')
        document=page.evaluate('bulkDocument')
        assert document['artist']=='Keep artist' and document['cards'][0]['nickname']=='Keep name'
    page.wait_for_function('!document.querySelector("#approve-all-art")')
    assert page.evaluate('bulkCalls')==1
    assert len([entry for entry in document['cards'] if entry.get('accepted_art')])==3
    assert page.evaluate('__fixture.deck.cards[2].faces[0].error')=='Image missing'
    assert not errors,errors


def test_card_save_offers_connection_or_download_without_a_source(dom_page):
    page,errors=dom_page
    page.evaluate('''()=>{
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(String(url).includes('/cards/')&&opts.body){
          const patch=JSON.parse(opts.body);
          if(patch.semanticOverrides){
            const face=__fixture.deck.cards[0].faces[0];
            face.semanticOverrides=patch.semanticOverrides;face.rulesOverrideLocal=true;
          }
        }
        return original(url,opts);
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','Flying')
    page.get_by_role('button',name='Save',exact=True).click()
    page.get_by_text('Connect or download data.json',exact=True).wait_for()
    assert page.get_by_role('button',name='Connect GitHub',exact=True).is_visible()
    assert page.get_by_label('GitHub data.json or folder link').is_visible()
    with page.expect_download() as download:
        page.get_by_role('button',name='Download data.json',exact=True).click()
    data=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
    assert data['cards'][0]['oracle_text']=='Flying'
    page.wait_for_function('!document.querySelector(".modal")')
    page.locator('[data-card]').click()
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('!document.querySelector(".modal")')
    assert not errors,errors


def test_card_save_connects_github_then_uses_that_connection(dom_page):
    page,errors=dom_page
    page.evaluate('''()=>{
      window.rulesDocument={version:1,cards:[]};window.rulesWrites=0;
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(String(url).startsWith('https://api.github.com/')){
          if(opts.method==='PUT'){
            rulesWrites++;rulesDocument=JSON.parse(atob(JSON.parse(opts.body).content));return {ok:true};
          }
          return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'sha-'+rulesWrites,content:btoa(JSON.stringify(rulesDocument))})};
        }
        if(String(url).includes('/cards/')&&opts.body){
          const patch=JSON.parse(opts.body);
          if(patch.semanticOverrides)__fixture.deck.cards[0].faces[0].semanticOverrides=patch.semanticOverrides;
        }
        return original(url,opts);
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','Flying')
    page.get_by_role('button',name='Save',exact=True).click()
    page.get_by_label('GitHub data.json or folder link').fill('https://github.com/owner/cards/tree/main')
    page.get_by_role('button',name='Connect GitHub',exact=True).click()
    page.get_by_role('button',name='Update data.json on GitHub',exact=True).click()
    page.get_by_label('GitHub connection token').fill('test-token')
    page.get_by_text('Remember access to update data.json next time',exact=True).click()
    assert page.evaluate('rulesWrites')==0
    page.get_by_role('button',name='Connect and update data.json',exact=True).click()
    page.wait_for_function('rulesWrites===1 && __fixture.deck.settings.dataJsonSource?.value && !document.querySelector(".modal")')
    assert page.evaluate('__fixture.deck.settings.dataJsonSource.value')=='https://github.com/owner/cards/blob/main/data.json'
    page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','Lifelink')
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('rulesWrites===2 && !document.querySelector(".modal")')
    assert page.evaluate('rulesDocument.cards[0].oracle_text')=='Lifelink'
    page.locator('[data-card]').click()
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('!document.querySelector(".modal")')
    assert page.evaluate('rulesWrites')==2
    assert not errors,errors


def test_card_save_updates_connected_local_data_without_a_prompt(dom_page):
    page,errors=dom_page
    page.evaluate('''()=>{
      window.localDocument={version:1,artist:'Keep artist',cards:[{name:'Test creature',nickname:'Keep nickname',oracle_text:'Flying'}]};
      window.localWrites=0;window.localPermissions=0;
      const file={queryPermission:async()=> 'granted',requestPermission:async()=>{localPermissions++;return 'granted';},
        getFile:async()=>({text:async()=>JSON.stringify(localDocument)}),
        createWritable:async()=>({write:async text=>{localWrites++;localDocument=JSON.parse(text);},close:async()=>{},abort:async()=>{}})};
      window.localRecord={file,document:structuredClone(localDocument)};
      const get=IDBObjectStore.prototype.get,put=IDBObjectStore.prototype.put,key='deck:'+__fixture.deck.id;
      IDBObjectStore.prototype.get=function(name){
        const request=get.call(this,name);
        if(name===key)Object.defineProperty(request,'result',{get:()=>localRecord});
        return request;
      };
      IDBObjectStore.prototype.put=function(value,name){
        if(name===key){localRecord=value;return put.call(this,{document:value.document},name);}
        return put.call(this,value,name);
      };
      __fixture.deck.cards[0].faces[0].semanticOverrides={oracle_text:'Flying'};
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(String(url).includes('/cards/')&&opts.body){
          const patch=JSON.parse(opts.body);
          if(patch.semanticOverrides)__fixture.deck.cards[0].faces[0].semanticOverrides=patch.semanticOverrides;
        }
        return original(url,opts);
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','Vigilance')
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('localWrites===1 && !document.querySelector(".modal")')
    assert page.evaluate('localDocument.artist')=='Keep artist'
    assert page.evaluate('localDocument.cards[0].nickname')=='Keep nickname'
    assert page.evaluate('localDocument.cards[0].oracle_text')=='Vigilance'
    page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','')
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('localWrites===2 && !document.querySelector(".modal")')
    assert page.evaluate('localDocument.cards[0].oracle_text')==''
    assert page.evaluate('localPermissions')==0
    assert not errors,errors


def test_card_save_keeps_failed_github_write_available_for_retry(dom_page):
    page,errors=dom_page
    page.evaluate('''async()=>{
      const m=__mod_artwork_files,url='https://github.com/owner/cards/blob/main/data.json';
      __fixture.deck.settings.dataJsonSource={kind:'github',value:url};
      await m.rememberGithub(__fixture.deck.id,url,{version:1,cards:[]});
      await m.connectGithub('owner/cards','test-only',false);
      window.failRulesWrite=true;window.rulesWrites=0;
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(String(url).startsWith('https://api.github.com/')){
          if(opts.method==='PUT'){rulesWrites++;return {ok:!failRulesWrite,status:503};}
          return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'current',content:btoa(JSON.stringify({version:1,cards:[]}))})};
        }
        if(String(url).includes('/cards/')&&opts.body){
          const patch=JSON.parse(opts.body);
          if(patch.semanticOverrides)__fixture.deck.cards[0].faces[0].semanticOverrides=patch.semanticOverrides;
        }
        return original(url,opts);
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.locator('#rules-override').evaluate('(el)=>{el.closest("details").open=true;}')
    page.fill('#rules-override','Flying')
    page.get_by_role('button',name='Save',exact=True).click()
    page.get_by_text('GitHub could not update data.json (503). Your changes are saved in the deck.',exact=True).wait_for()
    assert page.locator('#rules-override').input_value()=='Flying'
    assert page.evaluate('__fixture.deck.cards[0].faces[0].semanticOverrides.oracle_text')=='Flying'
    page.evaluate('window.failRulesWrite=false')
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('rulesWrites===2 && !document.querySelector(".modal")')
    assert not errors,errors


def test_card_save_retries_an_unsynced_local_edit_after_reopening(dom_page):
    page,errors=dom_page
    page.evaluate('''async()=>{
      const m=__mod_artwork_files,url='https://github.com/owner/cards/blob/main/data.json';
      __fixture.deck.settings.dataJsonSource={kind:'github',value:url};
      const face=__fixture.deck.cards[0].faces[0];
      face.semanticOverrides={oracle_text:'Flying'};face.rulesOverrideLocal=true;
      window.rulesDocument={version:1,cards:[{name:'Test creature',oracle_text:'Vigilance'}]};
      await m.rememberGithub(__fixture.deck.id,url,rulesDocument);
      await m.connectGithub('owner/cards','test-only',false);
      window.rulesWrites=0;const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(!String(url).startsWith('https://api.github.com/'))return original(url,opts);
        if(opts.method==='PUT'){
          rulesWrites++;rulesDocument=JSON.parse(atob(JSON.parse(opts.body).content));return {ok:true};
        }
        return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'current',content:btoa(JSON.stringify(rulesDocument))})};
      };
    }''')
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('rulesWrites===1 && !document.querySelector(".modal")')
    assert page.evaluate('rulesDocument.cards[0].oracle_text')=='Flying'
    page.locator('[data-card]').click()
    page.get_by_role('button',name='Save',exact=True).click()
    page.wait_for_function('!document.querySelector(".modal")')
    assert page.evaluate('rulesWrites')==1
    assert not errors,errors


def test_rules_file_merge_detects_conflicts_and_preserves_unrelated_changes(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,before={version:1,cards:[{name:'Spirit',oracle_text:'Flying',art:'before.png'}]};
      const changes=[{name:'Spirit',oracle_text:'Vigilance\\nLifelink'}];
      let conflict=false;
      try{m.mergeDataDocument({version:1,cards:[{name:'Spirit',oracle_text:'Haste'}]},changes,before);}
      catch(error){conflict=error.message.includes('rules text');}
      const other={version:1,cards:[{name:'Spirit',oracle_text:'Flying',art:'after.png'}]};
      const merged=m.mergeDataDocument(other,changes,before);
      let saved;
      const file={queryPermission:async()=> 'granted',getFile:async()=>({text:async()=>JSON.stringify(other)}),
        createWritable:async()=>({write:async text=>{saved=JSON.parse(text);},close:async()=>{},abort:async()=>{}})};
      await m.saveLocalData({file,document:before},changes);
      const reset=m.mergeDataDocument(merged,[{name:'Spirit',oracle_text:''}]);
      return {conflict,merged,saved,reset};
    }''')
    assert report['conflict']
    assert report['merged']['cards'][0]['art']=='after.png'
    assert report['saved']['cards'][0]['oracle_text']=='Vigilance\nLifelink'
    assert report['reset']['cards'][0]['oracle_text']==''
    assert not errors,errors


def test_automatic_save_tracks_its_write_and_newer_import_baselines(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,url='https://github.com/owner/cards/blob/main/data.json',id=__fixture.deck.id;
      const baseline={version:1,cards:[{name:'Spirit',oracle_text:'Flying'}]};
      await m.rememberGithub(id,url,baseline);await m.connectGithub('owner/cards','test-only',false);
      let current=structuredClone(baseline),writes=0;
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(!String(url).startsWith('https://api.github.com/'))return original(url,opts);
        if(opts.method==='PUT'){writes++;current=JSON.parse(atob(JSON.parse(opts.body).content));return {ok:true};}
        return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'sha-'+writes,content:btoa(JSON.stringify(current))})};
      };
      const save=(text,before)=>__mod_artwork_review.offerDataSave(id,[{name:'Spirit',oracle_text:text}],baseline,url,[],{autoSave:true,baseline:before});
      await save('Vigilance',baseline);
      await save('Lifelink',baseline);
      current.cards[0].oracle_text='Haste';
      const newer=structuredClone(current);
      await save('Reach',newer);
      current.cards[0].oracle_text='Defender';
      let conflict=false;try{await save('Trample',newer);}catch(error){conflict=error.message.includes('rules text');}
      return {writes,conflict,current};
    }''')
    assert report['writes']==3 and report['conflict']
    assert report['current']['cards'][0]['oracle_text']=='Defender'
    assert not errors,errors


def test_token_merge_preserves_independent_remote_changes_and_detects_real_conflicts(dom_page):
    page,errors=dom_page
    report=page.evaluate('''()=>{
      const m=__mod_artwork_files;
      const pair=(front,back,quantity)=>({front:{name:front},back:typeof back==='string'?{name:back}:back,quantity});
      const first=pair('Angel','Germ',2),second=pair('Soldier',{kind:'card-back'},1);
      const added=pair('Sol Ring',{kind:'card-back'},3);
      const before={version:1,cards:[],tokenAssignments:[first,second]};
      const remote={...before,tokenAssignments:[added,{...second,quantity:7},{quantity:2,back:first.front,front:first.back}]};
      const local={tokenAssignments:[{...first,quantity:4},second]};
      const merged=m.mergeTokenData(remote,local,before);
      const reordered=m.mergeTokenData(remote,{tokenAssignments:[second,first]},before);
      const deleted=m.mergeTokenData({...before,tokenAssignments:[first,second,added]},{tokenAssignments:[first]},before);
      const independent=m.mergeTokenData({version:1,cards:[],tokenAssignments:[added]},
          {tokenAssignments:[first],tokenTreatments:[]},{version:1,cards:[]});
      let conflicts=0;
      for(const changed of [[{...first,quantity:8},second],[second]]){
        try{m.mergeTokenData({...before,tokenAssignments:changed},local,before);}catch(error){if(error.message.includes('Angel / Germ'))conflicts++;}
      }
      const treated={face:{name:'Angel'},options:{power_toughness:'2/2',nonlegendary:true}};
      const treatments=m.mergeTokenData({version:1,cards:[],tokenTreatments:[treated,{face:{name:'Germ'},options:{power_toughness:'1/1'}}]},
          {tokenTreatments:[{face:{name:'Angel'},options:{nonlegendary:true,power_toughness:'2/2'}}]},
          {version:1,cards:[],tokenTreatments:[treated]});
      return {merged,reordered,deleted,independent,conflicts,treatments,remote};
    }''')
    by_front={row['front']['name']:row for row in report['merged']['tokenAssignments']}
    assert by_front['Angel']['quantity']==4
    assert by_front['Soldier']['quantity']==7 and by_front['Sol Ring']['quantity']==3
    assert report['reordered']['tokenAssignments']==report['remote']['tokenAssignments']
    assert [row['front']['name'] for row in report['deleted']['tokenAssignments']]==['Angel','Sol Ring']
    assert len(report['independent']['tokenAssignments'])==2 and report['conflicts']==2
    assert len(report['treatments']['tokenTreatments'])==2
    assert report['remote']['tokenAssignments'][-1]['quantity']==2
    assert not errors,errors


def test_alternate_art_metadata_merges_independent_variants_and_protects_edits(dom_page):
    page,errors=dom_page
    report=page.evaluate('''()=>{
      const m=__mod_artwork_files;
      const first={id:'11111111-1111-4111-8111-111111111111',card:{name:'Plains'},quantity:1,faces:[{name:'Plains',art:'first.png'}]};
      const other={...first,id:'22222222-2222-4222-8222-222222222222',faces:[{name:'Plains',art:'second.png'}]};
      const before={version:1,cards:[],artVariants:[first]};
      const remote={...before,artVariants:[first,other]};
      const merged=m.mergeTokenData(remote,{artVariants:[{...first,quantity:2}]},before);
      let conflict=false;try{m.mergeTokenData({...remote,artVariants:[{...first,quantity:3},other]},{artVariants:[{...first,quantity:2}]},before);}catch(error){conflict=error.message.includes('Alternate artwork');}
      let invalid=false;try{m.validateArtVariants([{...first,faces:[{name:'Plains',art:'../bad.png'}]}]);}catch(error){invalid=true;}
      const tokens=m.mergeTokenData({version:1,cards:[]},{tokenAssignments:[{front:{name:'Angel'},back:{name:'Angel',art_variant:first.id},quantity:2}]});
      return {merged,conflict,invalid,tokens};
    }''')
    assert [row['quantity'] for row in report['merged']['artVariants']]==[2,1]
    assert report['conflict'] and report['invalid']
    assert report['tokens']['tokenAssignments'][0]['back']['art_variant']
    assert not errors,errors


def test_token_save_retries_merge_without_losing_other_decks_assignments(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files;
      const baseline={version:1,cards:[]};
      const local={tokenAssignments:[{front:{name:'Angel'},back:{name:'Germ'},quantity:4}],tokenTreatments:[]};
      let current={...baseline,tokenAssignments:[{front:{name:'Sol Ring'},back:{kind:'card-back'},quantity:1}]},writes=0;
      const fetcher=async(url,options)=>{
        if(options.method!=='PUT')return {ok:true,json:async()=>({sha:'sha-'+writes,encoding:'base64',content:btoa(JSON.stringify(current))})};
        writes++;
        if(writes===1){current.tokenAssignments[0].quantity=6;return {ok:false,status:409};}
        current=JSON.parse(atob(JSON.parse(options.body).content));return {ok:true};
      };
      const result=await m.saveGithubData({repo:'owner/cards',branch:'main',path:'data.json'},'test-only',[],baseline,fetcher,[],local);
      return {result,writes};
    }''')
    assert report['writes']==2
    assert {row['front']['name']:row['quantity'] for row in report['result']['tokenAssignments']}=={'Sol Ring':6,'Angel':4}
    assert not errors,errors


def test_token_saves_recognize_earlier_write_despite_snapshot_property_order(dom_page):
    page,errors=dom_page
    report=page.evaluate('''async()=>{
      const m=__mod_artwork_files,url='https://github.com/owner/cards/blob/main/data.json',id=__fixture.deck.id;
      const baseline={version:1,artist:'Test',cards:[],tokenAssignments:[]};
      await m.rememberGithub(id,url,baseline);await m.connectGithub('owner/cards','test-only',false);
      let current={...structuredClone(baseline),tokenAssignments:[{front:{name:'Sol Ring'},back:{kind:'card-back'},quantity:1}]},writes=0;
      const original=window.fetch;
      window.fetch=async(url,opts={})=>{
        if(!String(url).startsWith('https://api.github.com/'))return original(url,opts);
        if(opts.method==='PUT'){writes++;current=JSON.parse(atob(JSON.parse(opts.body).content));return {ok:true};}
        return {ok:true,status:200,json:async()=>({encoding:'base64',sha:'sha-'+writes,content:btoa(JSON.stringify(current))})};
      };
      const save=(quantity,before)=>__mod_artwork_review.offerDataSave(id,[],baseline,url,[],{autoSave:true,baseline:before,
        tokenData:{tokenAssignments:[{front:{name:'Angel'},back:{name:'Germ'},quantity}],tokenTreatments:[]}});
      await save(2,baseline);
      const reordered={tokenAssignments:[],cards:[],artist:'Test',version:1};
      await save(4,reordered);
      const folder='https://github.com/owner/cards/tree/main';
      await __mod_artwork_review.offerDataSave(id,[{name:'Spirit',oracle_text:'Flying'}],baseline,folder,[],{autoSave:true});
      await save(6,reordered);
      current.tokenAssignments.find(row=>row.front.name==='Angel').quantity=9;
      let conflict=false;try{await save(7,baseline);}catch(error){conflict=error.message.includes('changed in the original');}
      return {writes,conflict,current};
    }''')
    assert report['writes']==4 and report['conflict']
    assert {row['front']['name']:row['quantity'] for row in report['current']['tokenAssignments']}=={'Sol Ring':1,'Angel':9}
    assert not errors,errors


def test_rules_save_detects_conflict_across_equivalent_selectors(dom_page):
    page,errors=dom_page
    report=page.evaluate('''()=>{
      const m=__mod_artwork_files,id='11111111-1111-4111-8111-111111111111',oracle='22222222-2222-4222-8222-222222222222';
      const cards=[{id:'one',scryfall:{id,oracle_id:oracle,name:'Spirit'},faces:[{index:0,name:'Spirit'}]}];
      const baseline={version:1,cards:[{name:'Spirit',oracle_id:oracle,oracle_text:'Flying'}]};
      const current={version:1,cards:[{name:'Spirit',oracle_id:oracle,oracle_text:'Haste',art:'keep.png'}]};
      const changes=[{name:'Spirit',oracle_id:oracle,scryfall_id:id,oracle_text:'Vigilance'}];
      let conflict=false;try{m.mergeCardDataDocument(current,changes,baseline,cards);}catch(error){conflict=error.message.includes('rules text');}
      current.cards[0].oracle_text='Flying';
      const result=m.mergeCardDataDocument(current,changes,baseline,cards);
      return {conflict,result};
    }''')
    assert report['conflict']
    assert len(report['result']['cards'])==1
    assert report['result']['cards'][0]['oracle_text']=='Vigilance'
    assert report['result']['cards'][0]['art']=='keep.png'
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
    assert parse_qs(urlparse(guide.get_attribute('href')).query)=={'name':['BulkProxyForge'],'description':['Update data.json card data'],'target_name':['owner'],'contents':['write'],'expires_in':['90']}
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
    enlarged.get_by_role('button',name='Close image',exact=True).click()
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
def test_choose_look_generates_normal_and_defers_custom(dom_page,look):
    page,errors=dom_page
    page.evaluate('''()=>{
      window.importSettings=null;window.prematureGeneration=[];const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path==='/api/decks/import'){
          importSettings=JSON.parse(options.body).settings;
          __fixture.deck.settings={...__fixture.deck.settings,...importSettings,symbols:Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)]))};
          return {ok:true,text:async()=>JSON.stringify({id:'import-fixture'})};
        }
        if(path==='/api/jobs/import-fixture')return {ok:true,text:async()=>JSON.stringify({state:'done',kind:'Import deck',result:__fixture.deck})};
        if(path.endsWith('/prepare')){prematureGeneration.push(path);return {ok:true,text:async()=>JSON.stringify({id:'normal-prepare'})};}
        if(path==='/api/jobs/normal-prepare')return {ok:true,text:async()=>JSON.stringify({state:'done',result:__fixture.deck})};
        if(path==='/api/render-sessions'){prematureGeneration.push(path);__fixture.deck.status='ready';return {ok:true,text:async()=>JSON.stringify({targets:[],errors:[],cached:1})};}
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
        page.wait_for_function("prematureGeneration.includes('/api/render-sessions')&&!document.querySelector('#generation-screen')")
        assert page.get_by_role('dialog',name='Your deck is ready').count()==0
        assert page.evaluate('prematureGeneration')==['/api/decks/'+page.evaluate('__fixture.deck.id')+'/prepare','/api/render-sessions']
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


def test_substitute_setting_defaults_on_and_saves_per_deck(dom_page):
    page,errors=dom_page
    page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
    control=page.locator('#create-dfc-substitutes')
    assert control.is_checked()
    control.uncheck()
    page.wait_for_function('__fixture.deck.settings.createDfcSubstitutes===false')
    page.evaluate("location.hash='#deck/'+__fixture.deck.id")
    page.locator('[data-card]').wait_for()
    page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
    assert not page.locator('#create-dfc-substitutes').is_checked()
    assert not errors,errors


def test_substitutes_have_separate_searchable_grid_and_normal_back(dom_page):
    page,errors=dom_page
    page.evaluate('''()=>{
      const deck=__fixture.deck,card=deck.cards[0];
      deck.settings.backAsset='b'.repeat(64);
      card.substitute={id:'substitute-face',name:'Test creature — substitute',compiled:{renderKey:'s'.repeat(64),render:{url:'/api/assets/'+'a'.repeat(64)}}};
      deck.summary.substitutes=card.quantity;
      location.hash='#deck/'+deck.id;
    }''')
    section=page.locator('[data-deck-section="substitutes"]')
    section.wait_for()
    tile=section.locator('[data-substitute]')
    assert tile.locator('.quantity-pill').inner_text()=='2×'
    assert page.locator('[data-deck-section="cards"] [data-card]').count()==1
    tile.hover()
    assert 'b'*64 in tile.locator('img').get_attribute('src')
    page.fill('#card-search','no-such-card')
    assert section.locator('[data-substitute]').count()==0
    page.fill('#card-search','Test creature')
    section.locator('[data-substitute]').click()
    assert page.locator('.modal-body').inner_text().startswith('Generated from this card')
    page.get_by_role('button',name='Close',exact=True).click()
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


def test_generation_screen_and_freshness_scope_cover_preflight(dom_page):
    page,errors=dom_page
    result=page.evaluate('''async()=>{
      const deck=__fixture.deck;deck.pendingImport=true;
      deck.settings.source={mode:'github',githubFolder:'https://github.com/owner/repo/tree/main/art'};
      deck.settings.artReviewSignature='matched';
      const original=window.fetch,visible=[],scopes=[];let total=0;
      const reply=value=>({ok:true,text:async()=>JSON.stringify(value)});
      window.fetch=async(path,options={})=>{
        const data=options.body?JSON.parse(options.body):{};
        if(path.endsWith('/metadata')) {
          visible.push(document.querySelector('#generation-screen')?.open===true);
          return reply({id:'clock-metadata'});
        }
        if(path==='/api/jobs/clock-metadata') {
          await new Promise(resolve=>setTimeout(resolve,80));delete deck.pendingImport;
          return reply({state:'done',result:deck});
        }
        if(path==='/api/setup/artwork-review') {
          visible.push(document.querySelector('#generation-screen')?.open===true);scopes.push(data.freshnessScope);
          await new Promise(resolve=>setTimeout(resolve,80));return reply({id:'artwork-fixture'});
        }
        if(path.endsWith('/prepare')) {scopes.push(data.freshnessScope);return reply({id:'clock-prepare'});}
        if(path==='/api/jobs/clock-prepare')return reply({state:'done',result:deck});
        if(path==='/api/render-sessions')return reply({targets:[],errors:[],cached:1});
        if(path==='/api/render-diagnostic') {if(data.diagnostic?.stage==='generation.total')total=data.diagnostic.seconds;return reply({});}
        return original(path,options);
      };
      await __mod_render.renderDecks([deck.id]);
      return {visible,scopes,total,closed:!document.querySelector('#generation-screen')};
    }''')
    assert result['visible']==[True,True]
    assert len(result['scopes'])==2 and result['scopes'][0]==result['scopes'][1] and result['scopes'][0]
    assert result['total']>=.15 and result['closed']
    assert not errors,errors


def test_setup_navigation_persists_edits_without_confirmation(dom_page):
    page,errors=dom_page
    page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
    page.locator('#deck-artist').fill('Keep this edit')
    page.click('.topbar [data-nav=decks]');page.locator('#deck-search').wait_for()
    assert page.evaluate('__fixture.deck.settings.artist')=='Keep this edit'
    assert not errors,errors


@pytest.mark.parametrize('during_generation',[False,True],ids=['setup','generation'])
def test_github_artwork_refresh_finds_added_images_and_prepares_latest_head(dom_page,during_generation):
    page,errors=dom_page
    page.evaluate('''duringGeneration=>{
      const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=';
      const deck=__fixture.deck,settings={source:{mode:'github',githubFolder:'https://github.com/owner/repo/tree/main/art'}};
      const original=window.fetch,heads=new Map(),jobs=new Map();
      window.remoteHead=0;window.headReads=0;window.artworkChecks=[];window.preparedHead=null;
      const readHead=scope=>{
        if(scope&&heads.has(scope))return heads.get(scope);
        headReads++;
        if(scope)heads.set(scope,remoteHead);
        return remoteHead;
      };
      const reply=value=>({ok:true,text:async()=>JSON.stringify(value)});
      window.fetch=async(path,options={})=>{
        const data=options.body?JSON.parse(options.body):{};
        if(path==='/api/setup/artwork-review') {
          const head=readHead(data.freshnessScope),id='refresh-review-'+artworkChecks.length;
          artworkChecks.push({scope:data.freshnessScope,head});
          jobs.set(id,{needsReview:true,signature:'head-'+head,cards:[],
            items:[{id:'missing',name:'Spirit',selector:{name:'Spirit'},image,status:'missing',key:null}],
            inventory:Array.from({length:head+1},(_,index)=>({key:'file'+index,filename:'custom_'+index+'.png',identity:'image'+index,image}))});
          return reply({id});
        }
        if(path.endsWith('/prepare')) {
          window.preparedScope=data.freshnessScope;window.preparedHead=readHead(data.freshnessScope);
          jobs.set('refresh-prepare',deck);return reply({id:'refresh-prepare'});
        }
        if(path.startsWith('/api/jobs/')&&jobs.has(path.split('/').pop()))
          return reply({state:'done',result:jobs.get(path.split('/').pop())});
        return original(path,options);
      };
      const operation=async screen=>{
        const result=await __mod_artwork_review.checkArtwork(deck,settings,[]);
        await __mod_ui.job('/api/decks/'+deck.id+'/prepare',{freshnessScope:screen?.freshnessScope});
        return result;
      };
      window.refreshResult=undefined;
      window.refreshPromise=(duringGeneration?__mod_generation_progress.withGenerationScreen('Test deck',1,operation):operation()).then(result=>window.refreshResult=result);
    }''',during_generation)
    page.locator('[data-artwork-file]').filter(has_text='custom_0.png').wait_for()
    for head in [1,2]:
        page.evaluate('head=>window.remoteHead=head',head)
        page.get_by_role('button',name='Refresh GitHub folder',exact=True).click()
        page.locator('[data-artwork-file]').filter(has_text=f'custom_{head}.png').wait_for(timeout=3000)
    page.locator('[data-artwork-card]').click()
    page.locator('[data-artwork-file]').filter(has_text='custom_2.png').click()
    page.click('#artwork-finish')
    page.wait_for_function('refreshResult!==undefined')
    result=page.evaluate('({checks:artworkChecks,headReads,preparedHead,preparedScope,result:refreshResult,closed:!document.querySelector("#generation-screen")})')
    assert [row['head'] for row in result['checks']]==[0,1,2]
    assert result['preparedHead']==2 and result['result']['changes'][0]['art']=='custom_2.png'
    if during_generation:
        assert len({row['scope'] for row in result['checks']})==3
        assert result['preparedScope']==result['checks'][-1]['scope']
        assert result['headReads']==3,'Preparation should reuse the refreshed head without another GitHub check.'
    assert result['closed'] and not errors,errors


def test_artwork_refresh_does_not_reuse_stale_images_or_pairs(dom_page):
    page,errors=dom_page;artwork_helper(page,count=1,images=1)
    page.locator('[data-artwork-card]').click();page.locator('[data-artwork-file]').click();page.click('#artwork-finish')
    page.wait_for_function('helperResult!==undefined')
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
        else if(path==='/api/jobs/github-fixture'){await new Promise(resolve=>window.finishGithubImport=resolve);value={state:'done',kind:'GitHub setup',message:'Done',done:1,total:1,result:{
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
    page.wait_for_function('typeof finishGithubImport==="function"')
    button=page.locator('#github-setup-button')
    assert button.inner_text()=='Importing…' and button.get_attribute('aria-pressed')=='true'
    assert button.get_attribute('aria-busy')=='true' and button.is_disabled()
    assert 'inset' in button.evaluate('button=>button.style.boxShadow')
    if leave_during_import:
        page.click('.topbar [data-nav=decks]');page.locator('#deck-search').wait_for()
        page.evaluate('finishGithubImport()')
        page.wait_for_function("window.__fixture.deck.settings.symbolsSource?.kind==='github'")
        page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
        page.locator('#setup-state').wait_for()
    else:
        page.evaluate('finishGithubImport()')
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
    assert button.inner_text()=='Imported' and button.get_attribute('aria-pressed')=='true'
    assert button.get_attribute('aria-busy')=='false' and button.is_disabled()
    page.locator('#github-setup-folder').fill('https://github.com/owner/cards/tree/main/other')
    assert button.inner_text()=='1-click import' and button.is_enabled()
    assert button.get_attribute('aria-pressed')=='false'
    page.locator('#github-setup-folder').fill('https://github.com/owner/cards/tree/main/deck/')
    assert button.inner_text()=='Imported' and button.get_attribute('aria-pressed')=='true'
    assert not errors,errors


@pytest.mark.parametrize('competing_edit',[False,True],ids=['background-metadata','real-setup-edit'])
def test_setup_save_retries_only_revisions_that_leave_the_setup_unchanged(dom_page,competing_edit):
    page,errors=dom_page
    page.evaluate('''competing=>{
      const original=window.fetch;window.setupSaveRequests=0;
      window.fetch=async(path,options={})=>{
        if(path.endsWith('/save')){
          setupSaveRequests++;
          if(setupSaveRequests===1){
            __fixture.deck.revision++;
            __fixture.deck.notes='Background notes are retained';
            __fixture.deck.cards[0].name='Resolved card name';
            if(competing)__fixture.deck.settings.artist='Another setup editor';
            return {ok:false,status:409,text:async()=>JSON.stringify({error:'This deck changed in another tab. Reload it before saving; your edits were not overwritten.'})};
          }
          if(JSON.parse(options.body).revision!==__fixture.deck.revision)throw new Error('Retry must use the latest revision');
        }
        return original(path,options);
      };
      location.hash='#deck/'+__fixture.deck.id+'/setup';
    }''',competing_edit)
    page.locator('#deck-artist').fill('My typed artist')
    if competing_edit:
        page.locator('#setup-state').filter(has_text='Could not save changes').wait_for()
        assert page.evaluate('setupSaveRequests')==1
        assert page.evaluate('__fixture.deck.settings.artist')=='Another setup editor'
        assert page.locator('#deck-artist').input_value()=='My typed artist'
    else:
        page.wait_for_function("document.querySelector('#setup-state').textContent==='Changes saved'")
        assert page.evaluate('setupSaveRequests')==2
        assert page.evaluate('__fixture.deck.settings.artist')=='My typed artist'
    assert page.evaluate('__fixture.deck.notes')=='Background notes are retained'
    assert page.evaluate('__fixture.deck.cards[0].name')=='Resolved card name'
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

@pytest.mark.parametrize('choice,label',[('token-full-art','Modern full-art token'),('token-borderless','Modern borderless token')])
def test_generated_token_frame_changes_persist_before_regeneration(dom_page,choice,label):
    page,errors=dom_page
    page.evaluate("""()=>{
      __fixture.deck.status='ready';__fixture.deck.summary.rendered=1;
      __fixture.deck.cards[0].faces[0].group='token';
      __fixture.deck.settings.symbols=Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)]));
      window.preparedFrames=[];const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path.endsWith('/prepare')){preparedFrames.push(__fixture.deck.settings.templateRules.token);return {ok:true,text:async()=>JSON.stringify({id:'prepare-fixture'})};}
        if(path==='/api/jobs/prepare-fixture')return {ok:true,text:async()=>JSON.stringify({state:'done',kind:'Prepare deck',result:__fixture.deck})};
        if(path==='/api/render-sessions')return {ok:true,text:async()=>JSON.stringify({targets:[],errors:[],cached:1})};
        return original(path,options);
      };
      location.hash='#deck/'+__fixture.deck.id+'/setup';
    }""")
    page.locator('[data-frame-group="token"]').click()
    page.get_by_role('button',name='Select '+label,exact=True).click()
    assert page.locator('#token-frame').input_value()==choice
    page.click('#save-generate')
    page.wait_for_function("preparedFrames.length===1&&!document.querySelector('#generation-screen')")
    assert page.evaluate('preparedFrames')==[choice]
    assert page.evaluate('__fixture.deck.settings.templateRules.token')==choice
    page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
    page.locator('[data-frame-group="token"]').wait_for()
    assert page.locator('#token-frame').input_value()==choice
    page.locator('#all-cards-tokens').check()
    page.locator('#token-frame').select_option('token-classic')
    page.wait_for_function("__fixture.deck.settings.templateRules.token==='token-classic'")
    page.locator('[data-frame-group="token"]').click()
    assert 'selected' in page.get_by_role('button',name='Select Classic arched token',exact=True).inner_text()
    page.locator('#modal-close').click()
    assert not errors,errors


@pytest.mark.parametrize('button',['generate-deck','save-generate'])
@pytest.mark.parametrize('failure',[False,True],ids=['import-success','import-failure'])
def test_generate_imports_pending_github_link_and_keeps_artist(dom_page,button,failure):
    page,errors=dom_page
    page.evaluate("""failure=>{
      window.importCalls=0;window.preparedSettings=[];const original=window.fetch;
      window.fetch=async(path,options={})=>{
        if(path==='/api/setup/github-import'){
          importCalls++;
          if(failure)return {ok:false,status:400,text:async()=>JSON.stringify({error:'GitHub folder unavailable'})};
          return {ok:true,text:async()=>JSON.stringify({id:'github-pending'})};
        }
        if(path==='/api/jobs/github-pending')return {ok:true,text:async()=>JSON.stringify({state:'done',result:{
          settings:{source:{mode:'github',githubFolder:'https://github.com/owner/cards/tree/main/deck/art',fallback:false,localFiles:{}},githubSetupFolder:'https://github.com/owner/cards/tree/main/deck',symbols:Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)])),backAsset:null,backDesign:{mode:'default'}},
          cardData:[],summary:{art:'github',symbols:'default',back:'default'},warnings:[]}})};
        if(path.endsWith('/prepare')){preparedSettings.push(structuredClone(__fixture.deck.settings));return {ok:true,text:async()=>JSON.stringify({id:'prepare-pending'})};}
        if(path==='/api/jobs/prepare-pending')return {ok:true,text:async()=>JSON.stringify({state:'done',result:__fixture.deck})};
        if(path==='/api/render-sessions')return {ok:true,text:async()=>JSON.stringify({targets:[],errors:[],cached:1})};
        return original(path,options);
      };
      location.hash='#deck/'+__fixture.deck.id+'/setup';
    }""",failure)
    page.locator('#github-setup-folder').fill('https://github.com/owner/cards/tree/main/deck')
    page.locator('#deck-artist').fill('My custom artist')
    page.click('#'+button)
    page.wait_for_function('importCalls===1')
    if failure:
        page.locator('#github-setup-status').filter(has_text='GitHub folder unavailable').wait_for()
        assert page.evaluate('preparedSettings')==[]
        assert page.locator('#'+button).is_enabled()
        assert page.locator('#deck-artist').input_value()=='My custom artist'
    else:
        page.wait_for_function('preparedSettings.length===1')
        settings=page.evaluate('preparedSettings[0]')
        assert settings['artist']=='My custom artist'
        assert settings['source']['mode']=='github' and settings['source']['githubFolder'].endswith('/deck/art')
        page.evaluate("location.hash='#deck/'+__fixture.deck.id+'/setup'")
        page.locator('#save-generate').click()
        page.wait_for_function('preparedSettings.length===2')
        assert page.evaluate('importCalls')==1
    assert not errors,errors


@pytest.mark.parametrize('invalid_first',[False,True])
def test_generate_checks_artist_before_background_metadata_finishes(dom_page,invalid_first):
    page,errors=dom_page
    page.evaluate("""()=>{
      const deck=__fixture.deck;
      deck.pendingImport=true;deck.settings.artist='';
      deck.settings.source={mode:'local',fallback:true,localFiles:{test_creature:'a'.repeat(64)}};
      deck.settings.symbols=Object.fromEntries(['common','uncommon','rare','mythic'].map(r=>[r,'a'.repeat(64)]));
      window.metadataCalls=[];window.metadataDone=false;const original=window.fetch;
      window.fetch=async(path,options={})=>{
        const reply=data=>({ok:true,text:async()=>JSON.stringify(data)});
        if(path.endsWith('/metadata')){metadataCalls.push('start');return reply({id:'metadata-fixture'});}
        if(path==='/api/jobs/metadata-fixture/pause'){metadataCalls.push('pause');return reply({ok:true});}
        if(path==='/api/jobs/metadata-fixture/resume'){metadataCalls.push('resume');return reply({ok:true});}
        if(path==='/api/jobs/metadata-fixture')return reply({state:metadataDone?'done':'running',kind:'Card metadata',message:'Still reading',done:0,total:10,result:deck});
        if(path.endsWith('/prepare')){metadataCalls.push('prepare');return reply({id:'prepare-fixture'});}
        if(path==='/api/jobs/prepare-fixture')return reply({state:'done',kind:'Prepare deck',result:deck});
        if(path==='/api/render-sessions'){metadataCalls.push('render');return reply({targets:[],errors:[],cached:1});}
        return original(path,options);
      };
      location.hash='#deck/'+deck.id+'/setup';
    }""")
    page.wait_for_function("metadataCalls.includes('start')")
    page.click('#save-generate')
    page.locator('#custom-artist-all').wait_for()
    assert page.evaluate('metadataDone') is False
    assert page.evaluate('metadataCalls')==['start','pause']
    assert not page.locator('#modal-close').is_visible()
    assert not page.locator('#custom-artist-cancel').count()
    page.keyboard.press('Escape')
    assert page.locator('#custom-artist-all').is_visible()
    assert page.evaluate('metadataCalls')==['start','pause']
    if invalid_first:
        page.click('#custom-artist-apply')
        page.locator('.modal-body .form-error').wait_for()
        assert page.evaluate('metadataCalls')==['start','pause']
    page.locator('#custom-artist-all').fill('Custom artist')
    page.click('#custom-artist-apply')
    page.wait_for_function("metadataCalls.includes('resume')")
    assert 'prepare' not in page.evaluate('metadataCalls')
    assert page.locator('#deck-artist').input_value()=='Custom artist'
    assert page.evaluate('__fixture.deck.settings.artist')=='Custom artist'
    page.evaluate('metadataDone=true;delete __fixture.deck.pendingImport')
    page.wait_for_function("metadataCalls.includes('render')")
    assert page.evaluate('__fixture.deck.settings.artist')=='Custom artist'
    assert not errors,errors


@pytest.mark.parametrize('dismiss',['escape','x'])
def test_optional_dialog_ignores_outside_click_and_keeps_focus(dom_page,dismiss):
    page,errors=dom_page
    page.evaluate("()=>{__mod_ui.modal('Optional test','');window.dialogFocus=document.activeElement;}")
    page.mouse.click(2,2)
    assert page.get_by_role('dialog',name='Optional test').count()==1
    assert page.evaluate('document.activeElement===dialogFocus')
    if dismiss=='escape':page.keyboard.press('Escape')
    else:page.click('#modal-close')
    assert page.locator('.modal').count()==0
    assert not errors,errors


def test_required_dialog_blocks_programmatic_close_and_replacement(dom_page):
    page,errors=dom_page
    result=page.evaluate("""()=>{
      const host=__mod_ui.modal('Required test','',{dismissible:false});
      const closed=__mod_ui.closeModal();let replacement='';
      try{__mod_ui.modal('Bypass','');}catch(error){replacement=error.message;}
      return {closed,replacement,title:host.querySelector('h2').textContent};
    }""")
    assert result['closed'] is False and result['replacement']
    assert result['title']=='Required test'
    assert not page.locator('#modal-close').is_visible()
    page.keyboard.press('Escape')
    assert page.get_by_role('dialog',name='Required test').count()==1
    page.evaluate('__mod_ui.closeModal({completed:true})')
    assert page.locator('.modal').count()==0
    assert not errors,errors


def test_busy_dialog_blocks_dismissal_and_unlocks_on_failure(dom_page):
    page,errors=dom_page
    page.evaluate("()=>{window.busyDialog=__mod_ui.modal('Saving test','');__mod_ui.setModalBusy(busyDialog,true);}")
    assert page.locator('#modal-close').is_disabled()
    page.keyboard.press('Escape')
    assert page.get_by_role('dialog',name='Saving test').count()==1
    assert page.evaluate('__mod_ui.closeModal()') is False
    page.evaluate('__mod_ui.setModalBusy(busyDialog,false)')
    page.click('#modal-close')
    assert page.locator('.modal').count()==0
    assert not errors,errors


@pytest.mark.parametrize('dismiss',['escape','x'])
def test_card_inspector_printing_picker_ignores_outside_click(dom_page,dismiss):
    page,errors=dom_page
    page.evaluate("""()=>{
      const original=window.fetch;
      window.fetch=async(path,options)=>path==='/api/printings'?{ok:true,text:async()=>JSON.stringify({data:[]})}:original(path,options);
    }""")
    page.locator('.deck-tile').click();page.locator('[data-card]').click()
    page.click('#choose-printing')
    picker=page.get_by_role('dialog',name='Select Art · Test creature',exact=True)
    picker.wait_for();picker.dispatch_event('click')
    assert picker.is_visible()
    if dismiss=='escape':page.keyboard.press('Escape')
    else:picker.get_by_role('button',name='Close picker').click()
    picker.wait_for(state='detached')
    assert not picker.count()
    assert page.locator('#save-card').is_visible()
    assert not errors,errors


@pytest.mark.parametrize('dismiss',['escape','x'])
def test_confirmation_can_only_be_dismissed_explicitly(dom_page,dismiss):
    page,errors=dom_page
    page.evaluate("()=>{window.confirmationResult=undefined;__mod_ui.confirmAction('Confirm test','Proceed?').then(result=>window.confirmationResult=result);}")
    assert not page.locator('#confirm-no').count()
    page.mouse.click(2,2)
    assert page.evaluate('confirmationResult===undefined')
    if dismiss=='escape':page.keyboard.press('Escape')
    else:page.click('#modal-close')
    page.wait_for_function('confirmationResult===false')
    assert page.locator('.modal').count()==0
    assert not errors,errors


@pytest.mark.parametrize('per_card',[False,True])
def test_custom_artist_prompt_rebases_background_revision(dom_page,per_card):
    page,errors=dom_page
    page.evaluate("""()=>{
      const deck=structuredClone(__fixture.deck);
      deck.settings.artist='';
      deck.settings.source={mode:'github',githubFolder:'https://github.com/example/art'};
      __fixture.deck=structuredClone(deck);
      window.creditResult=null;window.creditWrites=0;
      const original=window.fetch;
      window.fetch=async(path,options={})=>{
        const patch=options.body?JSON.parse(options.body):null;
        if(patch&&(path.endsWith('/save')||path.includes('/cards/'))){
          creditWrites++;
          if(creditWrites===1){
            __fixture.deck.revision++;
            __fixture.deck.notes='Background update during save';
          }
          if(patch.revision!==__fixture.deck.revision)
            return {ok:false,status:409,text:async()=>JSON.stringify({error:'This deck changed in another tab. Reload it before saving; your edits were not overwritten.'})};
          if(patch.settings){
            __fixture.deck.settings={...__fixture.deck.settings,...patch.settings};
            __fixture.deck.revision++;
            return {ok:true,status:200,text:async()=>JSON.stringify(__fixture.deck)};
          }
        }
        return original(path,options);
      };
      __mod_credits.ensureCustomArtCredits(deck).then(value=>window.creditResult=value);
      __fixture.deck.revision+=3;
      __fixture.deck.settings.artist='';
      __fixture.deck.settings.backgroundMarker='preserve me';
    }""")
    if per_card:
        page.check('#custom-artist-each')
        page.locator('[data-custom-artist]').fill('New credit')
    else:
        page.fill('#custom-artist-all','New credit')
    page.click('#custom-artist-apply')
    page.wait_for_function('creditResult!==null')
    assert page.locator('.modal').count()==0
    assert page.evaluate('creditWrites')==2
    result=page.evaluate('creditResult')
    assert result['notes']=='Background update during save'
    assert result['settings']['backgroundMarker']=='preserve me'
    assert result['settings']['source']['mode']=='github'
    if per_card:
        assert result['cards'][0]['faces'][0]['artistOverride']=='New credit'
    else:
        assert result['settings']['artist']=='New credit'
    assert not errors,errors
