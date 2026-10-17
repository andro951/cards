"""Production browser storage: generation commit, cancellation, reload, failed final saves."""
import base64,io,json,os
from pathlib import Path
import pytest
from PIL import Image
from test_browser_storage import static_browser

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual browser generation transaction')


@pytest.mark.parametrize('finish',['commit','abort','reload','fail'])
def test_generation_publishes_only_after_complete_final_save(static_browser,finish):
    directory,context,origin=static_browser
    out=io.BytesIO();Image.new('RGBA',(40,56),'blue').save(out,'PNG');png=base64.b64encode(out.getvalue()).decode()
    hook='''
original_generation_test_request=request
def request(app,method,url,body,headers):
    if url=='/api/__test__/generation-seed':
        import base64
        raw=base64.b64decode(PNG_DATA)
        asset=app.store.add_asset(raw,'image/png',40,56)
        deck={'id':'generation-test','name':'Original','status':'draft','cards':[{'id':'card','name':'Card','quantity':1,'scryfall':{'name':'Card','type_line':'Creature'},'faces':[{'id':str(n),'name':'Face '+str(n),'compiled':{'renderKey':str(n)*64,'data':{'width':40,'height':56}}} for n in range(1,4)]}]}
        app.store.put('decks',deck)
        return {'status':200,'mime':'application/json','body':json.dumps({'asset':asset['id']}).encode(),'headers':{}}
    if url=='/api/__test__/generation-stage':
        deck=app.store.get('decks','generation-test');deck['name']='Updated';app.store.put('decks',deck,deck['revision'])
        if json.loads(body).get('fail'):
            original=app.store.persist;calls=[]
            def failed(path):
                original(path);calls.append(1)
                if len(calls)==1:raise OSError('Injected final save failure after acceptance')
            app.store.persist=failed
        return {'status':200,'mime':'application/json','body':b'{}','headers':{}}
    if url=='/api/__test__/generation-state':
        deck=app.store.get('decks','generation-test')
        return {'status':200,'mime':'application/json','body':json.dumps({'name':deck['name'],'renders':sum(bool(app.store.render_get(str(n)*64)) for n in range(1,4))}).encode(),'headers':{}}
    return original_generation_test_request(app,method,url,body,headers)
'''.replace('PNG_DATA',repr(png))
    worker=directory/'web/engine-worker.js';text=worker.read_text(encoding='utf-8')
    worker.write_text(text.replace('def browser_request(method, url, body, headers):',hook+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate('''async ({png,finish})=>{
        const ui=await import('/site/ui.js'),{BrowserRenderSave}=await import('/web/render-save.js');
        await ui.api('/api/__test__/generation-seed',{});
        const generation=await ui.api('/api/generation/begin',{deckIds:['generation-test']});
        await ui.api('/api/__test__/generation-stage',{fail:finish==='fail'});
        const saver=await BrowserRenderSave.open(ui.api,undefined,generation),blob=await(await fetch('data:image/png;base64,'+png)).blob();
        await Promise.all([1,2,3].map(n=>saver.save({key:String(n).repeat(64),deckId:'generation-test',cardId:'card',faceId:String(n)},{blob,width:40,height:56})));
        let error='';
        if(finish==='commit'||finish==='fail')try{await ui.api('/api/generation/commit',{id:generation.id,rows:saver.rows});}catch(failure){error=failure.message;}
        if(finish==='abort')await ui.api('/api/generation/abort',generation);
        return {error,rows:saver.rows.length};
    }''',{'png':png,'finish':finish})
    assert result['rows']==3
    assert ('Injected final save failure' in result['error'])==(finish=='fail')
    page.reload();page.locator('#import-deck').wait_for(timeout=90000)
    state=page.evaluate("async()=>{const ui=await import('/site/ui.js');return ui.api('/api/__test__/generation-state');}")
    assert state==({'name':'Updated','renders':3} if finish=='commit' else {'name':'Original','renders':0})
