from pathlib import Path
import os
from foundry.storage import default_home

ROOT=Path(__file__).resolve().parents[1]

def test_visible_branding_and_theme_are_bulk_proxy_forge():
    html=(ROOT/'site/index.html').read_text()
    assert '<title>Bulk Proxy Forge' in html
    assert 'Bulk Proxy Forge<small>DECK & PRINT STUDIO' in html
    assert '/site/forge-theme.css' in html
    assert 'PROXY FOUNDRY 1.3' not in html
    manifest=(ROOT/'extension/manifest.json').read_text()
    assert 'Bulk Proxy Forge Print Helper' in manifest
    assert (ROOT/'site/forge-theme.css').is_file()

def test_launcher_and_console_use_current_product_name():
    assert 'title Bulk Proxy Forge' in (ROOT/'START_PROXY_FOUNDRY.bat').read_text(errors='ignore')
    assert 'BULK PROXY FORGE' in (ROOT/'run.py').read_text()

def test_storage_new_name_and_legacy_compatibility(tmp_path,monkeypatch):
    monkeypatch.delenv('BULK_PROXY_FORGE_HOME',raising=False);monkeypatch.delenv('PROXY_FOUNDRY_HOME',raising=False)
    if os.name=='nt':monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    else:monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path))
    assert default_home()==tmp_path/'BulkProxyForge'
    (tmp_path/'ProxyFoundry').mkdir()
    assert default_home()==tmp_path/'ProxyFoundry'
    (tmp_path/'BulkProxyForge').mkdir()
    assert default_home()==tmp_path/'BulkProxyForge'

def test_internal_protocol_identifiers_remain_compatible():
    bridge=(ROOT/'extension/site-bridge.js').read_text()
    assert 'proxy-foundry-helper' in bridge and 'proxy-foundry-workspace' in bridge
    backup=(ROOT/'foundry/backup.py').read_text()
    assert "'proxy-foundry-backup'" in backup
