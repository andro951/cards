import os,urllib.request
import pytest
from foundry.runtime import Runtime
from foundry.domain import ValidationError,CC_COMMIT,COMPAT_COMMIT

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

def test_colorless_saga_creature_frame_uses_exact_pinned_gap_source():
    calls=[]
    class FakeNet:
        def fetch(self,url,**kwargs):
            calls.append((url,kwargs))
            if len(calls)<3:raise ValidationError('HTTP 404: missing pinned asset')
            return b'\x89PNG\r\n\x1a\nfixture','image/png',{}
    runtime=Runtime(FakeNet())
    raw,mime=runtime.fetch(Runtime.COLORLESS_SAGA_CREATURE_PATH)
    assert raw.startswith(b'\x89PNG\r\n\x1a\n') and mime=='image/png'
    assert CC_COMMIT in calls[0][0]
    assert COMPAT_COMMIT in calls[1][0]
    expected='https://raw.githubusercontent.com/'+Runtime.COLORLESS_SAGA_CREATURE_REPO+'/'+Runtime.COLORLESS_SAGA_CREATURE_COMMIT+Runtime.COLORLESS_SAGA_CREATURE_PATH
    assert calls[2][0]==expected
    assert all(kwargs.get('immutable') is True for _,kwargs in calls)
    assert all('cardconjurer.app' not in url for url,_ in calls)
    assert runtime.diagnostic()['files'][Runtime.COLORLESS_SAGA_CREATURE_PATH]['url']==expected

def test_modern_saga_asset_source_is_not_a_global_fallback():
    calls=[]
    class FakeNet:
        def fetch(self,url,**kwargs):
            calls.append(url);raise ValidationError('HTTP 404: missing pinned asset')
    runtime=Runtime(FakeNet())
    with pytest.raises(ValidationError):runtime.fetch('/img/frames/saga/creature/not-a-real-frame.png')
    assert len(calls)==2
    assert Runtime.COLORLESS_SAGA_CREATURE_REPO not in calls[-1]

def test_creator_script_patches_inline_mana_cluster_wrapping():
    source='''function writeText(textObject, targetContext) {
		//Begin looping through words/codes
		innerloop: for (word of splitText) {
			var wordToWrite = word;
					var manaSymbolSpacing = textSize * 0.04 + textManaSpacing;
					var manaSymbolWidth = manaSymbol.width * textSize * 0.78;
					var manaSymbolHeight = manaSymbol.height * textSize * 0.78;
					var manaSymbolX = currentX + canvasMargin + manaSymbolSpacing;
}'''
    class FakeNet:
        def fetch(self,url,**kwargs):
            assert CC_COMMIT in url and kwargs.get('immutable') is True
            return source.encode(),'application/javascript',{}
    runtime=Runtime(FakeNet())
    raw,mime=runtime.fetch('/js/creator-23.js');text=raw.decode()
    assert mime=='application/javascript'
    assert 'proxyFoundryManaClusterWidth' in text
    assert "splitText.splice(proxyFoundryWordIndex, 0, '{lns}')" in text
    assert 'currentX + manaClusterWidth >= textWidth' in text
    assert 'innerloop: for (word of splitText)' not in text
    assert runtime.diagnostic()['files']['/js/creator-23.js']['adapter']=='inline mana cluster wrapping'


@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in pinned CardConjurer dependency inspection')
def test_colorless_saga_creature_gap_asset_exists_at_pinned_commit():
    url='https://raw.githubusercontent.com/'+Runtime.COLORLESS_SAGA_CREATURE_REPO+'/'+Runtime.COLORLESS_SAGA_CREATURE_COMMIT+Runtime.COLORLESS_SAGA_CREATURE_PATH
    request=urllib.request.Request(url,headers={'User-Agent':'Bulk-Proxy-Forge-CI'})
    with urllib.request.urlopen(request,timeout=30) as response:
        assert response.status==200
        assert response.read(8)==b'\x89PNG\r\n\x1a\n'
