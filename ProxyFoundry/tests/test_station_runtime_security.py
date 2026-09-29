from unittest.mock import patch
import pytest
from foundry.runtime import Runtime
from foundry.network import validate_remote_url
from foundry.domain import STATION_SCRIPT_URL,ValidationError

def test_only_exact_native_script_allowed():
    assert validate_remote_url(STATION_SCRIPT_URL)==STATION_SCRIPT_URL
    for url in [STATION_SCRIPT_URL+'?other=1',STATION_SCRIPT_URL.replace('versionStation','evil'),'https://cardconjurer.app/creator/index.html']:
        with pytest.raises(ValidationError):validate_remote_url(url)

def test_station_script_checksum_and_csp_safe_assignment(tmp_path):
    class Net:
        def fetch(self,url,**kwargs):raise AssertionError('Station script must be bundled.')
    runtime=Runtime(Net())
    result,mime=runtime.station_script()
    assert b'eval(`${target} = value`);' not in result and b'object[key] = value' in result
    assert mime=='application/javascript'
    assert runtime.diagnostic()['files']['/js/frames/versionStation.js']['bundled'] is True
    bad=tmp_path/'versionStation.js'
    bad.write_bytes(b'eval(`${target} = value`);')
    with patch.object(Runtime,'STATION_SCRIPT_FILE',bad):
        with pytest.raises(ValidationError,match='verified version'):runtime.station_script()
    bad.unlink()
    with patch.object(Runtime,'STATION_SCRIPT_FILE',bad):
        with pytest.raises(ValidationError,match='missing from this build'):runtime.station_script()
