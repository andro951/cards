"""Genuine Station module + actual pinned core. Art/text fixtures, not fixture drawing."""
import io,json,os,threading,zipfile
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants
from foundry.domain import slug,STATION_SCRIPT_URL,STATION_SCRIPT_SHA256
from tests.test_v58_station import card

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1' or os.environ.get('PF_BROWSER')!='1',reason='Opt-in real Station rendering')

def art(size):
    im=Image.new('RGB',size,'#27384b');d=ImageDraw.Draw(im)
    for y in range(0,size[1],60):d.rectangle((0,y,size[0],y+40),fill=(50+y%130,90+y%110,140+y%90))
    d.ellipse((size[0]*.3,size[1]*.3,size[0]*.7,size[1]*.7),fill='#e4b96a');b=io.BytesIO();im.save(b,'PNG');return b.getvalue()

def test_native_station_full_compact_two_tier_and_sequence(tmp_path):
    from playwright.sync_api import sync_playwright
    examples=[card(colors=['U'],pre=True),
       {'name':'Creature between Stations','type_line':'Creature — Elf','colors':['G'],'mana_cost':'{G}','oracle_text':'Vigilance','power':'2','toughness':'2','layout':'normal','rarity':'common','artist':'Creature Artist'},
       card(colors=['U','R'],pre=True,tiers=2),card(colors=[],legendary=False,pre=False),
       card(colors=['W','U','B'],legendary=False,pre=True,tiers=2)]
    for i,c in enumerate(examples):
        c['name']=['One Tier with Pretext','Creature between Stations','Dual Two Tier','Compact Colorless','Multicolor Two Tier'][i]
        c.update(id=f'33333333-3333-4333-8333-{i:012d}',image_uris={'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/'+str(i)+'.jpg'})
        if c['name']=='Compact Colorless':c['mana_cost']='{5}'
        elif c['name']=='Multicolor Two Tier':c['mana_cost']='{W}{U}{B}'
        elif c['name']=='One Tier with Pretext':c['mana_cost']='{3}{U}'
    records={c['id']:c for c in examples};s=Store(tmp_path/'workspace');net=Network(s);original=net._transport
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(records[url.rsplit('/',1)[-1]]).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:
            i=int(url.rsplit('/',1)[-1].split('.')[0]);return art((900,600) if i in [0,3] else (900,1400)),'image/png',{}
        return original(url)
    net.transport=remote;app=App(s,net);server=LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    a=ingest_image(s,art((300,420)));sym=ingest_image(s,art((100,100)))
    d=app.ws.create({'name':'Station release tests','source':[{'id':i} for i in records],
      'settings':{'symbols':rarity_variants(s,sym['id']),'backAsset':a['id']}})
    evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1500,'height':1040});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        # Observe actual native draw calls, without altering their inputs/results.
        page.add_init_script('''(() => {
          const original=CanvasRenderingContext2D.prototype.drawImage;
          window.__stationDraws=[];window.__nativeEvidence=[];
          CanvasRenderingContext2D.prototype.drawImage=function(image,...args){
            if(this.canvas===window.stationPostFrameCanvas&&image instanceof HTMLImageElement&&image.src.includes('/station/'))window.__stationDraws.push({src:image.src,args,alpha:this.globalAlpha});
            return original.call(this,image,...args);
          };
          window.addEventListener('message',e=>{
            if(e.data?.type==='render')window.__stationDraws=[];
            if(e.data?.type==='rendered'&&e.source){
              e.source.postMessage({source:'test-observer',type:'evidence'},e.origin);
            }
            if(e.data?.type==='evidence'&&window.card){
              parent.postMessage({type:'station-test-evidence',card:JSON.parse(JSON.stringify(window.card)),draws:window.__stationDraws},e.origin);
            }
            if(e.data?.type==='station-test-evidence')window.__nativeEvidence.push(e.data);
          });
        })();''')
        try:
            page.goto(server.origin+'/#deck/'+d['id']);page.locator('#generate-deck').wait_for();page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=360000)
            ready=app.ws.deck(d['id'])
            assert ready['status']=='ready',{'status':ready['status'],'log':page.locator('#activity-log').text_content(),'body':page.locator('body').inner_text(),'errors':errors}
            native=page.evaluate('window.__nativeEvidence');(evidence/'station-native-evidence.json').write_text(json.dumps(native,indent=2))
            assert len(native)==len(examples),[n.get('card',{}).get('version') for n in native]
            for i,n in enumerate(native):
                if i==1:assert not n['draws'];continue
                state=n['card']['station'];saved=ready['cards'][i]['faces'][0]['compiled']['data']['station']
                assert state['badgeSettings']==saved['badgeSettings']
                assert state['badgeValues']==saved['badgeValues']
                assert n['card']['text']['ability2']['text']==ready['cards'][i]['faces'][0]['compiled']['data']['text']['ability2']['text']
                badges=[x for x in n['draws'] if '/badges/' in x['src']]
                pts=[x for x in n['draws'] if '/pt/' in x['src']]
                assert badges and pts, n['draws']
                assert all(x['alpha']==1 and x['args'][-2:]==[151.2,151.2] for x in badges)
                assert all(x['alpha']==1 and x['args'][-2:]==[306,148] for x in pts)
                assert state['disableFirstAbility']==(i==3)
            for c in ready['cards']:
                comp=c['faces'][0]['compiled'];image=Image.open(s.asset_path(s.render_get(comp['renderKey'])['asset_id']))
                assert image.size==(2010,2814)
                image.thumbnail((603,844));image.save(evidence/('station_'+slug(c['name'])+'.png'))
            order=app.orders.build([d['id']],True)
            with zipfile.ZipFile(s.home/'orders'/(order['id']+'.zip')) as z:
                assert len(z.namelist())==10
                assert all(z.read('BACK/'+str(i).zfill(6)+'.png')==s.asset_path(a['id']).read_bytes() for i in range(1,6))
            assert not errors,errors
            station=app.runtime.diagnostic()['files']['/js/frames/versionStation.js']
            assert station['sha256']==STATION_SCRIPT_SHA256 and station['url']==STATION_SCRIPT_URL
        finally:
            page.screenshot(path=str(evidence/'station-browser.png'),full_page=True)
            (evidence/'station-diagnostics.json').write_text(json.dumps({'runtime':app.runtime.diagnostic(),'errors':errors,'activity':page.locator('#activity-log').text_content()},indent=2))
            (evidence/'station-runtime.log').write_text((s.home/'logs/app.log').read_text())
            browser.close();server.shutdown();server.server_close();app.close()
