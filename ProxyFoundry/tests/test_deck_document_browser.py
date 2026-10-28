"""Fresh headless browser + isolated server: no user browser/profile/storage."""
import json
import os
import threading
import pytest
from foundry.server import App,LocalServer
from foundry.deck_document import export_document
from test_deck_document import source_deck,destination

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in isolated browser check')


def test_complete_data_json_import_and_export_from_deck_ui(tmp_path):
    from playwright.sync_api import sync_playwright
    source,deck=source_deck(tmp_path)
    from urllib.parse import quote
    original_vector='data:image/svg+xml;utf8,'+quote('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><defs><linearGradient id="paint"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs><rect width="40" height="40" fill="url(#paint)"/></svg>')
    deck['cards'][0]['faces'][0]['compiled']['data']['frames'].append({'name':'Generated gradient','src':original_vector,'masks':[]})
    source.store.put('decks',deck,deck['revision'])
    document=export_document(source,deck['id'])
    target=destination(tmp_path,source,document)
    app=App(target.store);app.ws=target
    server=LocalServer(app)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    file=tmp_path/'data.json';file.write_text(json.dumps(document),encoding='utf-8')
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,**({'channel':os.environ['PF_BROWSER_CHANNEL']} if os.environ.get('PF_BROWSER_CHANNEL') else {}))
            page=browser.new_page()
            page.goto(server.origin)
            page.get_by_role('button',name='Add New Deck').click()
            page.get_by_text('Other import methods',exact=True).click()
            page.locator('input[type=file]').set_input_files(file)
            page.get_by_role('button',name='Add deck',exact=True).click()
            page.wait_for_url('**/#deck/*/cards')
            page.get_by_role('heading',name=deck['name'],exact=True).wait_for()
            restored_vector=target.store.list('decks')[0]['cards'][0]['faces'][0]['compiled']['data']['frames'][-1]['src']
            assert page.evaluate('''async sources=>{
              const pixels=async src=>{
                const image=new Image();image.src=src;await image.decode();
                const canvas=document.createElement('canvas');canvas.width=40;canvas.height=40;
                const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
                return [...ctx.getImageData(0,0,40,40).data];
              };
              const [before,after]=await Promise.all(sources.map(pixels));
              return before.every((v,i)=>v===after[i]);
            }''',[original_vector,restored_vector])
            page.get_by_role('button',name='More').click()
            assert page.get_by_role('button',name='Save complete data.json',exact=True).count()==0
            with page.expect_download() as download:
                page.get_by_role('button',name='Export complete data.json',exact=True).click()
            saved=tmp_path/'round-trip.json';download.value.save_as(saved)
            result=json.loads(saved.read_text(encoding='utf-8'))
            assert result['deck']['settings']==document['deck']['settings']
            assert result['deck']['cards'][0]['quantity']==3
            assert result['deck']['cards'][0]['faces'][0]['fit']==document['deck']['cards'][0]['faces'][0]['fit']
            assert result['images']==document['images']
            assert 'base64' not in saved.read_text(encoding='utf-8')
            merge_checks=page.evaluate('''async document=>{
              const files=await import('/site/artwork-files.js');
              const legacy={version:1,cards:[]},calls=[];
              const fetcher=async(url,options={})=>{
                calls.push(url);
                if(options.method==='PUT')return {ok:true,status:200};
                if(url.includes('/git/blobs/'))return {ok:true,text:async()=>JSON.stringify(legacy)};
                return {ok:true,status:200,json:async()=>({sha:'a'.repeat(40),encoding:'none'})};
              };
              const result=await files.saveGithubData({repo:'owner/cards',branch:'main',path:'data.json'},
                'fixture',[],legacy,fetcher,[],null,legacy,document);
              let writes=0;
              await files.saveGithubData({repo:'owner/cards',branch:'main',path:'data.json'},
                'fixture',[],result,async(url,options={})=>{
                  if(options.method==='PUT'){writes++;return {ok:true,status:200};}
                  return {ok:true,status:200,json:async()=>({sha:'a'.repeat(40),encoding:'base64',content:btoa(unescape(encodeURIComponent(JSON.stringify(result))))})};
                },[],null,result,result);
              const remote=structuredClone(document);remote.deck.notes='Someone else changed this';
              let blocked=false;
              try{files.completeDataDocument(remote,document,remote,document);}catch(error){blocked=error.message.includes('changed');}
              const preserved=files.mergeCardDataDocument(document,[{name:'One Card',nickname:'Restored'}]);
              return {version:result.version,writes,large:calls.some(url=>url.includes('/git/blobs/')),blocked,
                kept:preserved.deck.settings.showFlavorText===document.deck.settings.showFlavorText};
            }''',result)
            assert merge_checks=={'version':2,'writes':0,'large':True,'blocked':True,'kept':True}
            auto_save=page.evaluate('''async()=>{
              const ui=await import('/site/ui.js'),files=await import('/site/artwork-files.js');
              const id=location.hash.split('/')[1],url='https://github.com/owner/cards/blob/main/data.json';
              const deck=await ui.api('/api/decks/'+id);
              await ui.api('/api/decks/'+id+'/save',{revision:deck.revision,settings:{dataJsonSource:{kind:'github',value:url}}});
              await files.connectGithub('owner/cards','fixture-only',false);
              const original=window.fetch;let saved=null;
              window.fetch=async(address,options={})=>{
                if(String(address).startsWith('https://api.github.com/repos/owner/cards/contents/')) {
                  if(options.method==='PUT') {
                    const body=JSON.parse(options.body);
                    saved=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(body.content),c=>c.charCodeAt(0))));
                    return new Response('{}',{status:200});
                  }
                  return new Response(JSON.stringify({sha:'a'.repeat(40),encoding:'base64',content:btoa('{"version":1,"cards":[]}')}),{status:200});
                }
                return original(address,options);
              };
              const owner=ui.work.begin({label:'Automatic generation save test',resources:['deck:'+id]});
              try {
                await (await import('/site/deck-document.js')).saveGenerationData([id],{owner});
                return {vectors:Object.keys(saved.vectors).length,embedded:JSON.stringify(saved).includes('data:image/'),version:saved.version};
              } finally {window.fetch=original;ui.work.finish(owner);await files.disconnectGithub('owner/cards');}
            }''')
            assert auto_save=={'vectors':1,'embedded':False,'version':2}
            page.evaluate('''document=>{
              window.requiredSave=import('/site/artwork-review.js').then(({offerDataSave})=>
                offerDataSave('fixture',[],{version:1,cards:[]},'https://github.com/owner/cards/blob/main/data.json',[],
                  {title:'Required generation save',forceDocument:true,requireGithubSave:true,completeDocument:document}));
            }''',result)
            page.get_by_role('heading',name='Required generation save',exact=True).wait_for()
            assert page.get_by_role('button',name='Download data.json',exact=True).count()==0
            assert page.get_by_role('button',name='Update data.json on GitHub',exact=True).count()==1
            page.evaluate("import('/site/ui.js').then(({closeModal})=>closeModal())")
            assert page.evaluate('window.requiredSave.then(result=>result===undefined)')
            #A local-only image must receive a verified location before export.
            import io
            from PIL import Image
            buffer=io.BytesIO();Image.new('RGB',(24,24),'red').save(buffer,'PNG');raw=buffer.getvalue()
            asset=target.store.add_asset(raw,'image/png',24,24)
            current=target.store.list('decks')[0]
            current['cards'][0]['faces'][0]['artOverride']=asset['id']
            target.store.put('decks',current,current['revision'])
            from foundry.network import Network
            target.net=Network(target.store,transport=lambda url:(raw,'image/png',{}),sleeper=lambda _:None)
            page.reload();page.get_by_role('heading',name=deck['name'],exact=True).wait_for()
            page.get_by_role('button',name='More').click()
            page.get_by_role('button',name='Export complete data.json',exact=True).click()
            page.get_by_role('heading',name='Add permanent image sources',exact=True).wait_for()
            page.get_by_role('textbox',name='Permanent URL for image '+asset['id'][:8]).fill('https://cards.scryfall.io/art_crop/permanent.png')
            with page.expect_download() as download:
                page.get_by_role('button',name='Verify and save image sources',exact=True).click()
            verified=tmp_path/'verified-source.json';download.value.save_as(verified)
            assert json.loads(verified.read_text(encoding='utf-8'))['images'][asset['id']]['url']=='https://cards.scryfall.io/art_crop/permanent.png'
            browser.close()
    finally:
        server.shutdown();server.server_close()
