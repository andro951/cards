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


def build():
    masks=[load(path).getchannel('A') for path in (
        '/img/frames/token/short/m15MaskPinlineSuperShort.png',
        '/img/frames/m15/regular/m15MaskTitle.png',
        '/img/frames/token/short/m15MaskTypeShort.png',
        '/img/frames/token/short/m15MaskRulesShort.png')]
    destination=ROOT/'assets/token-short';destination.mkdir(exist_ok=True)
    for code in 'WUBRGMALC':
        name='frameC.png' if code=='C' else f'tokenFrame{code}Short.png'
        frame=load('/img/frames/token/short/'+name)
        #The token pack's black outer border is outside its art window.
        #Keep it even when artwork is fitted across the full canvas beneath it.
        width,height=frame.size
        coverage=Image.new('L',frame.size,255)
        ImageDraw.Draw(coverage).rectangle((round(.04*width),round(.0286*height),
            round(.96*width)-1,round(.9239*height)-1),fill=0)
        for mask in masks:
            coverage=ImageChops.lighter(coverage,mask.resize(frame.size,Image.Resampling.LANCZOS))
        frame.putalpha(ImageChops.multiply(frame.getchannel('A'),coverage))
        frame=Image.alpha_composite(Image.new('RGBA',frame.size),frame)
        frame.save(destination/('frame'+code+'.png'),optimize=True)
        print('Built short token '+code,flush=True)


if __name__=='__main__':build()
