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
        page.add_script_tag(content=source+'\nwindow.downloadTest={saveApiFile,state};')
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
