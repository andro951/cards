"""Restore transparent gaps in the native Devoid header's black matte."""
import io
from PIL import Image,ImageChops

PREFIX='/img/frames/proxy-foundry/devoid/'
VERSION=2


def transparent_header_png(raw,white_raw,frame_mask_raw):
    source=Image.open(io.BytesIO(raw)).convert('RGBA')
    white=Image.open(io.BytesIO(white_raw)).convert('RGBA')
    mask=Image.open(io.BytesIO(frame_mask_raw)).convert('RGBA')
    if source.size!=white.size or source.size!=mask.size:
        raise ValueError('Devoid header sources have different dimensions.')
    #Use the light frame as the shared silhouette, so genuinely dark material
    #on black Devoid frames stays opaque. Restrict changes to the upper Frame
    #component; the outer border, title bevel, pinline and lower panels survive.
    box=(0,round(source.height*80/2814),source.width,round(source.height*300/2814))
    channels=white.crop(box).split()
    light=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    opacity=light.point([round(max(0,min(1,(value-8)/40))*255) for value in range(256)])
    holes=ImageChops.multiply(ImageChops.invert(opacity),mask.crop(box).getchannel('A'))
    alpha=source.getchannel('A')
    alpha.paste(ImageChops.multiply(alpha.crop(box),ImageChops.invert(holes)),box)
    source.putalpha(alpha)
    output=io.BytesIO();source.save(output,'PNG')
    return output.getvalue()
