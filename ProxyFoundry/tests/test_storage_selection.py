import json
from pathlib import Path

from foundry.storage import configured_home,launcher_config_path,save_configured_home


def test_saved_storage_location_is_persistent(tmp_path,monkeypatch):
    monkeypatch.delenv('BULK_PROXY_FORGE_HOME',raising=False)
    monkeypatch.delenv('PROXY_FOUNDRY_HOME',raising=False)
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'data'))
    chosen=tmp_path/'chosen-drive'/'BulkProxyForge'
    save_configured_home(chosen)
    assert configured_home()==chosen.resolve()
    payload=json.loads(launcher_config_path().read_text(encoding='utf-8'))
    assert payload['home']==str(chosen.resolve())


def test_first_run_storage_prompt_contract_is_present():
    source=(Path(__file__).resolve().parents[1]/'foundry/storage.py').read_text(encoding='utf-8')
    for text in ['Pick a specific folder','Folder it will use:','Continue','candidate_drive_homes','ensure_storage_home_selected']:
        assert text in source
    run=(Path(__file__).resolve().parents[1]/'run.py').read_text(encoding='utf-8')
    assert 'ensure_storage_home_selected()' in run
