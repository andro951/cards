"""Benchmark entrypoints must resolve project imports without cwd assistance."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename',[
    'profile_startup.py','profile_image_ingest.py',
    'profile_render_save.py','benchmark_selected_folder.py',
])
def test_benchmark_entrypoint_imports_from_an_unrelated_directory(tmp_path,filename):
    environment=dict(os.environ);environment.pop('PYTHONPATH',None)
    code='import runpy;runpy.run_path('+repr(str(ROOT/'scripts'/filename))+",run_name='entrypoint_import_probe')"
    result=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,env=environment,
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    #Import-only mode deliberately opens no browser or permission picker.