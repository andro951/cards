"""Optional code-only CI asset fixture. Never used by the application launcher.

Release ZIPs contain the exact approved backgrounds. A code-only repository
checkout can run API/browser regressions with PF_TEST_BACK_ASSETS=1, using
synthetic backgrounds in a temporary folder. Release-image integrity and real
supplied-icon proofs are checked separately against the complete release.
"""
import hashlib,json,os
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def code_only_back_fixture(tmp_path,monkeypatch):
    if os.environ.get('PF_TEST_BACK_ASSETS')!='1' and not (os.environ.get('CI')=='true' and not (Path(__file__).resolve().parents[1]/'assets/backs/forge_default.png').is_file()):return
    from PIL import Image,ImageDraw
    from foundry import backs
    directory=tmp_path/'synthetic_backs';directory.mkdir()
    manifest={'format':'synthetic-test-fixture','version':1,'files':{}}
    for key,spec in backs.BUILTINS.items():
        im=Image.new('RGBA',spec['size'],(90,50,25,255));draw=ImageDraw.Draw(im)
        draw.rectangle((20,20,spec['size'][0]-21,spec['size'][1]-21),outline='orange',width=4)
        if key=='default':draw.rectangle((350,600,700,950),fill='orange')
        path=directory/spec['file'];im.save(path)
        manifest['files'][spec['file']]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':list(spec['size'])}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(backs,'ASSET_ROOT',directory)
