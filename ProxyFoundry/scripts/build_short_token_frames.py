"""Assemble the native Short token pack once, excluding its unused image areas."""
import io,sys,urllib.request
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.domain import CC_REPO,CC_COMMIT
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'test-results/short-token-frame-sources'


def load(path):
    target=CACHE/path.lstrip('/')
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(urllib.request.urlopen(f'https://raw.githubusercontent.com/{CC_REPO}/{CC_COMMIT}'+path,timeout=30).read())
    return Image.open(io.BytesIO(target.read_bytes())).convert('RGBA')


def black_border(frame):
    """Keep native black edge pixels, excluding the separate type-bar outlines."""
    red,green,blue,alpha=frame.split()
    black=ImageChops.lighter(ImageChops.lighter(red,green),blue).point(lambda value:255 if value==0 else 0)
    support=ImageChops.multiply(black,alpha)
    exterior=Image.new('L',frame.size)
    draw=ImageDraw.Draw(exterior);width,height=frame.size
    for y in range(height):
        row=support.crop((0,y,width,y+1)).tobytes()
        left=next((x for x,value in enumerate(row) if not value),width)
        right=next((x for x,value in enumerate(reversed(row)) if not value),width)
        if left:draw.line((0,y,left-1,y),fill=255)
        if right:draw.line((width-right,y,width-1,y),fill=255)
    border=Image.new('RGBA',frame.size)
    border.putalpha(ImageChops.multiply(alpha,exterior))
    return border


def build():
    masks=[load(path).getchannel('A') for path in (
        '/img/frames/token/short/m15MaskPinlineSuperShort.png',
        '/img/frames/m15/regular/m15MaskTitle.png',
        '/img/frames/token/short/m15MaskTypeShort.png',
        '/img/frames/token/short/m15MaskRulesShort.png')]
    destination=ROOT/'assets/token-short';destination.mkdir(exist_ok=True)
    #Use the exact rounded black border from the textless token pack for every
    #short-box color. Its contour is independent of the title and rules panels.
    border=black_border(load('/img/frames/token/textless/tokenFrameWTextless.png'))
    border.save(destination/'border.png',optimize=True)
    for code in 'WUBRGMALC':
        name='frameC.png' if code=='C' else f'tokenFrame{code}Short.png'
        frame=load('/img/frames/token/short/'+name)
        coverage=Image.new('L',frame.size)
        for mask in masks:
            coverage=ImageChops.lighter(coverage,mask.resize(frame.size,Image.Resampling.LANCZOS))
        frame.putalpha(ImageChops.multiply(frame.getchannel('A'),coverage))
        frame=Image.alpha_composite(border,frame)
        frame.save(destination/('frame'+code+'.png'),optimize=True)
        print('Built short token '+code,flush=True)


if __name__=='__main__':build()
