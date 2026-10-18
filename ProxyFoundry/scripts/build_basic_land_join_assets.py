"""Bake the basic-land cropped subtitle trimmed against the intact native title at native resolution."""
from pathlib import Path
import io,json,sys
from PIL import Image,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

W,H=2010,2814
BAR_X=.12733333333333333
BAR_WIDTH=.7687174129353235
BAR_HEIGHT=.1053
# Move two reference pixels upward from the previous +3 position.
BAR_Y=.8481-.0117+1/2100
CROP=148
SEAM_OVERLAP=1

def match_addon_alpha(addon,title):
    """Match the native title's rim and translucent fill independently."""
    rim=title.getpixel((W//2,2557))[3]/255
    fill=title.getpixel((W//2,2450))[3]/127
    result=addon.copy()
    result.putalpha(addon.getchannel('A').point(
        lambda a:round(a*(fill if 127<=a<=129 else rim))))
    return result

def join(source,masks,addon):
    """Trim addon overlap while preserving every native title pixel."""
    title=Image.new('RGBA',source.size)
    for mask,opacity in reversed(masks):
        layer=source.copy()
        layer.putalpha(ImageChops.multiply(source.getchannel('A'),mask).point(lambda a:round(a*opacity)))
        title=Image.alpha_composite(title,layer)
    sx=BAR_WIDTH*W/addon.width;sy=BAR_HEIGHT*H/addon.height
    top=BAR_Y*H+CROP*sy
    transform=(1/sx,0,-BAR_X*W/sx,0,1/sy,-top/sy)
    cropped=match_addon_alpha(addon,title).crop((0,CROP,addon.width,addon.height))
    bar=cropped.transform((W,H),Image.Transform.AFFINE,transform,Image.Resampling.BICUBIC)
    # Leave one rendered row under the title's low-alpha bottom edge.
    # All other overlap is removed from the addon; never change the title.
    # The native opaque footer remains behind the addon, not part of the join.
    footprint=title.getchannel('A').point(lambda a:255 if a else 0)
    footprint.paste(0,(0,2562,W,H))
    trim=Image.new('L',(W,H))
    trim.paste(footprint.crop((0,SEAM_OVERLAP,W,H)),(0,0))
    footprint=trim
    bar.putalpha(ImageChops.multiply(bar.getchannel('A'),ImageChops.invert(footprint)))
    return title,bar,footprint

def build(fetch,destination):
    destination.mkdir(parents=True,exist_ok=True)
    def load(path):return Image.open(io.BytesIO(fetch(path)[0])).convert('RGBA')
    masks=[(load('/img/frames/textless/eoe/masks/'+name+'.png').getchannel('A'),opacity)
           for name,opacity in [('maskNoBorder',.5),('maskPinlines',.6),('maskBorder',1)]]
    for code in 'WUBRG':
        source=load('/img/frames/textless/eoe/'+code.lower()+'.png')
        addon=load('/img/frames/m15/nickname/addons/m15NicknameTitle'+code+'.png')
        _,bar,_=join(source,masks,addon)
        bar.save(destination/('BasicTrueName'+code+'.png'))
    (destination/'basic-join.json').write_text(json.dumps({'canvas':[W,H],'crop':CROP,'referenceOffset':1,'barY':BAR_Y,'seamOverlap':SEAM_OVERLAP,'alpha':'native title rim and fill'},indent=2)+'\n')

if __name__=='__main__':
    from foundry.server import App
    from foundry.storage import Store
    root=Path(__file__).resolve().parents[1]
    app=App(Store(root/'test-results/name-outline-workspace'))
    build(app.runtime.fetch,root/'assets/land-addons')
