"""Compare foreground service during real import/archive jobs in a static build.

Only the temporary fixture adds 75ms per remote image/folder read. This isolates
worker queue blocking; it is not a live GitHub or export throughput benchmark.
"""
import argparse,base64,functools,http.server,json,subprocess,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_github_setup import BundleRemote,png
from test_website import build_site,copy_site

INJECT='''
import time
from foundry.github_setup import import_github_setup
from foundry.images import ingest_image
from foundry.domain import GENERATION_VERSION,uid
fixture_rows=ROWS
fixture_images=IMAGES
fixture_png=base64.b64decode(PNG)
original_transport=app.ws.net.transport
def fixture_transport(url):
    time.sleep(.075)
    if url.startswith('https://cards.scryfall.io/'):return fixture_png,'image/png',{}
    if url in fixture_rows:return json.dumps(fixture_rows[url]).encode(),'application/json',{}
    if url in fixture_images:return base64.b64decode(fixture_images[url]),'image/png',{}
    return original_transport(url)
app.ws.net.transport=fixture_transport
original_request=request
def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/seed-job-families':
        front=ingest_image(app.store,fixture_png);app.store.render_put('fixture-front',front)
        key,version,_=app.ws.compiler.template_identity('standard','auto')
        cards=[]
        for index in range(24):
            name='Export '+str(index)
            cards.append({'id':uid(),'name':name,'quantity':1,'scryfall':{'name':name,'layout':'normal','image_uris':{'png':'https://cards.scryfall.io/'+str(index)+'.png'}},
                'faces':[{'id':uid(),'name':name,'compiled':{'renderKey':'fixture-front','generationVersion':GENERATION_VERSION,'templateKey':key,'templateVersion':version}}]})
        deck=app.ws.new_deck('Job-family fixture');deck.update(cards=cards,status='prepared')
        deck['settings']['backAsset']=front['id'];deck=app.store.put('decks',deck,deck['revision'])
        result={'deckId':deck['id']}
    elif str(url)=='/api/__test__/files':
        result={'files':[p.name for p in (app.store.home/'orders').glob('*.zip')]}
    elif method=='POST' and str(url) in ['/api/setup/github-import','/api/decks/'+getattr(app,'fixture_deck','')+'/review-images'] and json.loads(body).get('serial'):
        data=json.loads(body)
        operation=(lambda update,cancel:import_github_setup(app.ws,data,update,cancel)) if str(url).endswith('github-import') else (lambda update,cancel:app.ws.review_images(app.fixture_deck,update,cancel))
        result=app.jobs.start('Serial fixture',operation)
    else:return original_request(app,method,url,body,headers)
    if str(url)=='/api/__test__/seed-job-families':app.fixture_deck=result['deckId']
    return {'status':200,'mime':'application/json','body':json.dumps(result).encode(),'headers':{}}
'''
DRIVE='''async({deckId,kind,serial,github})=>{
    const ui=await import(`/site/ui.js`),path=kind===`github`?`/api/setup/github-import`:`/api/decks/${deckId}/review-images`;
    const payload={serial,url:github};
    const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    const terminal=async id=>{let job;do{await wait(20);job=await ui.api(`/api/jobs/${id}`);}while([`queued`,`running`].includes(job.state));return job;};
    const started=performance.now(),queued=await ui.api(path,payload);
    await wait(20);
    const foreground=performance.now();await ui.api(`/api/decks`);
    const foregroundSeconds=(performance.now()-foreground)/1000;
    const state=await ui.api(`/api/jobs/${queued.id}`),done=await terminal(queued.id);
    if(done.state!==`done`)throw new Error(JSON.stringify(done));
    let zipFiles=null;
    if(kind===`review`){const response=await fetch(done.result.download);if(!response.ok)throw new Error(`Missing ZIP`);zipFiles=(await ui.api(`/api/__test__/files`)).files.length;}
    const completedSeconds=(performance.now()-started)/1000;
    const second=await ui.api(path,payload);await wait(20);
    const cancel=performance.now();await ui.api(`/api/jobs/${second.id}/cancel`,{});
    const cancelled=await terminal(second.id);
    if(cancelled.state!==`cancelled`)throw new Error(JSON.stringify(cancelled));
    if(kind===`review`&&zipFiles!==(await ui.api(`/api/__test__/files`)).files.length)throw new Error(`Cancelled ZIP was published`);
    return {kind,serial,foregroundSeconds,stateAfterForeground:state.state,doneAfterForeground:state.done,completedSeconds,cancelFinishSeconds:(performance.now()-cancel)/1000};
}'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/job-family-profile.json')
    args=parser.parse_args()
    remote=BundleRemote(back='custom');rows={};images={}
    for path,value in remote.rows.items():rows['https://api.github.com/repos/'+remote.repo+'/contents/'+path.replace(' ','%20')+'?ref=main']=value
    for path,value in remote.images.items():images['https://raw.githubusercontent.com/'+remote.repo+'/main/'+path.replace(' ','%20')]=base64.b64encode(value).decode()
    injected=INJECT.replace('ROWS',repr(rows)).replace('IMAGES',repr(images)).replace('PNG',repr(base64.b64encode(png(size=(30,42))).decode()))
    with tempfile.TemporaryDirectory(prefix='pf-job-families-') as temporary:
        tmp=Path(temporary);build_site(tmp);site=copy_site(tmp)
        worker=site/'web/engine-worker.js';source=worker.read_text(encoding='utf-8');anchor='def browser_request(method, url, body, headers):'
        assert source.count(anchor)==1
        worker.write_text(source.replace(anchor,injected+'\n'+anchor),encoding='utf-8')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=False)
                try:
                    page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto('http://127.0.0.1:'+str(server.server_port));page.locator('#import-deck').wait_for(timeout=120000)
                    deck=page.evaluate("async()=>{const ui=await import('/site/ui.js');return ui.api('/api/__test__/seed-job-families',{});}")
                    trials=[]
                    for kind in ['github','review']:
                        for serial in [True,False,False,True]:
                            row=page.evaluate(DRIVE,{'deckId':deck['deckId'],'kind':kind,'serial':serial,'github':remote.url});trials.append(row);print(json.dumps(row),flush=True)
                            if not serial:
                                assert row['foregroundSeconds']<.75,row
                                assert row['stateAfterForeground']=='running',row
                    assert not errors,errors
                    report={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'at':time.time(),
                        'note':'Actual static engine/import/export paths; temporary fixture adds 75ms per network read. No native rendering or live throughput claim.','trials':trials}
                    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
                finally:browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()