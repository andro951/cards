"""Prepare original-dual subtitles with the outside black contour removed."""
from pathlib import Path
import io,sys
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def remove_bottom_outer_outline(source):
    image=source.convert('RGBA').copy();pixels=image.load()
    # Walk inward from the bottom silhouette until the colored strip begins.
    # Its inner black line and translucent interior are behind that strip and
    # are never visited. This follows both curved shoulders as well as the base.
    for x in range(image.width):
        started=False
        for y in range(image.height-1,132,-1):
            r,g,b,a=pixels[x,y]
            if not a:
                if started:break
                continue
            started=True
            if max(r,g,b)>16:break
            pixels[x,y]=(r,g,b,0)
    return image

if __name__=='__main__':
    from foundry.server import App
    from foundry.storage import Store
    root=Path(__file__).resolve().parents[1]
    app=App(Store(root/'test-results/name-outline-workspace'))
    destination=root/'assets/land-addons';destination.mkdir(exist_ok=True)
    for code in 'WUBRGMAL':
        raw,_=app.runtime.fetch(f'/img/frames/m15/nickname/addons/m15NicknameTitle{code}.png')
        remove_bottom_outer_outline(Image.open(io.BytesIO(raw))).save(destination/f'TrueNameNoOuter{code}.png')
