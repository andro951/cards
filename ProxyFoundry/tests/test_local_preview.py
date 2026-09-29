"""The double-click launcher serves the static build at a stable loopback origin."""
import runpy
import threading
from pathlib import Path
from urllib.request import urlopen


ROOT=Path(__file__).resolve().parents[1]


def test_windows_launcher_targets_browser_preview():
    launcher=(ROOT/'START_PROXY_FOUNDRY.bat').read_text(encoding='utf-8')
    assert 'START_PROXY_FOUNDRY.pyw' in launcher
    assert 'run.py' not in launcher


def test_preview_serves_site_files_only_on_loopback(tmp_path):
    preview=runpy.run_path(str(ROOT/'START_PROXY_FOUNDRY.pyw'),run_name='preview_test')
    (tmp_path/'index.html').write_text('<meta name="proxy-foundry" content="workspace-v1">',encoding='utf-8')
    (tmp_path/'web').mkdir()
    (tmp_path/'web'/'engine-worker.js').write_text('self.ready=true;',encoding='utf-8')
    server=preview['make_server'](tmp_path,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert server.server_address[0]=='127.0.0.1'
        assert preview['is_foundry_preview'](server.server_port)
        with urlopen(preview['address'](server.server_port)+'web/engine-worker.js') as response:
            assert response.read()==b'self.ready=true;'
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
