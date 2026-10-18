"""Bundle native pinline transparency once, for recolored compact land rims."""
import io,sys
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ROOT=Path(__file__).resolve().parents[1]

def build(fetch,destination):
    raw,_=fetch('/img/frames/m15/boxTopper/short/wl.png')
    source=Image.open(io.BytesIO(raw)).convert('RGBA')
    mask=Image.new('RGBA',source.size)
    mask.putalpha(source.getchannel('A'))
    mask.save(destination/'PinlineFade.png')

if __name__=='__main__':
    from foundry.server import App
    from foundry.storage import Store
    app=App(Store(ROOT/'test-results/land-title-black-workspace'))
    build(app.runtime.fetch,ROOT/'assets/compact-land')
    print('Built native compact pinline fade',flush=True)
