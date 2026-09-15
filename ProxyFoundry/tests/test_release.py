"""Validate the exact distribution allowlist and per-file SHA-256 manifest."""
import hashlib,json,zipfile
from scripts.package_release import build

def test_complete_release_contains_no_runtime_cache_or_fonts(tmp_path):
    out=tmp_path/'release.zip';manifest=build(out)
    required=['START_PROXY_FOUNDRY.bat','START_LEGACY_CARD_TOOLS.bat','RUN_TESTS.bat','run.py','site/index.html','site/app.js','site/deck.js','site/setup.js','site/render.js','site/styles.css','foundry/server.py','extension/manifest.json','extension/bridge.js','extension/background.js','vendor/card_tools/pipeline/card_data_to_cardconjurer.py']
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert all('ProxyFoundry/'+p in names for p in required)
        assert not any(p.lower().endswith(('.ttf','.otf','.woff','.woff2','.pem','.crx','.pyc')) for p in names)
        assert not any('/test-results/' in p or '/.git/' in p or '/checkpoints/' in p for p in names)
        saved=json.loads(z.read('ProxyFoundry/RELEASE_MANIFEST.json'))
        assert saved==manifest
        for name,digest in saved['files'].items():assert hashlib.sha256(z.read('ProxyFoundry/'+name)).hexdigest()==digest
