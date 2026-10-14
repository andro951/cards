"""Tint native compact title artwork toward charcoal, preserving its shading."""
import io,json,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageOps,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

ROOT=Path(__file__).resolve().parents[1]
TYPE_OPACITY=.72
TITLE_SHADE=.30

def black_title(source,mask,type_source):
    """Tint native shading; adjust interior alpha independently of the rim."""
    source=source.convert('RGBA')
    shade=ImageOps.grayscale(source).point(lambda value:round(value*TITLE_SHADE))
    image=Image.merge('RGBA',(shade,shade,shade,source.getchannel('A')))
    mask=mask.resize(image.size,Image.Resampling.LANCZOS)
    alpha=ImageChops.multiply(source.getchannel('A'),mask)
    # Keep the native outline and bevel opaque. Feather only the transition
    # into the center, following the actual rounded title silhouette.
    inset=round(12*source.width/1500)
    interior=alpha.point(lambda value:255 if value>=16 else 0)
    interior=interior.filter(ImageFilter.MinFilter(inset*2+1))
    interior=interior.filter(ImageFilter.GaussianBlur(source.width/1500))
    material_alpha=Image.new('L',source.size)
    center_alpha=source.getpixel((source.width//2,round(150*source.height/2100)))[3]
    for y in range(source.height):
        native_y=y*2100/source.height
        sample_y=round(1286+min(1,max(0,(native_y-112)/96))*100)
        value=round(type_source.getpixel((type_source.width//2,sample_y))[3]*TYPE_OPACITY)
        material_alpha.paste(min(255,round(value*255/max(1,center_alpha))),(0,y,source.width,y+1))
    center=ImageChops.multiply(alpha,material_alpha)
    image.putalpha(Image.composite(center,alpha,interior))
    return image.resize((2010,2814),Image.Resampling.LANCZOS)

def black_crown(source,type_source):
    """Keep the joined crown/rim/subtitle; replace the main title fill only."""
    image=source.convert('RGBA').copy();pixels=image.load()
    fill=pixels[714,130]
    assert fill[:3]==(0,0,0) and 0<fill[3]<255
    for y in range(64,190):
        sample_y=round(1286+(min(185,max(72,y))-72)*100/113)
        material=type_source.getpixel((750,sample_y))
        for x in range(50,1378):
            if pixels[x,y]==fill:
                pixels[x,y]=(*material[:3],round(material[3]*TYPE_OPACITY))
    return image

def build(fetch,destination):
    def load(path):return Image.open(io.BytesIO(fetch(path)[0])).convert('RGBA')
    material=load('/img/frames/m15/boxTopper/short/l.png')
    geometry=json.loads((destination/'geometry.json').read_text(encoding='utf-8'))
    mask=load('/img/frames/m15/regular/m15MaskTitle.png').getchannel('A')
    for code in 'WUBRGMAL':
        title=black_title(load('/img/frames/m15/genericShowcase/m15GenericShowcaseFrame'+code+'.png'),mask,material)
        box=title.getchannel('A').getbbox()
        name='TitleBlack'+code
        title.crop(box).save(destination/(name+'.png'))
        geometry['parts'][name]={'x':box[0]/2010,'y':box[1]/2814,
                               'width':(box[2]-box[0])/2010,'height':(box[3]-box[1])/2814}
        if code=='L': # Compatibility for already compiled references.
            title.crop(box).save(destination/'TitleBlack.png')
            geometry['parts']['TitleBlack']=geometry['parts'][name].copy()
    for code in 'WUBRGMAL':
        black_crown(load('/img/frames/m15/nickname/m15NicknameCrown'+code+'.png'),material).save(destination/('CrownJoinedBlack'+code+'.png'))
    (destination/'geometry.json').write_text(json.dumps(geometry,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    from foundry.server import App
    from foundry.storage import Store
    app=App(Store(ROOT/'test-results/land-title-black-workspace'))
    build(app.runtime.fetch,ROOT/'assets/compact-land')
    print('Built compact-land black title assets')
