import pytest
from foundry.runtime import Runtime
from foundry.domain import ValidationError,CC_COMMIT

def test_absolute_native_host_alias_is_resolved_to_pinned_path():
    assert Runtime.upstream_alias('https://cardconjurer.app/img/blank.png')=='/img/blank.png'
    assert Runtime.upstream_alias('https://www.cardconjurer.com/img/frames/a.png?cache=2')=='/img/frames/a.png'
    assert Runtime.upstream_alias('https://cardconjurer.app.evil.test/img/a.png') is None
    assert Runtime.upstream_alias('https://user:pass@cardconjurer.app/img/a.png') is None
    with pytest.raises(ValidationError):Runtime.upstream_alias('https://cardconjurer.app/../secrets')

def test_pinned_asset_requests_not_live_cardconjurer_site():
    calls=[]
    class FakeNet:
        def fetch(self,url,**kwargs):calls.append(url);return b'bytes','image/png',{}
    runtime=Runtime(FakeNet())
    raw,mime=runtime.fetch(Runtime.upstream_alias('https://cardconjurer.app/img/blank.png'))
    assert raw==b'bytes' and CC_COMMIT in calls[0]
    assert 'cardconjurer.app' not in calls[0]
    assert '/archive/' not in calls[0]
