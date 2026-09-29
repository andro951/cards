from unittest.mock import patch
import hashlib
import pytest
from foundry.runtime import Runtime
from foundry.network import validate_remote_url
from foundry.domain import STATION_SCRIPT_URL,ValidationError

def test_station_script_uses_allowed_pinned_host():
    assert validate_remote_url(STATION_SCRIPT_URL)==STATION_SCRIPT_URL
    for url in ['https://cardconjurer.app/js/frames/versionStation.js','https://cardconjurer.app/creator/index.html']:
        with pytest.raises(ValidationError):validate_remote_url(url)

def test_station_script_checksum_and_csp_safe_assignment():
    source=b'function setValue(){eval(`${target} = value`);}'
    class Net:
        def __init__(self):self.source=source;self.calls=[]
        def fetch(self,url,**kwargs):
            self.calls.append((url,kwargs))
            return self.source,'text/plain',{'cache':False}
    net=Net();runtime=Runtime(net)
    with patch('foundry.runtime.STATION_SCRIPT_SHA256',hashlib.sha256(source).hexdigest()):
        result,mime=runtime.station_script()
    assert b'eval(`${target} = value`);' not in result and b'object[key] = value' in result
    assert mime=='application/javascript'
    assert net.calls==[(STATION_SCRIPT_URL,{'immutable':True})]
    assert runtime.diagnostic()['files']['/js/frames/versionStation.js']['url']==STATION_SCRIPT_URL
    assert runtime.diagnostic()['files']['/js/frames/versionStation.js']['cache'] is False
    net.source=b'eval(`${target} = value`);'
    with patch('foundry.runtime.STATION_SCRIPT_SHA256',hashlib.sha256(source).hexdigest()):
        with pytest.raises(ValidationError,match='verified version'):runtime.station_script()
