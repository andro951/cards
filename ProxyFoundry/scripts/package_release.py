"""Build a source release without secrets, font files, runtime caches or test workspaces."""
from pathlib import Path
import hashlib
import json
import zipfile
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','__pycache__','.pytest_cache','workspace','_work','.cache','node_modules','checkpoints','test-results'}
EXTENSIONS={'.py','.js','.html','.css','.md','.txt','.json','.ini','.bat','.svg'}

BACK_FILES={'assets/backs/forge_default.png','assets/backs/forge_blank.png'}
SYMBOL_FILES={f'assets/symbols/{rarity}.png' for rarity in ('common','uncommon','rare','mythic')}
BUNDLED_IMAGE_FILES=BACK_FILES|SYMBOL_FILES

def build(destination):
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(part in EXCLUDED for part in p.relative_to(ROOT).parts):continue
        if p.suffix.lower() not in EXTENSIONS and p.name!='.gitignore' and p.relative_to(ROOT).as_posix() not in BUNDLED_IMAGE_FILES:continue
        if p.name=='RELEASE_MANIFEST.json':continue
        files.append(p)
    assert any(p.name=='START_PROXY_FOUNDRY.bat' for p in files)
    assert BUNDLED_IMAGE_FILES <= {p.relative_to(ROOT).as_posix() for p in files}, 'Release is missing bundled image assets'
    back_manifest=json.loads((ROOT/'assets/backs/manifest.json').read_text())
    for name in BACK_FILES:
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==back_manifest['files'][Path(name).name]['sha256']
    assert all(p.suffix.lower() not in {'.ttf','.otf','.woff','.woff2','.pem','.crx'} for p in files)
    manifest={'application':'Bulk Proxy Forge','version':'1.3.0','files':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,Path('BulkProxyForge')/p.relative_to(ROOT))
        z.writestr('BulkProxyForge/RELEASE_MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(destination) as z:assert z.testzip() is None
    return manifest
if __name__=='__main__':
    import sys
    destination=Path(sys.argv[1] if len(sys.argv)>1 else ROOT.parent/'BulkProxyForge_1_3.zip')
    m=build(destination);print(f'{destination}: {len(m["files"])} files; {destination.stat().st_size:,} bytes')
