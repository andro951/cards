"""Cold/repeated native pixels must match after removing the fixed settling wait."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1' or os.environ.get('PF_LIVE_CC')!='1',reason='Actual pinned native renderer')


def test_native_first_use_and_no_wait_pixels():
    arguments=[os.sys.executable,str(ROOT/'scripts/profile_native_render.py'),'--readiness-only','--broad','--verify']
    if os.name!='nt':arguments.append('--headless')
    result=subprocess.run(arguments,cwd=ROOT,capture_output=True,text=True,timeout=600)
    assert result.returncode==0,result.stdout[-6000:]+result.stderr[-4000:]

