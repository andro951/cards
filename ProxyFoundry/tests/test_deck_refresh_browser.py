"""Built website refreshes a live deck through the real cooperative backend."""
import os
import pytest
from test_browser_storage import static_browser

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual Chromium browser storage')


def test_static_deck_refresh_keeps_saved_faces_and_defers_new_images(static_browser):
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
        deck['status']='prepared';deck=app.store.put('decks',deck,deck['revision']);remote['rows']=[('a',4),('c',1)]
        return {'status':200,'mime':'application/json','body':json.dumps(app.ws.deck(deck['id'])).encode(),'headers':{}}
    return original_deck_refresh_request(app,method,url,body,headers)
'''
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();errors=[];generation=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda request:generation.append(request.url) if '/api/render-sessions' in request.url else None)
    page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    deck=page.evaluate("async()=>{const {api}=await import('/site/ui.js');const deck=await api('/api/__test__/refresh-seed',{});location.hash='#deck/'+deck.id+'/cards';return deck;}")
    page.locator('[data-card]').first.wait_for();page.click('#deck-menu')
    page.get_by_role('button',name='Refresh deck cards',exact=True).click()
    page.click('#refresh-deck-cards')
    page.get_by_role('dialog',name='Refresh deck cards',exact=True).get_by_text('1 matching cards kept',exact=False).wait_for(timeout=30000)
    current=page.evaluate("async id=>{const {api}=await import('/site/ui.js');return api('/api/decks/'+id);}",deck['id'])
    assert current['name']==deck['name'] and current['settings']==deck['settings']
    alpha,gamma=current['cards']
    assert alpha['name']=='Alpha' and alpha['quantity']==4 and alpha['id']==deck['cards'][0]['id']
    assert alpha['faces']==deck['cards'][0]['faces']
    assert gamma['name']=='Gamma' and not gamma['faces'][0].get('compiled')
    assert page.get_by_role('button',name='Generate Images',exact=True).last.is_visible()
    page.get_by_role('button',name='Done',exact=True).click()
    page.reload(wait_until='domcontentloaded');page.locator('[data-card]').first.wait_for(timeout=90000)
    assert page.locator('[data-card]').count()==2
    assert not generation and not errors,{'generation':generation,'errors':errors}