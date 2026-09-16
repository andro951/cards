"""Genuine CardConjurer across structural recipes. Only card data/art are fixtures."""
import io,json,os,threading,zipfile
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from foundry.server import App,LocalServer
from foundry.storage import Store
from foundry.network import Network
from foundry.images import ingest_image,rarity_variants
from foundry.domain import slug
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1' or os.environ.get('PF_BROWSER')!='1',reason='Opt-in real upstream rendering')
def artwork():
    im=Image.new('RGB',(1200,1600),'#24345c');draw=ImageDraw.Draw(im)
    for i in range(0,1600,40):draw.rectangle((0,i,1200,i+30),fill=(40+i%140,80+i%100,120+i%110))
    draw.ellipse((270,400,950,1080),fill='#edb970');b=io.BytesIO();im.save(b,'PNG');return b.getvalue()
def records():
    base={'object':'card','id':'','name':'','layout':'normal','rarity':'rare','set':'tst','collector_number':'1','artist':'Fixture Artist','colors':[],'mana_cost':'','oracle_text':'','type_line':'','image_uris':{'art_crop':'https://cards.scryfall.io/art_crop/front/a/b/fixture.jpg'}}
    defs=[
      {'name':'Verdant Test','type_line':'Creature — Elf','colors':['G'],'mana_cost':'{1}{G}','oracle_text':'Vigilance','power':'2','toughness':'2'},
      {'name':'Triome Test','type_line':'Land — Swamp Forest Island','oracle_text':'This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.)'},
      {'name':'Legendary Grove Test','type_line':'Legendary Land','oracle_text':'{T}: Add one mana of any color.'},
      {'name':'Construct Test','type_line':'Artifact Creature — Construct','colors':['U'],'mana_cost':'{2}{U}','oracle_text':'Flying','power':'3','toughness':'3'},
      {'name':'Esika, God of the Tree // The Prismatic Bridge','layout':'modal_dfc','rarity':'mythic','type_line':'Legendary Creature — God // Legendary Enchantment','card_faces':[
        {'name':'Esika, God of the Tree','type_line':'Legendary Creature — God','colors':['G'],'mana_cost':'{1}{G}{G}','oracle_text':'Vigilance\n{T}: Add one mana of any color.','power':'1','toughness':'4','image_uris':base['image_uris']},
        {'name':'The Prismatic Bridge','type_line':'Legendary Enchantment','colors':['W','U','B','R','G'],'mana_cost':'{W}{U}{B}{R}{G}','oracle_text':'At the beginning of your upkeep, draw a card.','image_uris':base['image_uris']}]},
      {'name':'Chronicle Test','layout':'saga','type_line':'Enchantment — Saga','colors':['W'],'mana_cost':'{2}{W}','oracle_text':'I — Create a 1/1 white Soldier creature token.\nII — Draw a card.\nIII — Creatures you control get +1/+1 until end of turn.'},
      {'name':'Walker Test','type_line':'Legendary Planeswalker — Tester','colors':['U'],'mana_cost':'{2}{U}{U}','loyalty':'4','oracle_text':'+1: Draw a card.\n−2: Return target creature to its owner\'s hand.\n−7: Draw seven cards.'},
      {'name':'Budoka Gardener // Dokai, Weaver of Life','layout':'flip','type_line':'Creature — Human Monk','card_faces':[
        {'name':'Budoka Gardener','type_line':'Creature — Human Monk','colors':['G'],'mana_cost':'{1}{G}','power':'2','toughness':'1','oracle_text':'Upright rules for native Flip test.','artist':'Flip Artist','image_uris':base['image_uris']},
        {'name':'Dokai, Weaver of Life','type_line':'Legendary Creature — Human Monk','colors':['G'],'mana_cost':'','power':'3','toughness':'3','oracle_text':'Rotated lower rules for native Flip test.','artist':'Flip Artist','image_uris':base['image_uris']}]},
      {'name':'Vehicle Test','type_line':'Artifact — Vehicle','colors':['U','R'],'mana_cost':'{1}{U}{R}','power':'4','toughness':'4','oracle_text':'Flying\nCrew 2'},
      {'name':'Iron Man, Titan of Innovation','type_line':'Legendary Artifact Creature — Human','colors':['U','R'],'mana_cost':'{3}{U}{R}','power':'4','toughness':'4','oracle_text':'Flying, haste'},
      {'name':'Summon: Bahamut','layout':'saga','rarity':'mythic','type_line':'Enchantment Creature — Saga Dragon','colors':[],'mana_cost':'{9}','power':'9','toughness':'9','oracle_text':'(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II — Destroy up to one target nonland permanent.\nIII — Draw two cards.\nIV — Mega Flare — This creature deals damage equal to the total mana value of other permanents you control to each opponent.\nFlying'}
    ]
    return [{**base,**d,'id':f'11111111-1111-4111-8111-{i:012d}','oracle_id':f'22222222-2222-4222-8222-{i:012d}','collector_number':str(i)} for i,d in enumerate(defs,1)]
def test_real_native_deck_and_dfc_pairing(tmp_path):
    from playwright.sync_api import sync_playwright
    s=Store(tmp_path/'workspace');net=Network(s);transport=net._transport;byid={c['id']:c for c in records()};art=artwork()
    def remote(url):
        if 'api.scryfall.com/cards/' in url:return json.dumps(byid[url.rsplit('/',1)[-1]]).encode(),'application/json',{}
        if 'cards.scryfall.io' in url:return art,'image/png',{}
        return transport(url)
    net.transport=remote;app=App(s,net);server=LocalServer(app);threading.Thread(target=server.serve_forever,daemon=True).start()
    a=ingest_image(s,art);symbols=rarity_variants(s,a['id']);back=ingest_image(s,art)
    d=app.ws.create({'name':'Native structural smoke deck','source':[{'id':i,'quantity':1} for i in byid],'settings':{'symbols':symbols,'backAsset':back['id'],'artist':'Wrong Custom Default','modificationCredit':'Modified by ChatGPT'}})
    d=app.ws.prepare(d['id']);errors=[f['name']+': '+f['error'] for c in d['cards'] for f in c['faces'] if f.get('error')]
    assert not errors,errors
    evidence=ROOT/'test-results';evidence.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1050});browser_errors=[];page.on('pageerror',lambda e:browser_errors.append(str(e)))
        try:
            page.goto(server.origin+'/#deck/'+d['id']);page.locator('#generate-deck').wait_for();page.click('#generate-deck')
            page.locator('.badge.ready,.toast.error').first.wait_for(timeout=480000)
            ready=app.ws.deck(d['id'])
            assert ready['status']=='ready',{'status':ready['status'],'activity':page.locator('#activity-log').text_content(),'errors':browser_errors}
            assert ready['summary']['rendered']==12
            assert '/img/frames/saga/creature/c.png' in app.runtime.requested, 'Colorless Saga creature frame was not exercised by the native renderer'
            for c in ready['cards']:
                for f in c['faces']:
                    comp=f['compiled'];assert comp['data']['infoArtist']==comp['credit']['originalArtist']+' · Modified by ChatGPT'
                    render=s.render_get(comp['renderKey']);im=Image.open(s.asset_path(render['asset_id']))
                    assert im.size==(comp['data']['width'],comp['data']['height'])
                    im.crop((0, int(im.height*.93), im.width, im.height)).save(evidence/('credit_'+slug(f['name'])+'.png'))
                    im.thumbnail((300,420));im.save(evidence/('native_'+slug(f['name'])+'.png'))
            order=app.orders.build([d['id']],acknowledge=True)
            esika=next(c for c in ready['cards'] if len(c['faces'])==2)
            expected=s.render_get(esika['faces'][1]['compiled']['renderKey'])['asset_id']
            with zipfile.ZipFile(s.home/'orders'/(order['id']+'.zip')) as z:
                assert z.read('BACK/000005.png')==s.asset_path(expected).read_bytes()
                assert z.read('BACK/000001.png')==s.asset_path(back['id']).read_bytes()
                assert len(z.namelist())==22
                assert z.read('BACK/000008.png')==s.asset_path(back['id']).read_bytes(), 'Flip card must use the deck back'
            flip=ready['cards'][7]['faces'][0]['compiled']['data'];assert flip['text']['title2']['rotation']==180
            assert flip['text']['pt']['text']=='2/1' and flip['text']['pt2']['text']=='3/3'
            assert not browser_errors,browser_errors
        finally:
            page.screenshot(path=str(evidence/'native-structural-browser.png'),full_page=True)
            (evidence/'native-structural-diagnostics.json').write_text(json.dumps({'runtime':app.runtime.diagnostic(),'browserErrors':browser_errors,'activity':page.locator('#activity-log').text_content()},indent=2))
            (evidence/'native-structural.log').write_text((s.home/'logs/app.log').read_text())
            browser.close();server.shutdown();server.server_close();app.close()
