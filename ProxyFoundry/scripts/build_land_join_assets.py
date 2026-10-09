"""Rebuild the approved compact-land join from the pinned native frame parts.

The title stays intact. Only the subtitle is cropped and moved upward,
with native shading/alpha preserved and no horizontal blending.
These small bundled assets avoid image processing during card generation.
"""
from pathlib import Path
import io,json,sys
from PIL import Image,ImageChops,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.server import App
from foundry.storage import Store

ROOT=Path(__file__).resolve().parents[1]
W,H=2010,2814
BAR_SCALE=.1053/221
BAR_Y=219.5/2100-1.5*BAR_SCALE

def joined_parts(source,native_mask,addon):
    """Keep the title intact; trim and translate only the true-name addon."""
    rim=source.getpixel((source.width//2,90))[:3]
    source=source.copy()
    mask=native_mask.resize(source.size,Image.Resampling.LANCZOS)
    source.putalpha(ImageChops.multiply(source.getchannel('A'),mask).point(lambda a:round(a*.68)))
    title=source.resize((W,H),Image.Resampling.LANCZOS)
    cropped=addon.crop((0,148,1352,221))
    base=cropped.getpixel((676,59))[:3]
    pixels=cropped.load()
    for y in range(cropped.height):
        for x in range(cropped.width):
            r,g,b,a=pixels[x,y]
            if not a or max(r,g,b)<=16:continue
            # Match only the colored rim, preserving native shading and alpha.
            rgb=tuple(min(255,round(channel*target/channel_base) if channel_base else channel)
                      for channel,target,channel_base in zip((r,g,b),rim,base))
            pixels[x,y]=(*rgb,a)
    sx=.9014*W/1352;sy=BAR_SCALE*H
    transform=(1/sx,0,-.0494*W/sx,0,1/sy,-BAR_Y*H/sy)
    bar=cropped.transform((W,H),Image.Transform.AFFINE,transform,Image.Resampling.BICUBIC)
    # Ignore faint resampling halos so they cannot punch holes in the seam.
    silhouette=title.getchannel('A').point(lambda a:255 if a>=16 else 0)
    footprint=Image.new('L',(W,H))
    footprint.paste(silhouette.crop((0,1,W,H)),(0,0))
    bar.putalpha(ImageChops.multiply(bar.getchannel('A'),ImageChops.invert(footprint)))
    left,top,right,bottom=bar.getchannel('A').getbbox()
    shifted=Image.new('RGBA',(W,H))
    # Exact output pixels: crop one occupied row, then move up two. Do not
    # retrim after moving; the small native seam overlap is intentional.
    shifted.paste(bar.crop((left,top+1,right,bottom)),(left,top-1))
    return title,shifted


def build(fetch,destination):
    destination.mkdir(parents=True,exist_ok=True)
    manifest={'canvas':[W,H],'barY':BAR_Y,'topCropPixels':1,'raisePixels':2,
              'textShift':.0405+148*BAR_SCALE-BAR_Y+2/H,'parts':{}}
    def load(path):return Image.open(io.BytesIO(fetch(path)[0])).convert('RGBA')
    def save(name,image):
        box=image.getchannel('A').getbbox()
        image.crop(box).save(destination/(name+'.png'))
        manifest['parts'][name]={'x':box[0]/W,'y':box[1]/H,'width':(box[2]-box[0])/W,'height':(box[3]-box[1])/H}
    native_mask=load('/img/frames/m15/regular/m15MaskTitle.png').getchannel('A')
    for code in 'WUBRGMAL':
        source=load(f'/img/frames/m15/genericShowcase/m15GenericShowcaseFrame{code}.png')
        addon=load(f'/img/frames/m15/nickname/addons/m15NicknameTitle{code}.png')
        title,bar=joined_parts(source,native_mask,addon)
        save('Title'+code,title)
        save('TrueName'+code,bar)
    crown=load('/img/frames/m15/crowns/m15CrownBFloating.png')
    silhouette=crown.getchannel('A').point(lambda a:255 if a>=128 else 0)
    padded=Image.new('L',(crown.width+4,crown.height+4));padded.paste(silhouette,(2,2))
    ring=ImageChops.subtract(padded.filter(ImageFilter.MaxFilter(5)),padded.filter(ImageFilter.MinFilter(5)))
    outline=Image.new('RGBA',padded.size);outline.putalpha(ring);outline.save(destination/'CrownOutline.png')
    sx=.9387/crown.width;sy=.1024/crown.height
    manifest['parts']['CrownOutline']={'x':.0307-2*sx,'y':.0191-2*sy,'width':padded.width*sx,'height':padded.height*sy}
    (destination/'geometry.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return manifest

if __name__=='__main__':
    app=App(Store(ROOT/'test-results/name-outline-workspace'))
    build(app.runtime.fetch,ROOT/'assets/compact-land')
