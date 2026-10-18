"""Use alternate artwork from matching and the card editor without changing totals."""
import json,os
import pytest
from test_browser import browser_app,png,sf
from test_browser_storage import static_browser

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual browser alternate-art flow')


def test_match_art_split_download_reload_and_editor_split(browser_app,tmp_path):
    app,server,page,errors=browser_app
    assets={name:app.store.add_asset(png(color=color),'image/png',900,650)['id'] for name,color in [('a_test_creature','#447755'),('other_art','#774455'),('third_art','#445577')]}
    deck=app.ws.new_deck('Alternate art browser')
    card=app.ws.sources.entry(sf(),4)
    settings={**deck['settings'],'source':{'mode':'local','localFiles':assets,'localNames':{name:name+'.png' for name in assets},'fallback':False}}
    deck=app.store.put('decks',{**deck,'cards':[card],'settings':settings},deck['revision'])
    page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
    page.locator('#review-artwork').click()
    page.get_by_role('button',name='other_art.png',exact=True).click()
    page.get_by_role('button',name='Select existing card',exact=True).click()
    page.get_by_role('searchbox',name='Select existing card').fill('Test Creature')
    page.get_by_role('button',name='A Test Creature · 4 copies',exact=True).click()
    page.get_by_role('spinbutton',name='Alternate art quantity').fill('2')
    page.get_by_role('button',name='Split copies',exact=True).click()
    page.locator('[data-art-variant]').wait_for()
    assert '2 alternate-art copies' in page.locator('[data-art-variant]').inner_text()
    page.locator('#artwork-finish').click()
    page.get_by_role('heading',name='Save alternate artwork',exact=True).wait_for()
    with page.expect_download() as download:page.get_by_role('button',name='Download data.json',exact=True).click()
    path=tmp_path/'variants.json';download.value.save_as(path);document=json.loads(path.read_text())
    assert len(document['artVariants'])==1 and document['artVariants'][0]['quantity']==2
    assert document['artVariants'][0]['faces']==[{'name':'A Test Creature','art':'other_art.png'}]
    current=app.ws.deck(deck['id'])
    assert [c['quantity'] for c in current['cards']]==[2,2]
    ids=[c['id'] for c in current['cards']]
    page.goto(server.origin+'/#deck/'+deck['id'])
    page.locator('[data-card="'+ids[0]+'"]').click()
    page.get_by_role('button',name='Add alternate art',exact=True).click()
    page.get_by_role('searchbox',name='Select alternate artwork').fill('third')
    page.get_by_role('button',name='third_art.png',exact=True).click()
    page.get_by_role('button',name='Split copies',exact=True).click()
    page.get_by_role('heading',name='Save alternate artwork',exact=True).wait_for()
    with page.expect_download() as download:page.get_by_role('button',name='Download data.json',exact=True).click()
    download.value.save_as(path);document=json.loads(path.read_text())
    assert len(document['artVariants'])==2
    page.locator('[data-card]').nth(2).wait_for()
    page.reload();page.locator('[data-card]').nth(2).wait_for()
    final=app.ws.deck(deck['id'])
    assert [c['quantity'] for c in final['cards']]==[1,2,1]
    assert [c['id'] for c in final['cards']][:2]==ids
    assert len({f['variantArtFilename'] for c in final['cards'] for f in c['faces'] if f.get('variantArtFilename')})==2
    assert not errors,errors


def test_static_split_creates_github_data_then_prepares_immediately(static_browser):
    import base64
    directory,context,origin=static_browser
    raw=png((300,420))
    metadata=sf('Treasure');metadata.update(layout='token',type_line='Token Artifact — Treasure',colors=[],mana_cost='',oracle_text='{T}, Sacrifice this token: Add one mana of any color.')
    metadata.pop('power');metadata.pop('toughness')
    metadata['image_uris']={'normal':'data:image/png;base64,'+base64.b64encode(raw).decode()}
    injected=f'''
original_variant_transport=app.ws.net.transport
variant_card={metadata!r}
def variant_transport(url):
    if 'api.scryfall.com/' in url:return json.dumps(variant_card).encode(),'application/json',{{}}
    return original_variant_transport(url)
app.ws.net.transport=variant_transport
original_variant_request=request
def request(app,method,url,body,headers):
    if url=='/api/__test__/variants':
        asset=app.store.add_asset(base64.b64decode({base64.b64encode(raw).decode()!r}),'image/png',300,420)
        deck=app.ws.new_deck('Token alternate art')
        deck['cards']=[app.ws.sources.entry(variant_card,4)]
        deck['settings']['source'].update(mode='local',localFiles={{'treasure':asset['id'],'treasure2':asset['id']}},localNames={{'treasure':'treasure.png','treasure2':'treasure2.png'}})
        deck['settings'].update(githubSetupFolder='https://github.com/owner/cards/tree/main/deck',artist='Test Artist')
        app.store.put('decks',deck,deck['revision'])
        app.ws.net.json('https://api.github.com/repos/owner/cards/commits/main',ttl=0)
        return {{'status':200,'mime':'application/json','body':json.dumps(deck).encode(),'headers':{{}}}}
    return original_variant_request(app,method,url,body,headers)
'''
    worker=directory/'web/engine-worker.js'
    worker.write_text(worker.read_text(encoding='utf-8').replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    remote={'document':None,'requests':[]}
    def github(route):
        request=route.request;remote['requests'].append(request.url)
        if '/commits/main' in request.url:
            #Simulate a browser-cached branch head unless this read bypasses its old URL.
            fresh=remote['document'] is not None and '_bpf_refresh=' in request.url
            return route.fulfill(json={'sha':('b' if fresh else 'a')*40})
        if request.method=='PUT':
            remote['document']=json.loads(base64.b64decode(request.post_data_json['content']))
            return route.fulfill(status=201,json={})
        if remote['document'] is None:return route.fulfill(status=404,json={})
        route.fulfill(json={'sha':'file-sha','encoding':'base64','content':base64.b64encode(json.dumps(remote['document']).encode()).decode()})
    def raw_data(route):
        remote['requests'].append(route.request.url)
        if '/'+('b'*40)+'/' not in route.request.url:return route.fulfill(status=404,json={})
        route.fulfill(json=remote['document'])
    context.route('https://api.github.com/**',github)
    context.route('https://raw.githubusercontent.com/**',raw_data)
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    deck=page.evaluate('''async()=>{
        const ui=await import('/site/ui.js'),files=await import('/site/artwork-files.js');
        await files.connectGithub('owner/cards','test-only',false);
        return ui.api('/api/__test__/variants',{});
    }''')
    page.evaluate('''id=>{
        window.variantFlow=import('/site/artwork-review.js').then(module=>module.ensureArtworkReady(id,{returnDeck:true}));
    }''',deck['id'])
    page.get_by_role('button',name='treasure2.png',exact=True).click()
    page.get_by_role('button',name='Select existing card',exact=True).click()
    page.get_by_role('button',name='Treasure · 4 copies',exact=True).click()
    page.get_by_role('spinbutton',name='Alternate art quantity').fill('2')
    page.get_by_role('button',name='Split copies',exact=True).click()
    page.locator('#artwork-finish').click()
    updated=page.evaluate('window.variantFlow')
    assert updated['settings']['dataJsonSource']['value']=='https://github.com/owner/cards/blob/main/deck/data.json'
    prepared=page.evaluate('''async id=>{
        const ui=await import('/site/ui.js');await ui.job('/api/decks/'+id+'/prepare',{});
        return ui.api('/api/decks/'+id);
    }''',deck['id'])
    assert [card['quantity'] for card in prepared['cards']]==[2,2]
    assert all(card['faces'][0].get('compiled') for card in prepared['cards'])
    assert len(remote['document']['artVariants'])==1
    assert prepared['githubCardDataState']['commit']=='b'*40
    assert any('/'+('b'*40)+'/deck/data.json' in url for url in remote['requests'])
    assert not errors,errors