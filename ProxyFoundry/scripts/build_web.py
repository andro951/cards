"""Create a static browser distribution. A local server is only useful for tests."""
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
dist.mkdir(exist_ok=True)
(dist / 'site').mkdir(exist_ok=True)
(dist / 'web').mkdir(exist_ok=True)

for path in (root / 'site').iterdir():
    if path.is_file():
        shutil.copy2(path, dist / 'site' / path.name)
for name in ('bootstrap.js', 'engine-worker.js'):
    shutil.copy2(root / 'web' / name, dist / 'web' / name)
shutil.copy2(root / 'web' / 'service-worker.js', dist / 'sw.js')

html = (root / 'site' / 'index.html').read_text(encoding='utf-8')
html = html.replace('<script type="module" src="/site/app.js"></script>',
                    '<script type="module" src="/web/bootstrap.js"></script>')
html = html.replace('BULK PROXY FORGE 1.3 <span>LOCAL</span>',
                    'BULK PROXY FORGE 2.0 <span>WEB</span>')
(dist / 'index.html').write_text(html, encoding='utf-8')

with zipfile.ZipFile(dist / 'web' / 'runtime.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for directory in ('foundry', 'vendor/card_tools', 'assets', 'extension'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py', '.png', '.json', '.js', '.md', '.txt'}:
                archive.write(path, path.relative_to(root))
print(dist)
