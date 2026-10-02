"""Compare collection updates against the previous committed UI with offline fixtures.

No network, renderer or storage-throughput claim. This measures DOM/JS updates
in headless Chromium, retaining identical collection data in both variants.
"""
import argparse,json,re,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_dom_offline as fixture


def bundled(revision):
    out=[]
    for name in ['diagnostics','work','ui','deletion','credits','backs','github-setup','render','frame-picker','setup','orders','templates','settings','deck','app']:
        path='site/'+name+'.js'
        text=subprocess.check_output(['git','show',revision+':ProxyFoundry/'+path],cwd=ROOT).decode('utf-8') if revision and name in {'deck','app'} else (ROOT/path).read_text(encoding='utf-8')
        exports=re.findall(r'export\s+(?:async\s+)?(?:function|const|let|class)\s+([$\w]+)',text)
        if name=='app':exports.append('showLibrary')
        text=re.sub(r"import\s+\{([^}]+)\}\s+from\s+'\./([^']+)\.js';",lambda m:'const {'+m[1]+'}=__mod_'+m[2].replace('-','_')+';',text)
        text=text.replace("await import('./ui.js')",'__mod_ui');text=re.sub(r'\bexport\s+','',text)
        out.append('const __mod_'+name.replace('-','_')+'=(()=>{\n'+text+'\nreturn {'+','.join(exports)+'};})();')
    return '\n'.join(out)


def trial(revision):
    fixture.bundle=lambda:bundled(revision)
    with tempfile.TemporaryDirectory() as temporary:
        session=fixture.dom_page.__wrapped__(Path(temporary));page,errors=next(session)
        try:
            page.evaluate("""()=>{
                const fixture=window.__fixture,deck=fixture.deck,card=deck.cards[0];
                deck.cards=Array.from({length:400},(_,index)=>({...structuredClone(card),id:`00000000-0000-4000-8000-${String(index+1).padStart(12,'0')}`,name:`Card ${String(index).padStart(3,'0')}`,quantity:1}));
                deck.summary={cards:400,faces:400,rendered:0,warnings:0,errors:0};
                fixture.decks=[deck,...Array.from({length:299},(_,index)=>({...structuredClone(deck),cards:[],id:`10000000-0000-4000-8000-${String(index+1).padStart(12,'0')}`,name:`Other ${index}`}))];
            }""")
            page.locator('.deck-tile').click();page.locator('#card-search').wait_for()
            cards=page.evaluate("""async current=>{
                const deck=window.__fixture.deck,input=document.querySelector('#card-search'),button=document.querySelector('[data-card]');input.focus();
                let remounts=0;const observer=new MutationObserver(records=>remounts+=records.length);observer.observe(document.querySelector('#main'),{childList:true});
                const started=performance.now();
                for(let index=0;index<20;index++){deck.summary.rendered=index;
                    if(current)await __mod_deck.refreshDeckProgress(deck.id);else await __mod_deck.showDeck(deck.id,'cards');}
                const seconds=(performance.now()-started)/1000;await Promise.resolve();observer.disconnect();
                const refresh={seconds,remounts,inputRetained:input===document.querySelector('#card-search'),buttonRetained:button===document.querySelector('[data-card]'),focusRetained:input===document.activeElement};
                const searchStart=performance.now();
                for(let index=0;index<40;index++){const search=document.querySelector('#card-search');search.value=index%2?'Card 00':'Card ';search.dispatchEvent(new Event('input'));}
                return {refresh,searchSeconds:(performance.now()-searchStart)/1000};
            }""",not bool(revision))
            page.evaluate("async()=>{location.hash='#decks';await __mod_app.route();}")
            page.locator('#deck-search').wait_for()
            library=page.evaluate("""async current=>{
                const input=document.querySelector('#deck-search');input.focus();let remounts=0,templatesReads=0;
                const fetch=window.fetch;window.fetch=async(path,options)=>{if(path==='/api/templates')templatesReads++;return fetch(path,options);};
                const observer=new MutationObserver(records=>remounts+=records.length);observer.observe(document.querySelector('#main'),{childList:true});
                const started=performance.now();
                for(let index=0;index<20;index++){
                    if(current)await __mod_app.refreshLibraryProgress();else {await __mod_app.refreshLibrary();__mod_app.showLibrary();}}
                const seconds=(performance.now()-started)/1000;await Promise.resolve();observer.disconnect();
                const refresh={seconds,remounts,templatesReads,inputRetained:input===document.querySelector('#deck-search'),focusRetained:input===document.activeElement};
                const searchStart=performance.now();
                for(let index=0;index<40;index++){const search=document.querySelector('#deck-search');search.value=index%2?'Other 1':'Other ';search.dispatchEvent(new Event('input'));}
                return {refresh,searchSeconds:(performance.now()-searchStart)/1000};
            }""",not bool(revision))
            assert not errors,errors
            return {'cards':cards,'library':library}
        finally:
            try:next(session)
            except StopIteration:pass


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',default='d1888b3');parser.add_argument('--output',type=Path,default=ROOT/'test-results/collection-updates.json');options=parser.parse_args()
    report={'note':'Offline DOM/JS fixture: 400 cards, 300 decks, 20 progress updates and 40 search changes per variant. Network, native drawing, persistence and initial mount excluded.','baselineRevision':options.baseline,'trials':[]}
    for revision in [options.baseline,None,None,options.baseline]:
        row={'variant':'baseline' if revision else 'current',**trial(revision)};report['trials'].append(row);print(json.dumps(row),flush=True)
    options.output.parent.mkdir(parents=True,exist_ok=True);options.output.write_text(json.dumps(report,indent=2).rstrip(),encoding='utf-8')


if __name__=='__main__':main()