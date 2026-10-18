"""Actual static browser native-worker pixels across structural layouts."""
import os
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',reason='Opt-in native browser worker proof')

def test_static_native_worker_layouts_match_serial_reference():
    result=subprocess.run([os.sys.executable,str(ROOT/'scripts/profile_native_workers.py')],cwd=ROOT,capture_output=True,text=True,timeout=360)
    assert result.returncode==0,result.stdout+result.stderr
