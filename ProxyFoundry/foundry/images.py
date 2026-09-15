"""Image validation and opt-in rarity treatment; never generate substitute artwork."""
from __future__ import annotations
import base64,io,re,xml.etree.ElementTree as ET
from PIL import Image,ImageOps,UnidentifiedImageError
from .domain import ValidationError,RARITIES
MAX_PIXELS=48_000_000
MAX_BYTES=64*1024*1024

def decode_image(raw):
    if not raw or len(raw)>MAX_BYTES: raise ValidationError('Choose an image smaller than 64 MB.')
    try:
        im=Image.open(io.BytesIO(raw))
        if im.width*im.height>MAX_PIXELS:raise ValidationError('Image exceeds the 48 megapixel limit.')
        im.load();return ImageOps.exif_transpose(im).convert('RGBA')
    except (UnidentifiedImageError,OSError,ValueError) as exc:raise ValidationError('Could not decode image. Use PNG, JPEG, WebP or GIF.') from exc

def ingest_image(store,raw):
    im=decode_image(raw);out=io.BytesIO();im.save(out,'PNG')
    return store.add_asset(out.getvalue(),'image/png',im.width,im.height)

def data_uri(store,asset_id):
    a=store.asset(asset_id)
    if not a:raise ValidationError('An image is missing from the workspace. Upload it again.')
    return 'data:'+a['mime']+';base64,'+base64.b64encode(store.asset_path(asset_id).read_bytes()).decode()

def sanitize_svg(raw):
    if len(raw)>4*1024*1024:raise ValidationError('SVG is too large.')
    text=raw.decode('utf-8-sig')
    if re.search(r'<!DOCTYPE|<!ENTITY',text,re.I):raise ValidationError('SVG external entities are not supported.')
    try:root=ET.fromstring(text)
    except ET.ParseError as exc:raise ValidationError('Invalid SVG.') from exc
    if root.tag.split('}')[-1]!='svg':raise ValidationError('Not an SVG image.')
    allowed={'svg','g','path','defs','rect','circle','ellipse','line','polyline','polygon','linearGradient','radialGradient','stop','clipPath','mask','filter','feGaussianBlur','feOffset','feColorMatrix','feBlend','feComposite','feMerge','feMergeNode','title','desc','use'}
    for e in root.iter():
        if e.tag.split('}')[-1] not in allowed:raise ValidationError('SVG uses an unsupported active element.')
        for k,v in e.attrib.items():
            k=k.split('}')[-1]
            if k.lower().startswith('on') or k in {'href','src'} and not v.startswith('#'):
                raise ValidationError('SVG external resources and event handlers are not allowed.')
            if re.search(r'(javascript:|@import|https?:|file:|data:)',v,re.I):raise ValidationError('SVG must be self-contained.')
    return text.encode()

def rarity_variants(store,asset_id):
    im=decode_image(store.asset_path(asset_id).read_bytes());im.thumbnail((512,512),Image.Resampling.LANCZOS)
    # Retain transparency and dark linework. The preview makes this opt-in,
    # since one raster cannot reconstruct a hand-designed rarity symbol.
    gray=ImageOps.grayscale(im);alpha=im.getchannel('A');out={}
    palette={'common':('#333333','#ededed'),'uncommon':('#354652','#d8e4ea'),
             'rare':('#654314','#f7d680'),'mythic':('#7e240f','#ffac4c')}
    for rarity,(dark,light) in palette.items():
        colored=ImageOps.colorize(gray,black=dark,white=light).convert('RGBA');colored.putalpha(alpha)
        b=io.BytesIO();colored.save(b,'PNG');out[rarity]=store.add_asset(b.getvalue(),'image/png',*colored.size)['id']
    return out
