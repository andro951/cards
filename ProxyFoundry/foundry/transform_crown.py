"""Restore native Godzilla crown bevels without changing transform geometry."""
import io
from PIL import Image, ImageChops, ImageDraw

PREFIX = '/img/frames/proxy-foundry/transform/'
BEVEL_VERSION = 'native-crown-bevel-v2-circle-guard'
BACK_VERSION = 'right-arrow-header-v1'


def mirror_header_png(raw):
    """Reflect just a header asset, including its alpha and existing bevels."""
    with Image.open(io.BytesIO(raw)) as source:
        result=source.convert('RGBA').transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        output=io.BytesIO();result.save(output,'PNG');return output.getvalue()


def protect_marker_border(mask, source):
    """Keep the native circle collar; the donor has a rounded bar end here."""
    width,height=source.size
    if height<8:return
    alpha=source.getchannel('A');row=round(height*.46)
    runs=[];start=None;limit=round(width*.15)
    for x in range(limit):
        if alpha.getpixel((x,row))==0:
            if start is None:start=x
        elif start is not None:
            runs.append((start,x));start=None
    if start is not None:runs.append((start,limit))
    if not runs:return
    left,right=max(runs,key=lambda run:run[1]-run[0])
    if right-left<height*.3:return
    center=(left+right-1)//2;top=bottom=row
    while top>0 and alpha.getpixel((center,top-1))==0:top-=1
    while bottom+1<height and alpha.getpixel((center,bottom+1))==0:bottom+=1
    if bottom-top<height*.3:return
    padding=round(height*.045)
    ImageDraw.Draw(mask).ellipse((left-padding,top-padding,right-1+padding,bottom+padding),fill=0)


def restore_crown_bevel(transform_raw, godzilla_raw):
    with Image.open(io.BytesIO(transform_raw)) as source, Image.open(io.BytesIO(godzilla_raw)) as donor:
        source=source.convert('RGBA');donor=donor.convert('RGBA')
        if source.size!=donor.size:raise ValueError('Pinned transform and Godzilla crown dimensions differ.')
        # Both packs share the crown contour and texture coordinates. Restore
        # paint only where both have opaque colored crown material. Keep the
        # transform's circular opening, black outlines and translucent strip.
        mask=ImageChops.multiply(source.getchannel('A').point(lambda a:255 if a==255 else 0),
                                 donor.getchannel('A').point(lambda a:255 if a==255 else 0))
        for image in (source,donor):
            mask=ImageChops.multiply(mask,image.convert('RGB').convert('L').point(lambda v:255 if v>0 else 0))
        protect_marker_border(mask,source)
        result=source.copy();result.paste(donor,(0,0),mask)
        result.putalpha(source.getchannel('A'))
        output=io.BytesIO();result.save(output,'PNG')
        return output.getvalue()
