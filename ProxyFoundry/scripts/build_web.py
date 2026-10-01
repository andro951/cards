"""Create a static browser distribution. A local server is only useful for tests."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import zipfile

arguments=argparse.ArgumentParser()
arguments.add_argument('--base-path',default='/')
arguments.add_argument('--output',type=Path)
arguments.add_argument('--github-pages',action='store_true')
options=arguments.parse_args()
base=options.base_path
if options.github_pages:
    repository=os.environ.get('GITHUB_REPOSITORY','andro951/cards').split('/')[-1]
    base='/' if repository.lower().endswith('.github.io') else '/'+repository+'/'
if not re.fullmatch(r'/(?:[-A-Za-z0-9_.]+/)*',base) or any(part in {'.','..'} for part in base.split('/')):
    raise SystemExit('Choose an absolute deployment base path ending in /.')
base=base.rstrip('/')
root=Path(__file__).resolve().parents[1]
version=hashlib.sha256()
for directory in ('foundry','site','web','vendor/card_tools','assets'):
    for path in sorted((root/directory).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            version.update(path.relative_to(root).as_posix().encode());version.update(path.read_bytes())
build_id=version.hexdigest()[:20]
def deployed_source(text):
    text=re.sub(r"(['\"])/(site|web)/",lambda match:match[1]+base+'/'+match[2]+'/',text)
    text=text.replace("const buildId='development';","const buildId='"+build_id+"';")
    text=text.replace("const basePath='';","const basePath='"+base+"';")
    text=text.replace("register('/sw.js',{scope:'/',updateViaCache:'none'}","register('"+base+"/sw.js',{scope:'"+base+"/',updateViaCache:'none'}")
    return text

root = Path(__file__).resolve().parents[1]
dist = options.output or root / 'dist'
dist.mkdir(parents=True,exist_ok=True)
(dist / 'site').mkdir(exist_ok=True)
(dist / 'web').mkdir(exist_ok=True)

for path in (root / 'site').iterdir():
    if path.is_file():
        destination=dist/'site'/path.name
        if path.suffix in {'.js','.mjs','.html','.css'}:destination.write_text(deployed_source(path.read_text(encoding='utf-8')),encoding='utf-8')
        else:shutil.copy2(path,destination)
for name in ('bootstrap.js', 'engine-worker.js', 'storage-choice.js', 'settings-browser.js', 'templates-browser.js', 'review-browser.js', 'workspace-files.js', 'workspace-fs.js'):
    (dist/'web'/name).write_text(deployed_source((root/'web'/name).read_text(encoding='utf-8')),encoding='utf-8')
(dist/'sw.js').write_text(deployed_source((root/'web/service-worker.js').read_text(encoding='utf-8')),encoding='utf-8')

html = (root / 'site' / 'index.html').read_text(encoding='utf-8')
html = html.replace('<body>', '<body hidden>', 1)
html = html.replace('<script type="module" src="/site/app.js"></script>',
                    '<script type="module" src="/web/bootstrap.js"></script>')
html = html.replace('BULK PROXY FORGE 1.3 <span>LOCAL</span>',
                    'BULK PROXY FORGE 2.0 <span>WEB</span>')
(dist / 'index.html').write_text(deployed_source(html), encoding='utf-8')

runtime=dist / 'web' / 'runtime.zip'
pending=dist / 'web' / 'runtime.zip.tmp'
with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    archive.writestr('build.json',json.dumps({'id':build_id}))
    for directory in ('foundry', 'vendor/card_tools', 'assets', 'extension'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py', '.png', '.json', '.js', '.md', '.txt'}:
                archive.write(path, path.relative_to(root))
pending.replace(runtime)
print(dist)
