"""Exercise the shipped browser UI and token data persistence without rendering."""
import base64,io,json,os
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from test_browser_storage import static_browser
from test_browser import browser_app

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual browser token assignment UI')
ROOT=Path(__file__).resolve().parents[1]
DECK='11111111-1111-4111-8111-111111111111'


def test_shared_token_assignments_do_not_show_token_errors_on_normal_deck(browser_app):
    from test_browser import sf
    from foundry.token_assignments import reference
    app,server,page,errors=browser_app
    deck=app.ws.new_deck('Normal subset deck')
    card=app.ws.sources.entry(sf(),2)
    rows=[{'front':reference(card),'back':{'kind':'card-back'},'quantity':8},
          {'front':{'name':'Absent token'},'back':{'kind':'card-back'},'quantity':3}]
    deck['cards']=[card];deck['settings']['tokenAssignments']=rows
    app.store.put('decks',deck,deck['revision'])
    page.goto(server.origin+'/#deck/'+deck['id'])
    page.locator('[data-card="'+card['id']+'"]').wait_for()
    assert page.locator('[aria-label="Tokens not ready"]').count()==0
    assert page.get_by_role('button',name='Remove invalid pairing').count()==0
    assert page.locator('[data-deck-section]').count()==1
    assert app.ws.deck(deck['id'])['settings']['tokenAssignments']==rows
    assert not errors,errors


@pytest.mark.parametrize('first_action',['pair','convert'])
def test_token_save_refreshes_revision_after_connecting_github(browser_app,first_action):
    from foundry.domain import uid
    app,server,page,errors=browser_app
    deck=app.ws.new_deck('Token save revision')
    deck['settings']['dataJsonSource']={'kind':'github','value':'https://github.com/owner/cards/tree/main'}
    cards=[]
    for name,layout in [('Angel','token'),('Germ','token'),('Ordinary','normal')]:
        cards.append(app.ws.sources.entry({'id':uid(),'oracle_id':uid(),'name':name,'layout':layout,
            'type_line':('Token ' if layout=='token' else '')+'Creature — Human','rarity':'common'}))
    deck=app.store.put('decks',{**deck,'cards':cards},deck['revision'])
    page.evaluate('''async()=>{
        const files=await import('/site/artwork-files.js');
        await files.connectGithub('owner/cards','test-only',false);
        const original=window.fetch;window.testGithubDocument=null;window.testGithubWrites=0;
        window.fetch=async(url,options={})=>{
            if(!String(url).startsWith('https://api.github.com/'))return original(url,options);
            if(options.method==='PUT'){
                if(!window.testGithubWrites)await new Promise(resolve=>window.finishFirstGithubSave=resolve);
                window.testGithubDocument=JSON.parse(atob(JSON.parse(options.body).content));window.testGithubWrites++;
                return new Response('{}',{status:201});
            }
            if(!window.testGithubDocument)return new Response('{}',{status:404});
            return new Response(JSON.stringify({sha:'sha-'+window.testGithubWrites,encoding:'base64',content:btoa(JSON.stringify(window.testGithubDocument))}),{status:200});
        };
    }''')
    page.evaluate('(id)=>location.hash="#deck/"+id',deck['id'])
    if first_action=='pair':
        page.locator('[data-token-face="'+cards[0]['id']+'"]').click()
        page.locator('[data-token-back="'+cards[1]['id']+'"]').click()
        page.get_by_role('button',name='Save token',exact=True).click()
    else:
        page.locator('[data-card="'+cards[2]['id']+'"]').click()
        page.get_by_role('button',name='Convert to token',exact=True).click()
        page.get_by_role('button',name='Apply token treatment',exact=True).click()
    page.wait_for_function('() => typeof window.finishFirstGithubSave==="function"')
    assert page.locator('#modal-host .modal').get_attribute('aria-busy')=='true'
    assert page.locator('#modal-close').is_disabled()
    page.keyboard.press('Escape')
    assert page.locator('#modal-host .modal').count()==1
    page.evaluate('window.finishFirstGithubSave()')
    page.locator('#modal-host .modal').wait_for(state='detached')
    current=app.ws.deck(deck['id'])
    assert current['settings']['dataJsonSource']['value']=='https://github.com/owner/cards/blob/main/data.json'
    assert current['revision']==deck['revision']+2
    assert page.evaluate("import('/site/ui.js').then(module=>module.state.activeDeck.revision)")==current['revision']
    page.locator('[data-token-face="'+cards[1]['id']+'"]').click()
    page.locator('[data-token-back="normal"]').click()
    page.get_by_role('button',name='Save token',exact=True).click()
    page.locator('#modal-host .modal').wait_for(state='detached')
    saved=app.ws.deck(deck['id'])
    assert len(saved['settings']['tokenAssignments'])==(2 if first_action=='pair' else 1)
    assert page.evaluate('window.testGithubWrites')==2
    #An actual independent edit must still reject stale token writes.
    page.locator('[data-token-face="'+cards[0]['id']+'"]').click()
    page.locator('[data-token-back="normal"]').click()
    app.ws.save(deck['id'],{'revision':saved['revision'],'notes':'Changed in another tab'})
    page.get_by_role('button',name='Save token',exact=True).click()
    page.get_by_text('This deck changed in another tab. Reload it before saving; your edits were not overwritten.',exact=True).wait_for()
    final=app.ws.deck(deck['id'])
    assert final['settings']['tokenAssignments']==saved['settings']['tokenAssignments']
    assert final['notes']=='Changed in another tab'
    assert not errors,errors


def test_token_grid_pairing_duplicate_edit_download_and_reload(static_browser,tmp_path):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';text=worker.read_text(encoding='utf-8')
    pngs={}
    for name,color in [('Angel','#d8cda5'),('Germ','#73596c'),('Ordinary','#8bb5c5'),('Day // Night','#c9ad60')]:
        image=Image.new('RGB',(250,350),color);draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((7,7,243,343),radius=12,outline='#eeeeee',width=3)
        draw.rectangle((12,15,238,51),fill='#222222');draw.text((20,24),name,fill='white',font_size=18)
        draw.ellipse((50,80,200,230),fill='#333333');draw.text((80,140),'TOKEN' if name!='Ordinary' else 'CARD',fill='white',font_size=20)
        draw.rectangle((12,255,238,335),fill='#eeeeee');draw.text((22,270),name,fill='black',font_size=18)
        buffer=io.BytesIO();image.save(buffer,'PNG');pngs[name]=base64.b64encode(buffer.getvalue()).decode()
    hook='''
original_token_request=request
def request(app,method,url,body,headers):
    if url=='/api/__test__/tokens':
        import base64
        from foundry.domain import uid,type_group,PIPELINE_VERSION
        pngs=TOKEN_PNGS
        deck=app.ws.new_deck('Token assignment test');deck['id']='11111111-1111-4111-8111-111111111111';deck['cards']=[]
        for name,layout,kind in [('Angel','token','Token Creature — Angel'),('Germ','token','Token Creature — Germ'),('Ordinary','normal','Creature — Human'),('Day // Night','double_faced_token','Card')]:
            raw=base64.b64decode(pngs[name]);asset=app.store.add_asset(raw,'image/png',250,350)
            sf={'id':uid(),'oracle_id':uid(),'name':name,'layout':layout,'type_line':kind,'rarity':'common','artist':'Test artist'}
            if layout=='double_faced_token':sf['card_faces']=[{'name':'Day','type_line':'Card'},{'name':'Night','type_line':'Card'}]
            card=app.ws.sources.entry(sf,2)
            for face in card['faces']:
                group=type_group((sf.get('card_faces') or [sf])[face['index']],sf,face['index'])
                key,version,_=app.ws.compiler.template_identity(group,'auto');render=uid();app.store.render_put(render,asset)
                face['compiled']={'renderKey':render,'generationVersion':PIPELINE_VERSION,'templateKey':key,'templateVersion':version,'data':{'width':40,'height':56,'text':{}},'render':app.store.render_get(render)}
            deck['cards'].append(card)
        deck['status']='prepared';app.store.put('decks',deck)
        return {'status':200,'mime':'application/json','body':json.dumps(app.ws.deck(deck['id'])).encode(),'headers':{}}
    return original_token_request(app,method,url,body,headers)
'''.replace('TOKEN_PNGS',repr(pngs))
    worker.write_text(text.replace('def browser_request(method, url, body, headers):',hook+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.set_viewport_size({'width':1280,'height':1000})
    page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    seed=page.evaluate("async()=>{const ui=await import('/site/ui.js');const result=await ui.api('/api/__test__/tokens',{});location.hash='#deck/"+DECK+"';return result;}")
    page.locator('[data-token-face]').first.wait_for(timeout=30000)
    assert page.locator('[data-deck-section]').count()==3
    assert page.locator('[data-token-face]').count()==2 and page.locator('[data-token-pair]').count()==1
    assert page.locator('.page-head .badge').inner_text()=='Tokens not ready'
    angel,germ=seed['cards'][:2];before=[c['faces'] for c in seed['cards']]
    face=page.locator('[data-token-face="'+angel['id']+'"]')
    src=face.locator('img').get_attribute('src');face.hover();assert face.locator('img').get_attribute('src')==src
    page.locator('[data-card-filter="tokens"]').click()
    assert page.locator('[data-token-face]').count()==2 and page.locator('[data-token-pair]').count()==0
    face.click();page.get_by_role('searchbox',name='Search token backs').fill('Germ')
    assert page.locator('[data-token-back]:visible').count()==1
    assert page.locator('[data-token-back="'+angel['id']+'"]').count()==0
    page.locator('[data-token-back="'+germ['id']+'"]').click();page.get_by_role('spinbutton',name='Token quantity').fill('7')
    page.get_by_role('button',name='Save token',exact=True).click()
    page.get_by_role('heading',name='Save token assignments').wait_for(timeout=30000)
    with page.expect_download() as download:
        page.get_by_role('button',name='Download data.json',exact=True).click()
    path=tmp_path/'data.json';download.value.save_as(path);document=json.loads(path.read_text(encoding='utf-8'))
    assert len(document['tokenAssignments'])==2
    assert next(row for row in document['tokenAssignments'] if 'kind' not in row['back'])['quantity']==7
    assert page.locator('[data-card-filter="all"]').get_attribute('aria-pressed')=='true'
    assert page.locator('[data-token-face]').count()==2
    assert page.locator('.page-head .badge').inner_text()=='Ready to print'
    assert page.locator('[data-token-pair]').count()==2
    assert page.locator('[data-token-face="'+angel['id']+'"] .quantity-pill').inner_text()=='(7)'
    page.locator('[data-token-face="'+germ['id']+'"]').click();page.locator('[data-token-back="'+angel['id']+'"]').click()
    duplicate=page.get_by_role('alertdialog',name='Duplicate token combination');assert '7 copies' in duplicate.inner_text()
    duplicate.get_by_role('button',name='Adjust quantity').click();page.get_by_role('spinbutton',name='Token quantity').fill('3')
    page.get_by_role('button',name='Save token',exact=True).click()
    page.get_by_role('heading',name='Save token assignments').wait_for(timeout=30000)
    page.get_by_role('button',name='Close dialog',exact=True).click()
    page.locator('[data-token-pair="0"]').click()
    page.get_by_role('spinbutton',name='Token quantity').fill('4');page.get_by_role('button',name='Save token',exact=True).click()
    page.get_by_role('heading',name='Save token assignments').wait_for(timeout=30000)
    page.get_by_role('button',name='Close dialog',exact=True).click()
    page.reload();page.locator('[data-token-face]').first.wait_for(timeout=90000)
    assert page.locator('[data-token-face="'+angel['id']+'"] .quantity-pill').inner_text()=='(3)'
    result=page.evaluate("async()=>{const ui=await import('/site/ui.js');return ui.api('/api/decks/"+DECK+"');}")
    assert [c['faces'] for c in result['cards']]==before
    assert len(result['settings']['tokenAssignments'])==2
    assert next(pair for pair in result['tokens']['assigned'] if pair['backKind']=='reverse')['quantity']==4
    pair=page.locator('[data-token-pair="1"]');front=pair.locator('img').get_attribute('src');pair.hover()
    assert pair.locator('img').get_attribute('src')!=front
    page.locator('h1').hover();assert pair.locator('img').get_attribute('src')==front
    artifacts=ROOT/'test-results/token-assignments';artifacts.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(artifacts/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path=str(artifacts/'mobile.png'),full_page=True)
    page.locator('[data-token-face="'+angel['id']+'"]').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path=str(artifacts/'assign-mobile.png'),full_page=True)
    page.get_by_role('button',name='Cancel',exact=True).click()
    page.set_viewport_size({'width':1280,'height':1000})
    page.locator('[data-card]').click()
    page.get_by_role('button',name='Convert to token',exact=True).click()
    page.get_by_role('button',name='Apply token treatment',exact=True).click()
    page.get_by_role('heading',name='Save token assignments').wait_for(timeout=30000)
    page.get_by_role('button',name='Close dialog',exact=True).click()
    page.locator('[data-token-face]').nth(2).wait_for()
    assert page.locator('[data-token-face]').count()==3
    assert page.locator('.page-head .badge').inner_text()=='Tokens not ready'
    page.locator('[data-card-filter="tokens"]').click();assert page.locator('[data-token-face]').count()==1
    page.get_by_role('button',name='Assign normal backs to all unused faces',exact=True).click()
    page.get_by_role('heading',name='Save token assignments').wait_for(timeout=30000)
    page.get_by_role('button',name='Close dialog',exact=True).click()
    final=page.evaluate("async()=>{const ui=await import('/site/ui.js');return ui.api('/api/decks/"+DECK+"');}")
    assert final['tokens']['ready'] and len(final['settings']['tokenAssignments'])==3
    assert final['settings']['tokenTreatments']
    assert page.locator('[data-card-filter="all"]').get_attribute('aria-pressed')=='true'
    assert page.locator('[data-token-face]').count()==3
    ordinary=seed['cards'][2]
    page.locator('[data-token-face="'+ordinary['id']+'"]').click()
    assert page.locator('[data-token-back="'+angel['id']+'"]').count()==1
    assert page.locator('[data-token-back="'+germ['id']+'"]').count()==1
    assert page.locator('[data-token-back="'+ordinary['id']+'"]').count()==0
    page.locator('[data-token-back="'+angel['id']+'"]').click()
    page.get_by_role('spinbutton',name='Token quantity').fill('2')
    page.get_by_role('button',name='Save token',exact=True).click()
    page.get_by_role('heading',name='Save token assignments').wait_for(timeout=30000)
    page.get_by_role('button',name='Close dialog',exact=True).click()
    assert page.locator('[data-token-face]').count()==3
    page.locator('[data-token-pair]').nth(3).wait_for()
    assert page.locator('[data-token-pair]').count()==4
    assert page.locator('[data-token-face="'+angel['id']+'"] .quantity-pill').inner_text()=='(5)'
    assert page.locator('[data-token-face="'+ordinary['id']+'"] .quantity-pill').inner_text()=='(4)'
    page.locator('[data-token-face="'+germ['id']+'"]').click()
    assert page.locator('[data-token-back="'+angel['id']+'"]').count()==1
    assert page.locator('[data-token-back="'+ordinary['id']+'"]').count()==1
    page.get_by_role('button',name='Cancel',exact=True).click()


def test_token_data_merge_preserves_cards_and_rejects_remote_pair_conflicts(static_browser):
    _,context,origin=static_browser
    page=context.new_page();page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate('''async()=>{
        const files=await import('/site/artwork-files.js');
        const first={front:{name:'Angel'},back:{name:'Germ'},quantity:2};
        const baseline={version:1,cards:[{name:'Angel',nickname:'Fallen Seraph'}],tokenAssignments:[first]};
        const desired={tokenAssignments:[{...first,quantity:4}],tokenTreatments:[]};
        const merged=files.mergeCardDataDocument(baseline,[],baseline,[],desired);
        const changed={...baseline,tokenAssignments:[{...first,quantity:8}]};
        let conflict='';try{files.mergeCardDataDocument(changed,[],baseline,[],desired);}catch(error){conflict=error.message;}
        const preserved=files.mergeCardDataDocument(merged,[{name:'Angel',oracle_text:'Flying'}]);
        const requests=[];
        const fetcher=async(url,options)=>{
            requests.push({url,options});
            if(options.method==='PUT')return {ok:true};
            return {ok:true,json:async()=>({sha:'abc',encoding:'base64',content:btoa(JSON.stringify(baseline))})};
        };
        const github=await files.saveGithubData({repo:'owner/repo',branch:'main',path:'data.json'},'test-token',[],baseline,fetcher,[],desired);
        return {merged,conflict,preserved,github,body:JSON.parse(atob(JSON.parse(requests[1].options.body).content))};
    }''')
    assert result['merged']['cards']==[{'name':'Angel','nickname':'Fallen Seraph'}]
    assert result['merged']['tokenAssignments'][0]['quantity']==4
    assert 'changed in the original' in result['conflict']
    assert result['preserved']['tokenAssignments']==result['merged']['tokenAssignments']
    assert result['github']==result['body']==result['merged']
