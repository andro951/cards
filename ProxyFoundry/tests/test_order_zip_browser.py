"""Real browser-native ZIP writes, exact pairs, cancellation and saved downloads."""
import base64,io,json,os,zipfile
import pytest
from PIL import Image
from test_browser_storage import static_browser

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual Chromium browser storage')


@pytest.mark.parametrize('storage',['browser','selected-folder'])
@pytest.mark.parametrize('static_browser',['msedge'] if os.name=='nt' else [None],indirect=True)
def test_native_paired_zip_download_and_cleanup(static_browser,tmp_path,storage):
    directory,context,origin=static_browser
    images=[]
    for color in ['red','green','blue','yellow','purple','orange']:
        stream=io.BytesIO();Image.new('RGB',(3,4),color).save(stream,format='PNG');images.append(stream.getvalue())
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected='''
original_order_test_request=request

def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/zip/seed':
        import base64
        from foundry.domain import GENERATION_VERSION,type_group,uid
        from foundry.workspace import DEFAULT_SETTINGS
        assets=[app.store.add_asset(base64.b64decode(raw),'image/png',3,4) for raw in IMAGE_DATA]
        cards=[]
        for index,(name,quantity,front,back) in enumerate([('Normal',2,0,None),('Double faced',1,2,3),('Custom back',1,4,None)]):
            sf={'name':name,'layout':'transform' if back is not None else 'normal','type_line':'Creature — Human'}
            if back is not None:sf['card_faces']=[{'name':name,'type_line':'Creature — Human'},{'name':'Reverse','type_line':'Creature — Human'}]
            faces=[]
            for face_index,asset_index in enumerate([front]+([back] if back is not None else [])):
                face=(sf.get('card_faces') or [sf])[face_index];group=type_group(face,sf,face_index)
                key,version,_=app.ws.compiler.template_identity(group,'auto',face)
                render_key='zip-test-'+str(asset_index);app.store.render_put(render_key,assets[asset_index])
                faces.append({'id':uid(),'index':face_index,'name':face['name'],'group':group,
                    'compiled':{'renderKey':render_key,'generationVersion':GENERATION_VERSION,'templateKey':key,'templateVersion':version}})
            cards.append({'id':uid(),'name':name,'quantity':quantity,'scryfall':sf,'faces':faces,**({'backOverride':assets[5]['id']} if index==2 else {})})
        deck=app.store.put('decks',{'name':'ZIP pairs','settings':dict(DEFAULT_SETTINGS,createDfcSubstitutes=False,backAsset=assets[1]['id']),'status':'prepared','cards':cards})
        app.ws.deck(deck['id'])
        return {'status':200,'mime':'application/json','body':json.dumps({'deckId':deck['id']}).encode(),'headers':{}}
    if str(url)=='/api/__test__/zip/cleanup':
        result={'orders':len(app.store.list('orders')),'files':[path.name for path in (app.store.home/'orders').iterdir()],'pins':len(app.store._asset_pins)}
        return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
    return original_order_test_request(app,method,url,body,headers)
'''.replace('IMAGE_DATA',repr([base64.b64encode(raw).decode() for raw in images]))
    source=source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):')
    worker.write_text(source,encoding='utf-8')
    # A controlled pause before writing makes cancellation deterministic without slowing normal ZIPs.
    zipper=directory/'site/order-zip-worker.js';source=zipper.read_text(encoding='utf-8')
    source=source.replace('const build=async({directory,path,entries})=>{','const build=async({directory,path,entries,hold=false,fail=false})=>{')
    source=source.replace('await writer.write(chunk);check();',
        'if(hold){self.postMessage({testReady:true,state:`running`});while(!cancelled)await new Promise(resolve=>setTimeout(resolve,10));check();}'+
        'await writer.write(chunk);if(fail)throw new Error(`Injected disk failure`);check();')
    zipper.write_text(source,encoding='utf-8')
    if storage=='selected-folder':
        choice=directory/'web/storage-choice.js';source=choice.read_text(encoding='utf-8')
        start=source.index('export async function savedFolder()');end=source.index('\nexport async function chooseFolder',start)
        source=source[:start]+'''export async function savedFolder(){
            const root=await navigator.storage.getDirectory(),folder=await root.getDirectoryHandle('zip-selected-test',{create:true});
            folder.queryPermission=async()=> 'granted';return folder;
        }
''' +source[end:];choice.write_text(source,encoding='utf-8')
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    deck=page.evaluate("async()=>{const {api}=await import('/site/ui.js');return api('/api/__test__/zip/seed',{});}")
    # Observe the actual worker lifetime and inject only controlled failure/cancellation flags.
    page.evaluate('''()=>{
        const NativeWorker=window.Worker;window.zipWorkers=0;
        window.Worker=class extends NativeWorker {
            constructor(url,options){super(url,options);this.zip=String(url).includes('order-zip-worker');if(this.zip){window.zipWorkers++;this.addEventListener('message',event=>{if(event.data.testReady)window.zipReady=true;});}}
            postMessage(data,...rest){if(this.zip&&data.entries)data={...data,hold:window.holdZip,fail:window.failZip};return super.postMessage(data,...rest);}
            terminate(){if(this.zip){window.zipWorkers--;this.zip=false;}return super.terminate();}
        };
    }''')
    result=page.evaluate("async deckId=>{const {job}=await import('/site/ui.js');return job('/api/orders/build',{deckIds:[deckId]});}",deck['deckId'])
    assert result['count']==4 and page.evaluate('window.zipWorkers')==0
    saved=tmp_path/'paired.zip'
    def download():
        data=page.evaluate("""async({path,id})=>{
            const root=await navigator.storage.getDirectory();
            window.showDirectoryPicker=async()=>root.getDirectoryHandle('export-download',{create:true});
            const {saveApiFile}=await import('/site/ui.js');await saveApiFile(path,'paired.zip');
            const target=await (await root.getDirectoryHandle('export-download')).getDirectoryHandle('BulkProxyForge_Order_'+id.slice(0,8));
            return [...new Uint8Array(await (await (await target.getFileHandle('part-001.zip')).getFile()).arrayBuffer())];
        }""",{'path':result['download'],'id':result['id']})
        saved.write_bytes(bytes(data))
    download()
    expected=[images[0],images[1],images[0],images[1],images[2],images[3],images[4],images[5]]
    with zipfile.ZipFile(saved) as archive:
        assert archive.namelist()==[side+f'/{index:06d}.png' for index in range(1,5) for side in ('FRONT','BACK')]
        assert archive.testzip() is None
        assert [archive.read(name) for name in archive.namelist()]==expected
    original=saved.read_bytes()
    for mode in ['cancel','failure']:
        page.evaluate('''async({deckId,mode})=>{
            const {job,api}=await import('/site/ui.js');window.holdZip=mode===`cancel`;window.failZip=mode===`failure`;window.zipReady=false;window.zipOutcome=null;
            window.zipPromise=job('/api/orders/build',{deckIds:[deckId]},{onStarted:id=>window.zipJob=id}).then(()=>window.zipOutcome=`done`,error=>window.zipOutcome=error.message);
        }''',{'deckId':deck['deckId'],'mode':mode})
        if mode=='cancel':
            page.wait_for_function('window.zipReady===true',timeout=30000)
            page.evaluate("async()=>{const {api}=await import('/site/ui.js');await api('/api/jobs/'+window.zipJob+'/cancel',{});}")
        page.wait_for_function('window.zipOutcome!==null',timeout=30000)
        assert page.evaluate('window.zipOutcome')!='done'
        assert page.evaluate('window.zipWorkers')==0
        cleanup=page.evaluate("async()=>{const {api}=await import('/site/ui.js');return api('/api/__test__/zip/cleanup');}")
        assert cleanup=={'orders':1,'files':[result['id']],'pins':0}
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    download();assert saved.read_bytes()==original
    assert not errors,errors
