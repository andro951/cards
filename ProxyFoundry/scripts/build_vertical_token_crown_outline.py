"""Outline the floating crown after the vertical token header crops it."""
import io,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw,ImageFilter

ROOT=Path(__file__).resolve().parents[1]


def header_outline(raw):
    with Image.open(io.BytesIO(raw)) as source:
        alpha=source.convert('RGBA').getchannel('A').point(lambda a:255 if a>=128 else 0)
    # Match the 2010 x 2814 header clip and the native floating crown bounds.
    bottom=round((round(.1124*2814)/2814-.0191)/.1024*alpha.height)
    alpha.paste(0,(0,bottom,alpha.width,alpha.height))
    padded=Image.new('L',(alpha.width+4,alpha.height+4));padded.paste(alpha,(2,2))
    # Fill the enclosed title opening before finding the outside contour.
    # This leaves the title's own outline alone and closes the cropped bottom.
    ImageDraw.floodfill(padded,(0,0),128)
    solid=padded.point(lambda value:0 if value==128 else 255)
    ring=ImageChops.subtract(solid.filter(ImageFilter.MaxFilter(5)),solid.filter(ImageFilter.MinFilter(5)))
    outline=Image.new('RGBA',ring.size);outline.putalpha(ring)
    return outline


if __name__=='__main__':
    sys.path.insert(0,str(ROOT))
    from foundry.server import App
    from foundry.storage import Store
    app=App(Store(ROOT/'test-results/vertical-token-crown-assets'))
    try:
        raw,_=app.runtime.fetch('/img/frames/m15/crowns/m15CrownLFloating.png')
        header_outline(raw).save(ROOT/'assets/compact-land/CrownHeaderOutline.png')
    finally:app.close()
