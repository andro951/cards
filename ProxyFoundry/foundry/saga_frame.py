"""Reuse native transform header and type materials on the Saga structure."""
import io
from PIL import Image

PREFIX='/img/frames/proxy-foundry/saga/'
VERSION=1


def transform_back_png(saga_raw,back_raw,type_mask_raw):
    def rgba(raw):
        with Image.open(io.BytesIO(raw)) as image:
            if image.size!=(1500,2100):raise ValueError('Unexpected native Saga frame dimensions.')
            return image.convert('RGBA')
    saga=rgba(saga_raw);back=rgba(back_raw);mask=rgba(type_mask_raw).getchannel('A')
    #Both native packs use the same title coordinates. Copy the whole header
    #including its bevel and marker recess, rather than tinting the pale title.
    saga.paste(back.crop((0,60,1500,237)),(0,60))
    #The native type bars have identical geometry, 593 pixels apart. Preserve
    #the Saga's outline and everything in its chapter/art wells.
    material=Image.new('RGBA',saga.size)
    material.paste(back,(0,593))
    saga.paste(material,(0,0),mask)
    out=io.BytesIO();saga.save(out,'PNG');return out.getvalue()
