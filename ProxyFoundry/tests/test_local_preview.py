"""The double-click launcher serves the static build at a stable loopback origin."""
import runpy
import threading
from pathlib import Path
from urllib.request import urlopen


ROOT=Path(__file__).resolve().parents[1]


def test_windows_launcher_targets_browser_preview():
    old_launcher=(ROOT/'START_PROXY_FOUNDRY.bat').read_text(encoding='utf-8')
    launcher=(ROOT/'START_BULK_PROXY_FORGE.bat').read_text(encoding='utf-8')
    assert 'run.py' in old_launcher
    assert 'START_BULK_PROXY_FORGE.pyw' not in old_launcher
    assert 'START_BULK_PROXY_FORGE.pyw' in launcher
    assert 'run.py' not in launcher


def test_preview_serves_site_files_only_on_loopback(tmp_path):
    preview=runpy.run_path(str(ROOT/'START_BULK_PROXY_FORGE.pyw'),run_name='preview_test')
    (tmp_path/'index.html').write_text('<meta name="proxy-foundry" content="workspace-v1">',encoding='utf-8')
    (tmp_path/'web').mkdir()
    (tmp_path/'web'/'engine-worker.js').write_text('self.ready=true;',encoding='utf-8')
    (tmp_path/'web'/'runtime.zip').write_bytes(b'PK\x03\x04fixture')
    server=preview['make_server'](tmp_path,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert server.server_address[0]=='127.0.0.1'
        assert preview['is_foundry_preview'](server.server_port)
        with urlopen(preview['address'](server.server_port)+'web/engine-worker.js') as response:
            assert response.read()==b'self.ready=true;'
            assert response.headers['Cache-Control']=='no-cache'
        with urlopen(preview['address'](server.server_port)) as response:
            assert response.headers['Cache-Control']=='no-cache'
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_launcher_builds_before_reopening_an_existing_preview(monkeypatch):
    preview=runpy.run_path(str(ROOT/'START_BULK_PROXY_FORGE.pyw'),run_name='preview_test')
    calls=[]
    class Built:
        returncode=0
        stderr=''
        stdout=''
    monkeypatch.setitem(preview['build_and_start'].__globals__['subprocess'].__dict__,'run',
                        lambda *args,**kwargs:(calls.append('build') or Built()))
    monkeypatch.setitem(preview['build_and_start'].__globals__,'is_foundry_preview',
                        lambda:(calls.append('detect') or True))
    class Events:
        def put(self,item):
            calls.append(item[0])
            if item[0]=='existing':assert item[1].startswith(preview['address']()+'?_pf_launch=')
    preview['build_and_start'](Events())
    assert calls==['status','build','detect','existing']


def test_every_browser_open_bypasses_cached_startup_on_same_workspace_origin(monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    preview=runpy.run_path(str(ROOT/'START_BULK_PROXY_FORGE.pyw'),run_name='preview_test')
    opened=[]
    monkeypatch.setattr(preview['webbrowser'],'open',lambda url,**kwargs:opened.append(url))
    preview['open_site']();preview['open_site']()
    assert len(set(opened))==2
    for url in opened:
        parsed=urlsplit(url)
        assert parsed.scheme=='http' and parsed.netloc=='127.0.0.1:8767' and parsed.path=='/'
        assert len(parse_qs(parsed.query)['_pf_launch'][0])==32


def test_old_app_marker_alone_is_not_treated_as_static_preview(tmp_path):
    preview=runpy.run_path(str(ROOT/'START_BULK_PROXY_FORGE.pyw'),run_name='preview_test')
    (tmp_path/'index.html').write_text('<meta name="proxy-foundry" content="workspace-v1">',encoding='utf-8')
    server=preview['make_server'](tmp_path,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert not preview['is_foundry_preview'](server.server_port)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
