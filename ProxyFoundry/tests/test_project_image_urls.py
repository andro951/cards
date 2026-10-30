"""Actual project-path deployment must load assets through its scoped service worker."""
import io,os,shutil,subprocess
import pytest
from PIL import Image
from test_browser_storage import static_browser,ROOT

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual browser project-path images')

@pytest.mark.parametrize('static_browser',['msedge'] if os.name=='nt' else [None],indirect=True)
def test_images_and_thumbnails_decode_inside_project_scope(static_browser):
    directory,context,origin=static_browser
    source=directory.with_name('original-site');directory.rename(source);directory.mkdir()
    subprocess.run([os.sys.executable,str(ROOT/'scripts/build_web.py'),'--base-path','/cards/','--output',str(directory/'cards')],cwd=ROOT,check=True,capture_output=True)
    page=context.new_page();page.goto(origin+'/cards/');page.locator('#import-deck').wait_for(timeout=90000)
    raw=io.BytesIO();Image.new('RGB',(120,160),'purple').save(raw,'PNG')
    result=page.evaluate('''async bytes=>{
      const ui=await import('/cards/site/ui.js');
      const image=await ui.blobRequest('/api/uploads',new Uint8Array(bytes),'image/png');
      const paths=[ui.asset(image.id),ui.thumbnail('/api/assets/'+image.id)];
      const results=[];
      for(const src of paths){const img=document.createElement('img');img.src=src;document.body.append(img);await img.decode();results.push({path:new URL(img.src).pathname,width:img.naturalWidth,height:img.naturalHeight});}
      return {results,external:ui.thumbnail('https://example.com/image.png'),twice:ui.workspaceUrl(paths[0])};
    }''',list(raw.getvalue()))
    assert all(item['path'].startswith('/cards/api/assets/') and item['width']>0 for item in result['results'])
    assert result['results'][0]['width']==120 and result['external']=='https://example.com/image.png'
    assert result['twice']==result['results'][0]['path']
