"""Interactive actual-disk benchmark using the production browser save regression."""
import functools
import hashlib
import http.server
import json
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_website import build_site,copy_site
from test_browser_storage import test_native_png_save_benchmark_preserves_bytes_and_survives_reload
from playwright.sync_api import sync_playwright


def main():
    parent=Path(sys.argv[1]).resolve()
    name='BulkProxyForge-Save-Benchmark-'+uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix='bpf-folder-benchmark-') as temporary:
        tmp=Path(temporary);build_site(tmp);site=copy_site(tmp)
        (site/'select-folder.html').write_text('<title>BulkProxyForge real-folder benchmark</title><button id="select">Select Documents for benchmark</button>',encoding='utf-8')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',8769),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as playwright:
                context=playwright.chromium.launch_persistent_context(str(ROOT/'test-results/selected-folder-profile'),headless=False)
                context.on('close',lambda:print('Browser context closed.',flush=True))
                context.on('page',lambda page:page.on('pageerror',lambda error:print('Page error:',error,flush=True)))
                try:
                    origin='http://127.0.0.1:'+str(server.server_port)
                    page=context.new_page();page.goto(origin+'/select-folder.html')
                    page.evaluate("""name=>{document.querySelector('#select').onclick=async()=>{
                      try{
                        const parent=await showDirectoryPicker({mode:'readwrite',startIn:'documents'});
                        const folder=await parent.getDirectoryHandle(name,{create:true});
                        const marker=await folder.getFileHandle('benchmark-proof.txt',{create:true});
                        const stream=await marker.createWritable();await stream.write(name);await stream.close();
                        await (await import('/web/storage-choice.js')).useFolder(folder);
                        window.selection={name:folder.name,parent:parent.name};
                      }catch(error){window.selection={error:error.message};}
                    };}""",name)
                    page.click('#select');print('Select Documents in the benchmark folder picker.',flush=True)
                    page.wait_for_function('window.selection',timeout=900000)
                    selection=page.evaluate('window.selection');assert 'error' not in selection,selection
                    folder=parent/name
                    assert (folder/'benchmark-proof.txt').read_text()==name,('Disk folder did not match the selected folder',str(folder),selection)
                    page.evaluate("document.body.textContent='Folder connected. Running save benchmark; please leave this browser open.'")
                    original=ROOT/'test-results/render-save-benchmark.json'
                    previous=original.read_bytes() if original.is_file() else None
                    try:
                        test_native_png_save_benchmark_preserves_bytes_and_survives_reload((site,context,origin),tmp)
                        report=json.loads(original.read_text())
                    finally:
                        if previous is not None:original.write_bytes(previous)
                        else:original.unlink(missing_ok=True)
                    report['storageType']='selected-folder';report['folder']=str(folder)
                    expected=report['runs'][-1]['asset'];asset=folder/'assets'/expected[:2]/expected
                    assert asset.is_file() and hashlib.sha256(asset.read_bytes()).hexdigest()==expected
                    renders=list((folder/'renders').rglob('*.png'));assert renders
                    assert any(hashlib.sha256(p.read_bytes()).hexdigest()==expected for p in renders)
                    assert (folder/'workspace.sqlite3').is_file()
                    with Image.open(asset) as image:assert image.size==(2010,2814)
                    report['diskVerified']=True;report['reloadVerified']=True;report['renderFiles']=len(renders)
                    (ROOT/'test-results/render-save-selected-folder.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(json.dumps(report,indent=2),flush=True)
                finally:context.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
