"""Devoid gaps reveal artwork without erasing dark frame material or outlines."""
import io,os,base64,threading
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from foundry.devoid_frame import PREFIX,transparent_header_png
from foundry.network import Network
from foundry.runtime import Runtime
from foundry.storage import Store


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def sources():
    white=Image.new('RGBA',(201,281),'white')
    black=Image.new('RGBA',white.size,(25,20,30,255))
    mask=Image.new('RGBA',white.size,(0,0,0,0))
    ImageDraw.Draw(mask).rectangle((8,8,192,29),fill='white')
    white.putpixel((40,10),(0,0,0,255))
    white.putpixel((41,10),(24,24,24,255))
    black.putpixel((40,10),(0,0,0,255))
    black.putpixel((41,10),(3,3,3,255))
    #The title outline and border are black too, but outside the Frame mask.
    white.putpixel((40,35),(0,0,0,255));black.putpixel((40,35),(0,0,0,255))
    return png(black),png(white),png(mask)


def test_only_header_matte_becomes_transparent():
    raw,white,mask=sources();before=Image.open(io.BytesIO(raw)).convert('RGBA')
    result=Image.open(io.BytesIO(transparent_header_png(raw,white,mask))).convert('RGBA')
    assert result.getpixel((40,10))[3]==0
    assert 0<result.getpixel((41,10))[3]<255
    assert result.getpixel((70,10))==before.getpixel((70,10))
    assert result.getpixel((40,35))==before.getpixel((40,35))
    assert result.crop((0,30,201,281)).tobytes()==before.crop((0,30,201,281)).tobytes()
    assert result.crop((0,0,201,8)).tobytes()==before.crop((0,0,201,8)).tobytes()
    art=Image.new('RGBA',result.size,(240,100,220,255))
    assert Image.alpha_composite(art,result).getpixel((40,10))==(240,100,220,255)


def test_corrected_material_is_cached_across_runtime_restarts(tmp_path):
    raw,white,mask=sources();calls=[]
    def transport(url):
        calls.append(url)
        data=mask if url.endswith('m15MaskFrame.png') else white if url.endswith('FrameW.png') else raw
        return data,'image/png',{}
    runtime=Runtime(Network(Store(tmp_path),transport=transport))
    path=PREFIX+'m15DevoidFrameB.png'
    corrected,mime=runtime.fetch(path)
    assert mime=='image/png' and len(calls)==3
    def fail(url):raise AssertionError('Cached Devoid material must not download or derive again')
    restarted=Runtime(Network(Store(tmp_path),transport=fail))
    assert restarted.fetch(path)==(corrected,mime)
    assert restarted.requested[path]['cache'] is True


@pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual native Devoid compositing')
def test_native_header_gaps_reveal_artwork(tmp_path):
    from playwright.sync_api import sync_playwright
    from foundry.server import App,LocalServer
    from foundry.compiler import Compiler
    from foundry.images import ingest_image,rarity_variants
    from foundry.backup import referenced_assets
    store=Store(tmp_path);app=App(store)
    raw=png(Image.new('RGB',(900,1260),(240,100,220)))
    art=ingest_image(store,raw);settings={'symbols':rarity_variants(store,art['id'])}
    sf={'name':'Eldrazi Displacer','layout':'normal','rarity':'rare','colors':[],
        'type_line':'Creature — Eldrazi','mana_cost':'{2}{W}','power':'3','toughness':'3',
        'oracle_text':'Devoid (This card has no color.)','keywords':['Devoid']}
    data=Compiler(store).compile_face(sf,sf,0,{},settings,art['id'],art_origin='uploaded override')['data']
    app.runtime_assets.update(referenced_assets(data))
    data['artSource']='data:image/png;base64,'+base64.b64encode(raw).decode()
    server=LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True);page=browser.new_page()
            page.goto(server.origin+'/#templates')
            error=page.evaluate('''async ({origin,data})=>{
                const frame=document.createElement('iframe');frame.src=origin+'/runtime/host';document.body.append(frame);
                return new Promise((resolve,reject)=>{
                    let started=false;const timer=setTimeout(()=>reject(Error('Native render timed out')),180000);
                    window.addEventListener('message',event=>{
                        if(event.source!==frame.contentWindow||event.data?.source!=='pf-native-runtime')return;
                        if(event.data.type==='ready'&&!started){started=true;frame.contentWindow.postMessage({source:'pf-app',type:'render',key:'devoid-preview',data},origin);}
                        if(event.data.type==='rendered'||event.data.type==='failed'){clearTimeout(timer);resolve(event.data.error||'');}
                    });
                    frame.onload=()=>frame.contentWindow.postMessage({source:'pf-app',type:'ping'},origin);
                });
            }''',{'origin':app.runtime_origin,'data':data})
            assert not error,error
            frame=next(f for f in page.frames if '/runtime/host' in f.url)
            pixels=frame.evaluate('''()=>{
                const context=cardCanvas.getContext('2d');
                return [400,750].map(x=>[...context.getImageData(x,100,1,1).data]);
            }''')
            assert pixels[0]==[240,100,220,255],pixels
            assert pixels[1]!=pixels[0],pixels
            preview=frame.evaluate("() => cardCanvas.toDataURL('image/png').split(',')[1]")
            output=Path(__file__).resolve().parents[1]/'test-results'/'devoid-transparency-preview.png'
            output.parent.mkdir(exist_ok=True);output.write_bytes(base64.b64decode(preview))
            browser.close()
    finally:server.shutdown();server.server_close();app.close()
