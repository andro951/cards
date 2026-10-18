"""Render the Studio export through the app's genuine native runtime."""
import base64,copy,io,json,os,threading
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.network import Network
from foundry.storage import Store
from foundry.compiler import Compiler
from foundry.images import ingest_image,rarity_variants

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in pinned native render')


def build_studio_export(mode='native'):
    """Build a fresh portable file through Studio, never reuse an ignored artifact."""
    import importlib.util
    from playwright.sync_api import sync_playwright
    spec=importlib.util.spec_from_file_location('studio_test_host',ROOT/'prototype/template-editor/server.py')
    host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
    server=host.create_server(0);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('canvas[data-ready]').wait_for(timeout=120000)
                if mode!='native':
                    page.evaluate('''async mode => {
                        const {Workflow}=await import('/workflow.js');
                        const canvas=document.createElement('canvas');canvas.width=500;canvas.height=700;
                        const ctx=canvas.getContext('2d');ctx.fillStyle='#dddddd';ctx.fillRect(0,0,500,90);
                        const part=TemplateEditor.model.parts.find(part=>part.id==='Title');
                        for(const code of 'WUBRGMALCV') {
                            const tint=TemplateEditor.model.palette[code]||({M:'#c3a24f',A:'#b1b4b8',L:'#b4a18e',C:'#c6c6c6',V:'#967453'})[code];
                            const source=mode==='recolor' ? await TemplateStudio.recolor(canvas.toDataURL(),tint) : canvas.toDataURL();
                            Workflow.Assign(TemplateEditor.model,part,source,'custom_'+code+'.png',code);
                        }
                        part.mask=null;
                        TemplateEditor.afterChange();
                    }''',mode)
                return page.evaluate('async () => (await import("/exporter.js")).Exporter.Build(TemplateEditor.model)')
            finally:browser.close()
    finally:server.shutdown();server.server_close()


@pytest.mark.parametrize('mode',['native','recolor','individual'])
def test_studio_export_compiles_and_renders_in_native_runtime(tmp_path,mode):
    from playwright.sync_api import sync_playwright
    exported=build_studio_export(mode)
    app=App(Store(tmp_path/'workspace'))
    template=app.ws.import_template_file(exported)
    original=ROOT.parent/'supernatural/art/001_syr_gwyn_hero_of_ashvale.png'
    art=ingest_image(app.store,original.read_bytes())
    settings={'symbols':rarity_variants(app.store,art['id']),'templateRules':{'legendary':template['id']}}
    sf={'id':'22222222-2222-4222-8222-222222222222','oracle_id':'33333333-3333-4333-8333-333333333333',
        'name':'Studio Native Test','type_line':'Legendary Creature — Human Wizard','layout':'normal','colors':['U','R'],
        'mana_cost':'{3}{U}{R}','power':'4','toughness':'4','oracle_text':'Flying\nWhen this creature enters, draw a card.',
        'flavor_text':'Every frame begins with a spark.','rarity':'rare','artist':'Studio artist','set':'tst','collector_number':'1'}
    compiled=Compiler(app.store).compile_face(sf,sf,0,{'semanticOverrides':{'nickname':'The Stormcaller'}},settings,art['id'])
    data=copy.deepcopy(compiled['data'])
    from foundry.backup import referenced_assets
    app.runtime_assets.update(referenced_assets(data))
    assert data['text']['title']['text']=='The Stormcaller'
    assert data['text']['subtitle']['text']=='Studio Native Test'
    assert len(data['frames'])==10
    for key,asset in [('artSource',art['id']),('setSymbolSource',compiled['symbolId'])]:
        item=app.store.asset(asset);data[key]='data:'+item['mime']+';base64,'+base64.b64encode(app.store.asset_path(asset).read_bytes()).decode()
    server=LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False)
        page=browser.new_page(viewport={'width':1500,'height':1050})
        try:
            page.goto(server.origin+'/#templates')
            result=page.evaluate('''async ({origin,data}) => {
                const frame=document.createElement("iframe");frame.src=origin+"/runtime/host";document.body.append(frame);
                return await new Promise((resolve,reject)=>{
                    let started=false;const timer=setTimeout(()=>reject(new Error("Native render timed out")),180000);
                    window.addEventListener("message",async event=>{
                        if(event.source!==frame.contentWindow||event.data?.source!=="pf-native-runtime")return;
                        if(event.data.type==="failed"){clearTimeout(timer);reject(new Error(event.data.error));}
                        if(event.data.type==="ready"&&!started){started=true;frame.contentWindow.postMessage({source:"pf-app",type:"render",key:"studio-test",data},origin);}
                        if(event.data.type==="rendered"){
                            clearTimeout(timer);const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.readAsDataURL(event.data.blob);
                        }
                    });
                    frame.onload=()=>frame.contentWindow.postMessage({source:"pf-app",type:"ping"},origin);
                });
            }''',{'origin':app.runtime_origin,'data':data})
            raw=base64.b64decode(result.split(',',1)[1]);image=Image.open(io.BytesIO(raw))
            assert image.size==(2010,2814)
            assert image.getbbox() is not None
            if mode!='native':
                #A real custom title sheet occupies the top band, not the old masked title.
                r,g,b,*_=image.convert('RGBA').getpixel((500,40))
                assert r>80 and g>60 and b>30
            (ROOT/f'test-results/studio-{mode}-native.png').write_bytes(raw)
        finally:
            browser.close();server.shutdown();server.server_close()