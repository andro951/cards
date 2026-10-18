"""Verify actual native ability font sizes and ink bounds after fitting."""
import base64,io,json,os,threading
from pathlib import Path
import pytest
from PIL import Image
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.compiler import Compiler
from foundry.images import ingest_image,rarity_variants
from foundry.backup import referenced_assets

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in native planeswalker rendering')


def test_abilities_share_actual_font_size_and_stay_inside_their_rows(tmp_path):
    from playwright.sync_api import sync_playwright
    examples=[
        ('Venser the Sojourner',['W','U'],
         '+2: Exile target permanent you own. Return it to the battlefield under your control at the beginning of the next end step.\n'
         "-1: Creatures can't be blocked this turn.\n"
         '-8: You get an emblem with "Whenever you cast a spell, exile target permanent."'),
        ('Vivien on the Hunt',['G'],
         '+2: You may sacrifice a creature. If you do, search your library for a creature card with mana value equal to 1 plus the sacrificed creature\'s mana value, put it onto the battlefield, then shuffle.\n'
         '+1: Mill five cards, then put any number of creature cards milled this way into your hand.\n'
         '-1: Create a 4/4 green Rhino Warrior creature token.'),
    ]
    app=App(Store(tmp_path));buffer=io.BytesIO();Image.new('RGB',(600,840),'#557744').save(buffer,'PNG')
    art=ingest_image(app.store,buffer.getvalue());settings=app.ws.validate_settings({'symbols':rarity_variants(app.store,art['id'])})
    samples=[]
    for name,colors,oracle in examples:
        card={'name':name,'layout':'normal','type_line':'Legendary Planeswalker — Tester','colors':colors,
              'mana_cost':'{3}'+''.join('{'+c+'}' for c in colors),'oracle_text':oracle,'loyalty':'4','rarity':'rare'}
        for choice in (['auto','godzilla-card'] if len(colors)==2 else ['auto']):
            samples.append(Compiler(app.store).compile_face(card,card,0,{'templateOverride':choice},settings,art['id'])['data'])
    tall=json.loads((Path(__file__).parent/'fixtures/godzilla_special/Tezzeret.json').read_text(encoding='utf-8'))
    for choice in ('auto','godzilla-card'):
        samples.append(Compiler(app.store).compile_face(tall,tall,0,{'templateOverride':choice},settings,art['id'])['data'])
    for data in samples:
        app.runtime_assets.update(referenced_assets(data))
        data['artSource']='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
    server=LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            for data in samples:
                page=browser.new_page();page.goto(server.origin+'/#templates')
                error=page.evaluate("""async ({origin,data})=>{
                  const frame=document.createElement('iframe');frame.src=origin+'/runtime/host';document.body.append(frame);
                  return new Promise((resolve,reject)=>{
                    let started=false;const timer=setTimeout(()=>reject(Error('Native render timed out')),180000);
                    window.addEventListener('message',event=>{
                      if(event.source!==frame.contentWindow||event.data?.source!=='pf-native-runtime')return;
                      if(event.data.type==='ready'&&!started){started=true;frame.contentWindow.postMessage({source:'pf-app',type:'render',key:'walker',data},origin);}
                      if(event.data.type==='rendered'||event.data.type==='failed'){clearTimeout(timer);resolve(event.data.error||'');}
                    });
                    frame.onload=()=>frame.contentWindow.postMessage({source:'pf-app',type:'ping'},origin);
                  });
                }""",{'origin':app.runtime_origin,'data':data})
                assert not error,error
                frame=next(f for f in page.frames if '/runtime/host' in f.url)
                rows=frame.evaluate("""()=>{
                  const rows=[];
                  for(const [key,field] of Object.entries(card.text)){
                    if(!/^ability[0-3]$/.test(key)||!field.text||!field.height)continue;
                    const canvas=document.createElement('canvas');canvas.width=cardCanvas.width;canvas.height=cardCanvas.height;
                    const context=canvas.getContext('2d');writeText(field,context);
                    const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
                    let minY=canvas.height,maxY=-1,maxX=-1;
                    for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
                      if(pixels[(y*canvas.width+x)*4+3]>128){minY=Math.min(minY,y);maxY=Math.max(maxY,y);maxX=Math.max(maxX,x);}
                    }
                    rows.push({key,size:field.proxyFoundryTextFit.size,minY,maxY,maxX,
                      top:field.y*card.height,bottom:(field.y+field.height)*card.height,right:(field.x+field.width)*card.width});
                  }
                  return rows;
                }""")
                assert len(rows)==data['planeswalker']['count'],rows
                assert len({row['size'] for row in rows})==1,rows
                for row in rows:
                    assert row['maxY']>=row['minY']>=row['top']-2,row
                    assert row['maxY']<=row['bottom']+2,row
                    assert row['maxX']<=row['right']+4,row
                page.close()
            browser.close()
    finally:
        server.shutdown();server.server_close();app.close()
