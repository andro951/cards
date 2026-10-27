"""Extract native black edges once; generation only reads the bundled PNGs."""
import base64,io,sys,urllib.request
from pathlib import Path
from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.domain import CC_REPO,CC_COMMIT
from foundry.pinline_masks import SOURCES
from foundry.planeswalker_frame import pinline_without_loyalty_png
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'test-results/pinline-mask-sources'


def fetch(path):
    target=CACHE/path.lstrip('/')
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(urllib.request.urlopen(f'https://raw.githubusercontent.com/{CC_REPO}/{CC_COMMIT}'+path,timeout=30).read())
    return target.read_bytes()


def build(page):
    destination=ROOT/'assets/frame-masks'
    for name,(mask_path,frame_path) in SOURCES.items():
        raw=fetch(mask_path)
        if name.startswith('walker-'):
            raw=pinline_without_loyalty_png(raw,fetch('/img/frames/planeswalker/maskLoyalty.png'),fetch(mask_path.replace('MaskPinline.png','MaskType.png')))
        if mask_path.endswith('.svg'):
            encoded=base64.b64encode(raw).decode()
            raw=base64.b64decode(page.evaluate("""async encoded => {
                const image=new Image();image.src='data:image/svg+xml;base64,'+encoded;await image.decode();
                const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
                canvas.getContext('2d').drawImage(image,0,0);return canvas.toDataURL('image/png').split(',')[1];
            }""",encoded))
        mask=Image.open(io.BytesIO(raw)).convert('RGBA')
        frame=Image.open(io.BytesIO(fetch(frame_path))).convert('RGBA')
        if frame.size!=mask.size:frame=frame.resize(mask.size,Image.Resampling.LANCZOS)
        #Restore only black/antialiased black where the pinline paints.
        #The gradient and its existing color/geometry stay untouched.
        light=ImageChops.lighter(ImageChops.lighter(frame.getchannel('R'),frame.getchannel('G')),frame.getchannel('B'))
        black=ImageChops.multiply(light.point(lambda value:255-min(255,round(value*255/64))),frame.getchannel('A'))
        alpha=ImageChops.multiply(mask.getchannel('A'),black)
        result=frame.copy();result.putalpha(alpha)
        #Discard invisible RGB to keep the bundled assets small.
        result=Image.alpha_composite(Image.new('RGBA',result.size),result)
        result.save(destination/(name+'-outline.png'),optimize=True)
        print('Built '+name,flush=True)


if __name__=='__main__':
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:build(browser.new_page())
        finally:browser.close()
