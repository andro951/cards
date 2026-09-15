import hashlib
from unittest.mock import patch
import pytest
from foundry.runtime import Runtime
from foundry.network import validate_remote_url
from foundry.domain import STATION_SCRIPT_URL,ValidationError

def test_only_exact_native_script_allowed():
    assert validate_remote_url(STATION_SCRIPT_URL)==STATION_SCRIPT_URL
    for url in [STATION_SCRIPT_URL+'?other=1',STATION_SCRIPT_URL.replace('versionStation','evil'),'https://cardconjurer.app/creator/index.html']:
        with pytest.raises(ValidationError):validate_remote_url(url)

def test_station_script_checksum_and_csp_safe_assignment():
    raw=b'eval(`${target} = value`);'
    class Net:
        def fetch(self,url,**kwargs):return raw,'application/javascript',{}
    runtime=Runtime(Net())
    with pytest.raises(ValidationError,match='verified version'):runtime.station_script()
    with patch('foundry.runtime.STATION_SCRIPT_SHA256',hashlib.sha256(raw).hexdigest()):
        result,mime=runtime.station_script()
        assert b'eval(' not in result and b'object[key] = value' in result
        assert mime=='application/javascript'
