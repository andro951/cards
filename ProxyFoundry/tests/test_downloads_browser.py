"""Exercise download-folder selection and large-export streaming in Chromium."""
import os,re
from pathlib import Path
import pytest
from ui_component import ui_source

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in browser download tests')

@pytest.fixture
def download_page():
    from playwright.sync_api import sync_playwright
    source=ui_source()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(accept_downloads=True)
        page.add_script_tag(content=source+'\nwindow.downloadTest={saveApiFile,downloadReviewFile,state};')
        page.evaluate('downloadTest.state.bootstrap={browser:true}')
        yield page
        browser.close()

@pytest.mark.parametrize('filename',['card_review.png','small_export.zip'])
def test_small_exports_use_normal_download_without_picker(download_page,filename):
    page=download_page
    page.evaluate('''() => {
        window.showSaveFilePicker=()=>{throw new Error('Small download opened a picker');};
        window.fetch=async()=>new Response(new Uint8Array([1,2,3,4]));
    }''')
    with page.expect_download() as result:
        page.evaluate('name=>downloadTest.saveApiFile("/api/files/export",name,4)',filename)
    download=result.value
    assert download.suggested_filename==filename
    assert Path(download.path()).read_bytes()==bytes([1,2,3,4])

def test_large_exports_keep_streaming_file_picker(download_page):
    page=download_page
    result=page.evaluate('''async () => {
        const evidence={pickers:0,writes:[],closed:false,range:null};
        window.showSaveFilePicker=async options=>{
            evidence.pickers++;evidence.filename=options.suggestedName;
            return {createWritable:async()=>({
                write:async chunk=>evidence.writes.push([...new Uint8Array(chunk)]),
                close:async()=>{evidence.closed=true;},
                abort:async()=>{throw new Error('Unexpected abort');}
            })};
        };
        window.fetch=async(path,options)=>{
            evidence.range=options.headers.Range;
            return new Response(new Uint8Array([1,2,3,4]),{
                status:206,headers:{'Content-Range':'bytes 0-3/4'}
            });
        };
        await downloadTest.saveApiFile('/api/files/export','large.zip',51*1024*1024);
        return evidence;
    }''')
    assert result=={'pickers':1,'writes':[[1,2,3,4]],'closed':True,
                    'range':'bytes=0-4194303','filename':'large.zip'}


@pytest.mark.parametrize('size',[4,1300*1024*1024])
def test_review_downloads_always_use_download_folder_and_release_staging(download_page,size):
    page=download_page
    page.evaluate("""() => {
        window.showSaveFilePicker=()=>{throw new Error('Review download opened a picker');};
        window.reviewRequests=[];
        window.fetch=async(path,options)=>{
            reviewRequests.push({path,method:options?.method||'GET'});
            if(options?.method==='POST')return new Response(JSON.stringify({ok:true}));
            return new Response(new Uint8Array([1,2,3,4]));
        };
    }""")
    with page.expect_download() as result:
        page.evaluate("size=>downloadTest.downloadReviewFile({download:'/api/review-downloads/file',cleanup:'/api/review-downloads/token/delete',filename:'reviews.zip',bytes:size})",size)
    assert Path(result.value.path()).read_bytes()==bytes([1,2,3,4])
    assert page.evaluate('reviewRequests')==[{'path':'/api/review-downloads/file','method':'GET'},{'path':'/api/review-downloads/token/delete','method':'POST'}]


def test_failed_review_download_releases_staging(download_page):
    page=download_page
    result=page.evaluate("""async()=>{
        const calls=[];
        window.fetch=async(path,options)=>{
            calls.push(path);
            return options?.method==='POST'?new Response(JSON.stringify({ok:true})):new Response(JSON.stringify({error:'Download failed'}),{status:500});
        };
        let error='';
        try{await downloadTest.downloadReviewFile({download:'/review',cleanup:'/cleanup',filename:'review.png',bytes:4});}
        catch(failure){error=failure.message;}
        return {calls,error};
    }""")
    assert result=={'calls':['/review','/cleanup'],'error':'Download failed'}


from tests.test_browser_storage import static_browser

def test_static_review_downloads_release_workspace_files_after_browser_receives_them(static_browser):
    import io,zipfile
    directory,context,origin=static_browser
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    injected="""
original_review_request=request

def request(app,method,url,body,headers):
    if str(url)=='/api/__test__/seed-review-downloads':
        import base64,io,zipfile
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfYQAAAAASUVORK5CYII=')
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('card_review.png',raw)
        outputs=[]
        for name,content in [('card_review.png',raw),('review_images.zip',archive.getvalue())]:
            token,path=app.ws._review_download(name);path.write_bytes(content)
            outputs.append(app.ws._review_download_result(token,name,path,1))
        return {'status':200,'mime':'application/json','body':json.dumps(outputs).encode(),'headers':{}}
    if str(url)=='/api/__test__/review-download-files':
        root=app.store.home/'tmp'/'review-downloads'
        files={'staging':len(list(root.iterdir())) if root.exists() else 0, 'orders':len(list((app.store.home/'orders').iterdir()))}
        return {'status':200,'mime':'application/json','body':json.dumps(files).encode(),'headers':{}}
    return original_review_request(app,method,url,body,headers)
"""
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',injected+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin,wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    page.evaluate("() => {window.showSaveFilePicker=()=>{throw new Error('Review downloads must not open a picker');};}")
    outputs=page.evaluate("async()=>await (await fetch('/api/__test__/seed-review-downloads')).json()")
    for output in outputs:
        with page.expect_download() as result:
            page.evaluate("async output=>{const ui=await import('/site/ui.js');await ui.downloadReviewFile(output);}",output)
        data=Path(result.value.path()).read_bytes()
        assert result.value.suggested_filename==output['filename']
        if output['filename'].endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(data)) as z:assert z.read('card_review.png').startswith(b'\x89PNG')
        else:assert data.startswith(b'\x89PNG')
    assert page.evaluate("async()=>await (await fetch('/api/__test__/review-download-files')).json()")=={'staging':0,'orders':0}

    isolated=page.evaluate("""async()=>{
        const {WorkspaceFiles}=await import('/web/workspace-files.js');
        const root=await navigator.storage.getDirectory();
        const selected=await root.getDirectoryHandle('selected-folder-test',{create:true});
        const scratch=await root.getDirectoryHandle('separate-scratch-test',{create:true});
        const files=new WorkspaceFiles(selected,scratch),path='tmp/review-downloads/export.png';
        await files.execute('mkdir','tmp/review-downloads',new URLSearchParams());
        await files.execute('write',path,new URLSearchParams({offset:'0'}),new Uint8Array([1,2,3]));
        await files.close(path);
        const selectedNames=[];
        for await(const name of selected.keys())selectedNames.push(name);
        const stored=await files.file(path);
        return {selectedNames,bytes:[...new Uint8Array(await stored.arrayBuffer())]};
    }""")
    assert isolated=={'selectedNames':[],'bytes':[1,2,3]}
    #An interrupted export is removed on the next app start, without touching orders.
    page.evaluate("async()=>await fetch('/api/__test__/seed-review-downloads')")
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    assert page.evaluate("async()=>await (await fetch('/api/__test__/review-download-files')).json()")=={'staging':0,'orders':0}
