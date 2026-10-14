"""Colored reverse-face paint on the native Godzilla title geometry."""
import io
from PIL import Image,ImageDraw

VERSION='godzilla-reverse-title-v3-full-bevel'
PREFIX='/img/frames/proxy-foundry/transform/'


def title_paint_mask(header,limit):
    """Follow the connected translucent interior, bounded by the native outline."""
    region=header.crop((0,0,header.width,limit))
    mask=region.getchannel('A').point(lambda a:255 if 0<a<255 else 0)
    center=(header.width//2,limit//2)
    if region.getpixel(center)!=(0,0,0,128):
        center=next(((x,y) for y in range(limit) for x in range(header.width)
                     if region.getpixel((x,y))==(0,0,0,128)),None)
    if center is None:return Image.new('L',region.size)
    ImageDraw.floodfill(mask,center,128)
    return mask.point(lambda value:255 if value==128 else 0)


def color_title_png(header_raw,back_raw,*,joined_crown=False):
    """Color the complete interior/bevel; retain the border and name strip."""
    with Image.open(io.BytesIO(header_raw)) as header,Image.open(io.BytesIO(back_raw)) as back:
        result=header.convert('RGBA')
        # Sample native back-face material away from its icon and beveled edges.
        material=back.convert('RGBA').crop((250,115,1300,195))
        limit=round(result.height*193/270) if joined_crown else result.height
        material=material.resize((result.width,limit),Image.Resampling.LANCZOS)
        mask=title_paint_mask(result,limit).load()
        pixels=result.load();paint=material.load()
        base=128*(1-128/255)
        for y in range(limit):
            for x in range(result.width):
                r,g,b,a=pixels[x,y]
                if mask[x,y]:
                    pr,pg,pb,_=paint[x,y]
                    # Native bevel shading includes both RGB and opacity. Read
                    # it against neutral gray, relative to the black 50% center.
                    light=(.2126*r+.7152*g+.0722*b)*a/255+128*(1-a/255)
                    if light>=base:
                        mix=(light-base)/(255-base)
                        color=[round(v+(255-v)*mix) for v in (pr,pg,pb)]
                    else:color=[round(v*light/base) for v in (pr,pg,pb)]
                    pixels[x,y]=(*color,255)
        output=io.BytesIO();result.save(output,'PNG');return output.getvalue()
