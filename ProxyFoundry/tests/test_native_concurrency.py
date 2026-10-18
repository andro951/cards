"""Experimental parallel native rendering must preserve every output pixel."""
import json,os,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',reason='Actual pinned native renderer experiment')


def test_one_two_three_native_renderers_preserve_pixels(tmp_path):
    output=tmp_path/'concurrency.json'
    arguments=[os.sys.executable,str(ROOT/'scripts/profile_renderer_concurrency.py'),'--output',str(output)]
    if os.name!='nt':arguments.append('--headless')
    result=subprocess.run(arguments,cwd=ROOT,capture_output=True,text=True,timeout=900)
    assert result.returncode==0,result.stdout[-5000:]+result.stderr[-4000:]
    report=json.loads(output.read_text(encoding='utf-8'))
    assert [row['count'] for row in report['trials']]==[1,2,3,3,2,1]
    assert all(row['faces']==7 and len(row['images'])==7 for row in report['trials'])
    assert all(image['pixelsIdentical'] for row in report['trials'] for image in row['images'])
    #The experiment must still record actual worker compatibility, not infer it
    #from OffscreenCanvas availability alone.
    assert report['workerCompatibility']['loaded'] is False
    assert report['workerCompatibility']['documentAvailable'] is False
    evidence=ROOT/'test-results/renderer-concurrency';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')