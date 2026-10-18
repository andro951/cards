"""Import a fresh Studio template through the actual static browser application."""
import functools,http.server,json,os,threading,time
from pathlib import Path
import pytest
from scripts.static_server import StaticSiteServer
from test_website import build_site,copy_site
from test_visual_template_native import build_studio_export

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in actual Pyodide browser import')


def test_static_browser_imports_and_reexports_studio_template(tmp_path):
    from playwright.sync_api import sync_playwright
    exported=build_studio_export()
    source=tmp_path/'studio.json';source.write_text(json.dumps(exported),encoding='utf-8')
    build_site(tmp_path);site=copy_site(tmp_path)
    server=StaticSiteServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(site)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            try:
                page.goto(f'http://127.0.0.1:{server.server_port}/#templates',wait_until='domcontentloaded')
                page.get_by_role('button',name='Import Template',exact=True).wait_for(timeout=120000)
                with page.expect_file_chooser() as chooser:
                    page.get_by_role('button',name='Import Template',exact=True).click()
                chooser.value.set_files(str(source))
                started=time.monotonic()
                assert page.get_by_role('button',name='Importing template…',exact=True).is_disabled()
                page.get_by_role('heading',name=exported['name'],exact=True).wait_for(timeout=120000)
                templates=page.evaluate('async () => (await import("/site/ui.js")).api("/api/templates")')
                imported=next(item for item in templates if item['name']==exported['name'])
                assert imported['visualRecipe']['version']==1
                assert all(src.startswith('/api/assets/') for src in imported['visualRecipe']['sources'].values())
                import_seconds=time.monotonic()-started
                page.get_by_role('button',name='Edit',exact=True).click()
                page.get_by_role('heading',name='Edit in Template Studio',exact=True).wait_for()
                assert page.get_by_role('button',name='Download editable template',exact=True).is_enabled()
                page.keyboard.press('Escape')
                with page.expect_download(timeout=120000) as download:
                    page.get_by_role('button',name='Export JSON',exact=True).click()
                output=tmp_path/'browser-export.json';download.value.save_as(str(output))
                restored=json.loads(output.read_text(encoding='utf-8'))
                assert restored['editorSource']['assetTable']=='visualRecipe.sources'
                assert len(restored['assets'])>20
                assert restored['visualRecipe']==imported['visualRecipe']
                report=Path(__file__).resolve().parents[1]/'test-results/studio-browser-import.json'
                report.write_text(json.dumps({'importSeconds':import_seconds,'portableBytes':source.stat().st_size,'storedImageCount':len(restored['assets'])}),encoding='utf-8')
                assert not errors
            finally:browser.close()
    finally:server.shutdown();server.server_close()