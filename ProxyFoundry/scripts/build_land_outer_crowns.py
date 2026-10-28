"""Bundle the approved floating land crown with only its inner stroke removed."""
import io,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

ROOT=Path(__file__).resolve().parents[1]


def remove_inner_stroke(image):
    image=image.convert('RGBA');alpha=image.getchannel('A')
    light=ImageChops.lighter(ImageChops.lighter(image.getchannel('R'),image.getchannel('G')),image.getchannel('B'))
    support=ImageChops.multiply(light.point(lambda value:255 if value<32 else 0),alpha.point(lambda value:255 if value else 0))
    x=image.width//2
    seed=next((x,y) for y in range(image.height//2,-1,-1) if support.getpixel((x,y))==255)
    ImageDraw.floodfill(support,seed,128)
    removed=support.point(lambda value:255 if value==128 else 0)
    #Remove the antialiased fringe of this same stroke, retaining the outer edge.
    fringe=ImageChops.multiply(removed.filter(ImageFilter.MaxFilter(3)),light.point(lambda value:255 if value<100 else 0))
    image.putalpha(ImageChops.multiply(alpha,ImageChops.invert(fringe)))
    return image


def build(fetch,destination):
    for code in 'WUBRGMALC':
        raw,_=fetch(f'/img/frames/m15/crowns/m15Crown{code}Floating.png')
        remove_inner_stroke(Image.open(io.BytesIO(raw))).save(destination/('CrownFloatingOuter'+code+'.png'))
    remove_inner_stroke(Image.open(destination/'CrownOutline.png')).save(destination/'CrownOuterOutline.png')


if __name__=='__main__':
    from foundry.server import App
    from foundry.storage import Store
    app=App(Store(ROOT/'test-results/legendary-land-negative-title-mask/preview-workspace'))
    try:build(app.runtime.fetch,ROOT/'assets/compact-land')
    finally:app.close()
