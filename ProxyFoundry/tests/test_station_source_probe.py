"""Temporary read-only upstream dependency probe; not a replacement renderer."""
import hashlib,json,os,re,urllib.request
from pathlib import Path
import pytest
@pytest.mark.skipif(os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in native dependency inspection')
def test_station_source_probe():
    root=Path(__file__).resolve().parents[1]/'test-results'/'station-source'
    root.mkdir(parents=True,exist_ok=True)
    report={}
    for path in ['/js/frames/versionStation.js','/creator/index.html','/js/creator-23.js']:
        url='https://cardconjurer.app'+path
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'ProxyFoundry/1.2 native Station integration test'})
            with urllib.request.urlopen(request,timeout=25) as response:
                raw=response.read(2*1024*1024)
                report[path]={'status':response.status,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'finalUrl':response.url}
                if path.endswith('.js'):
                    (root/path.rsplit('/',1)[-1]).write_bytes(raw)
                else:
                    text=raw.decode('utf-8',errors='replace')
                    report[path]['githubUrls']=re.findall(r'https://github.com/[^\s"<>]+',text)
                    report[path]['scripts']=re.findall(r'<script[^>]+src=["\']([^"\']+)',text)
        except Exception as exc:report[path]={'error':str(exc)}
    (root/'sources.json').write_text(json.dumps(report,indent=2))
    assert report['/js/frames/versionStation.js'].get('status')==200,report
