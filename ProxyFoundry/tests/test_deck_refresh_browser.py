"""Built website refreshes a live deck through the real cooperative backend."""
import os
import pytest
from test_browser_storage import static_browser

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual Chromium browser storage')


@pytest.mark.parametrize('treated_tokens',[False,True],ids=['ordinary-cards','token-treated-cards'])
def test_static_deck_refresh_keeps_saved_faces_and_defers_new_images(static_browser,treated_tokens):
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected='''
original_deck_refresh_request=request

def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/refresh-seed':
        import base64
        from foundry.domain import GENERATION_VERSION
        records={letter:{'id':letter*8+'-'+letter*4+'-4'+letter*3+'-8'+letter*3+'-'+letter*12,
            'name':name,'layout':'normal','type_line':'Artifact','oracle_text':'','rarity':'common','colors':[]}
            for letter,name in [('a','Alpha'),('b','Beta'),('c','Gamma')]}
        treated_tokens=__TREATED_TOKENS__
        if treated_tokens:records['b']['name']='Badgermole Cub'
        remote={'rows':[('a',2),('b',1)]}
        def transport(address):
            if '/decks/' in address:
                result={'name':'Remote name','entries':{'mainboard':[{'count':count,'card_digest':records[key]} for key,count in remote['rows']]}}
            else:result=next(card for card in records.values() if address.endswith(card['id']))
            return json.dumps(result).encode(),'application/json',{}
        app.ws.net.transport=transport
        link='https://scryfall.com/@tester/decks/33333333-3333-4333-8333-333333333333'
        deck=app.ws.create({'source':link,'name':'Keep my deck name'})
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=')
        asset=app.store.add_asset(raw,'image/png',1,1)
        key,version,_=app.ws.compiler.template_identity('standard','auto')
        for index,card in enumerate(deck['cards']):
            face=card['faces'][0];render='refresh-existing-'+str(index);app.store.render_put(render,asset)
            face['compiled']={'renderKey':render,'artId':asset['id'],'generationVersion':GENERATION_VERSION,'templateKey':key,'templateVersion':version}
        if treated_tokens:
            from foundry import token_assignments
            #Previously saved staged imports need not carry per-card metadata markers.
            deck['stagedImport']=True;deck['settings']['allCardsTokens']=True
            deck['settings']['tokenAssignments']=[{'front':token_assignments.reference(deck['cards'][0]),'back':token_assignments.reference(deck['cards'][1]),'quantity':2}]
        deck['status']='prepared';deck=app.store.put('decks',deck,deck['revision']);remote['rows']=[('a',4),('c',1)]
        return {'status':200,'mime':'application/json','body':json.dumps(app.ws.deck(deck['id'])).encode(),'headers':{}}
    return original_deck_refresh_request(app,method,url,body,headers)
'''
    injected=injected.replace('__TREATED_TOKENS__',repr(treated_tokens))
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();errors=[];generation=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda request:generation.append(request.url) if '/api/render-sessions' in request.url else None)
    page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    deck=page.evaluate("async()=>{const {api}=await import('/site/ui.js');const deck=await api('/api/__test__/refresh-seed',{});location.hash='#deck/'+deck.id+'/cards';return deck;}")
    tile='[data-token-face]' if treated_tokens else '[data-card]'
    page.locator(tile).first.wait_for();page.click('#deck-menu')
    page.get_by_role('button',name='Refresh deck cards',exact=True).click()
    page.click('#refresh-deck-cards')
    page.locator('#activity-title').filter(has_text='1 matching cards kept').wait_for(timeout=30000)
    assert page.get_by_role('dialog',name='Refresh deck cards',exact=True).count()==0
    current=page.evaluate("async id=>{const {api}=await import('/site/ui.js');return api('/api/decks/'+id);}",deck['id'])
    assert current['name']==deck['name']
    settings={**deck['settings'],'tokenAssignments':[]} if treated_tokens else deck['settings']
    assert current['settings']==settings
    alpha,gamma=current['cards']
    assert alpha['name']=='Alpha' and alpha['quantity']==4 and alpha['id']==deck['cards'][0]['id']
    assert alpha['faces']==deck['cards'][0]['faces']
    assert gamma['name']=='Gamma' and not gamma['faces'][0].get('compiled')
    if treated_tokens:
        assert current['tokens']['cardIds']==[alpha['id'],gamma['id']]
        assert not current['tokens']['invalid'] and not current['tokens']['assigned']
        assert page.locator('[data-token-face="'+deck['cards'][1]['id']+'"]').count()==0
        assert page.locator('#deck-body').get_by_text('Badgermole Cub',exact=True).count()==0
        retained=page.locator('[data-token-face="'+alpha['id']+'"] img').first
        retained.wait_for();page.wait_for_function('selector=>{const image=document.querySelector(selector);return image?.complete&&image.naturalWidth>0;}',arg='[data-token-face="'+alpha['id']+'"] img')
    assert page.locator('#generate-deck').is_visible() and page.locator('#generate-deck').is_enabled()
    page.reload(wait_until='domcontentloaded');page.locator(tile).first.wait_for(timeout=90000)
    assert page.locator(tile).count()==2
    if treated_tokens:assert page.locator('[data-token-face="'+deck['cards'][1]['id']+'"]').count()==0
    assert not generation and not errors,{'generation':generation,'errors':errors}