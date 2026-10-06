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

@pytest.mark.parametrize('path',[
    '/img/frames/prepare/regular/b.png',
    '/img/frames/prepare/regular/pinline.png',
    '/img/frames/prepare/regular/prepare.png',
    '/img/frames/prepare/regular/preparePinline.png',
    '/img/frames/prepare/regular/rules.png',
    '/img/frames/prepare/regular/frame.png',
])
def test_prepare_frames_fall_back_after_browser_transport_404(path):
    calls=[]
    class FakeNet:
        def fetch(self,url,**kwargs):
            calls.append(url)
            if len(calls)==1:raise RuntimeError('Error: HTTP 404 '+url)
            return b'\x89PNG\r\n\x1a\nfixture','image/png',{'cache':False}
    runtime=Runtime(FakeNet())
    raw,mime=runtime.fetch(path)
    assert raw.startswith(b'\x89PNG\r\n\x1a\n') and mime=='image/png'
    assert len(calls)==2 and CC_COMMIT in calls[0]
    assert calls[1].endswith('/public'+path) and COMPAT_COMMIT in calls[1]
    assert runtime.diagnostic()['files'][path]['url']==calls[1]

def test_browser_transport_non_404_does_not_try_another_frame_source():
    calls=[]
    class FakeNet:
        def fetch(self,url,**kwargs):
            calls.append(url);raise RuntimeError('Error: HTTP 500 '+url)
    with pytest.raises(RuntimeError,match='HTTP 500'):
        Runtime(FakeNet()).fetch('/img/frames/prepare/regular/b.png')
    assert len(calls)==1

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


@pytest.mark.parametrize('kind,height,original',[('Title',.069,.1053)])
def test_godzilla_main_title_is_cropped_from_pinned_asset(kind,height,original):
    import io
    from PIL import Image
    source=Image.new('RGBA',(60,100))
    source.putdata([(x,y,0,255) for y in range(100) for x in range(60)])
    buffer=io.BytesIO();source.save(buffer,'PNG');calls=[]
    class FakeNet:
        def fetch(self,url,**kwargs):
            calls.append(url)
            assert CC_COMMIT in url and kwargs.get('immutable') is True
            assert url.endswith(f'/img/frames/m15/nickname/m15Nickname{kind}B.png')
            return buffer.getvalue(),'image/png',{}
    runtime=Runtime(FakeNet())
    path=f'/img/frames/proxy-foundry/godzilla/{kind}B.png'
    raw,mime=runtime.fetch(path)
    output=Image.open(io.BytesIO(raw))
    assert mime=='image/png' and len(calls)==1
    expected=source.crop((0,0,60,round(100*height/original)))
    assert output.size==expected.size and output.tobytes()==expected.tobytes()
    assert runtime.diagnostic()['files'][path]['source'].endswith(f'm15Nickname{kind}B.png')


def test_godzilla_crown_retains_shoulders_and_removes_subtitle():
    import io
    from PIL import Image
    source=Image.new('RGBA',(1428,270),(200,40,30,255))
    source.putpixel((80,222),(0,0,0,255))
    source.putpixel((1348,222),(0,0,0,255))
    buffer=io.BytesIO();source.save(buffer,'PNG')
    class FakeNet:
        def fetch(self,url,**kwargs):return buffer.getvalue(),'image/png',{}
    raw,_=Runtime(FakeNet()).fetch('/img/frames/proxy-foundry/godzilla/CrownR.png')
    output=Image.open(io.BytesIO(raw))
    assert output.size==source.size
    assert output.getpixel((714,194))==(0,0,0,255)
    for point in [(80,222),(1348,222),(714,100)]:
        assert output.getpixel(point)==source.getpixel(point)
    for point in [(714,200),(714,260),(80,240),(1348,240)]:
        assert output.getpixel(point)[3]==0


@pytest.mark.parametrize('kind',['Crown','Title'])
def test_joined_godzilla_crown_is_the_unchanged_native_asset(kind):
    import io
    from PIL import Image
    buffer=io.BytesIO();Image.new('RGBA',(1428,270),(90,30,20,255)).save(buffer,'PNG')
    class FakeNet:
        def fetch(self,url,**kwargs):
            assert url.endswith('/m15Nickname'+kind+'W.png')
            return buffer.getvalue(),'image/png',{}
    raw,mime=Runtime(FakeNet()).fetch('/img/frames/proxy-foundry/godzilla/'+kind+'JoinedW.png')
    assert raw==buffer.getvalue() and mime=='image/png'
