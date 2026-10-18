"""Measure preview bytes and offline 400-card order filtering against a baseline."""
import argparse,io,json,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from ui_component import ui_source
from foundry.browser import create_app,request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--baseline',default='2098941')
    parser.add_argument('--output',type=Path,default=ROOT/'test-results/order-previews-profile.json')
    args=parser.parse_args();raw=args.image.read_bytes()
    report={'baseline':args.baseline,'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'note':'Preview byte/pixel measurements through the production browser API. Order filtering is offline DOM/JS only; excludes initial mount, network, image decoding and native rendering.','trials':[]}
    with tempfile.TemporaryDirectory(prefix='pf-preview-profile-') as temporary:
        app=create_app(Path(temporary),lambda url:None,'http://127.0.0.1:8767')
        try:
            with Image.open(io.BytesIO(raw)) as image:size=image.size
            asset=app.store.add_asset(raw,'image/png',*size);path='/api/assets/'+asset['id']
            rows=[]
            for repeat in range(3):
                start=time.perf_counter();result=request(app,'GET',path+'/thumbnail');assert result['status']==200
                png=(app.store.home/result['file']).read_bytes()
                with Image.open(io.BytesIO(png)) as image:thumb=image.size
                rows.append({'repeat':repeat,'seconds':time.perf_counter()-start,'bytes':len(png),'size':thumb})
            original=request(app,'GET',path)
            assert (app.store.home/original['file']).read_bytes()==raw
            report['image']={'sourceBytes':len(raw),'sourceSize':size,'thumbnailTrials':rows,'originalUnchanged':True}
        finally:app.close()
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            for baseline in [True,False,False,True]:
                page=browser.new_page()
                try:
                    page.set_content('<body><div id="modal-host"></div><div id="toast-host"></div>')
                    page.add_script_tag(content=ui_source())
                    source=subprocess.check_output(['git','show',args.baseline+':ProxyFoundry/web/review-browser.js'],cwd=ROOT).decode('utf-8') if baseline else (ROOT/'web/review-browser.js').read_text(encoding='utf-8')
                    source='\n'.join(line for line in source.splitlines() if not line.startswith('import ')).replace('export ','')
                    page.add_script_tag(content=source)
                    row=page.evaluate('''()=>{
                        const cards=Array.from({length:400},(_,index)=>({deckId:'deck',cardId:String(index),name:'Card '+String(index).padStart(3,'0'),deckName:'Deck',frontAsset:index.toString(16).padStart(64,'0'),backAsset:'b'.repeat(64)}));
                        showReview({id:'order',count:400,bytes:100,decks:[{id:'deck',name:'Deck',backAsset:'b'.repeat(64)}],cards},['deck'],true,()=>{},()=>{});
                        const grid=document.querySelector('#browser-pair-grid'),search=document.querySelector('.modal-body input'),first=grid.querySelector('img');
                        search.focus();let mutations=0;const observer=new MutationObserver(rows=>{mutations+=rows.length;});observer.observe(grid,{childList:true,subtree:true});
                        const start=performance.now();
                        for(let index=0;index<40;index++){search.value=index%2?``:`Card 00`;search.dispatchEvent(new Event(`input`));}
                        const seconds=(performance.now()-start)/1000;mutations+=observer.takeRecords().length;observer.disconnect();
                        return {seconds,mutations,sameImage:first===grid.querySelector('img'),focused:document.activeElement===search,imageCount:grid.querySelectorAll('img').length,thumbnailCount:[...grid.querySelectorAll('img')].filter(i=>i.getAttribute('src').endsWith('/thumbnail')).length};
                    }''')
                    row['baseline']=baseline;report['trials'].append(row)
                    if not baseline:assert row['mutations']==0 and row['sameImage'] and row['focused'] and row['thumbnailCount']==400,row
                    print(json.dumps(row),flush=True)
                finally:page.close()
        finally:browser.close()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()