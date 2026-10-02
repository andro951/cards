"""Image validation and opt-in rarity treatment; never generate substitute artwork."""
from __future__ import annotations
import base64,hashlib,io,re,xml.etree.ElementTree as ET
from PIL import Image,ImageOps,UnidentifiedImageError
from .domain import ValidationError,RARITIES
from .timing import timing
MAX_PIXELS=48_000_000
MAX_BYTES=64*1024*1024
TRANSPARENT_EDGE_ALPHA_THRESHOLD=2

def decode_image(raw):
    if not raw or len(raw)>MAX_BYTES: raise ValidationError('Choose an image smaller than 64 MB.')
    try:
        im=Image.open(io.BytesIO(raw))
        if im.width*im.height>MAX_PIXELS:raise ValidationError('Image exceeds the 48 megapixel limit.')
        im.load();return ImageOps.exif_transpose(im).convert('RGBA')
    except (UnidentifiedImageError,OSError,ValueError) as exc:raise ValidationError('Could not decode image. Use PNG, JPEG, WebP or GIF.') from exc

def trim_transparent_edges(im):
    alpha=im.getchannel('A')
    # Alpha 0-2 is visually negligible but can occur as stray anti-aliasing/noise
    # far outside the intended artwork. Ignore it only while finding the outer
    # crop bounds; retained pixels are copied unchanged from the original image.
    visible=alpha.point(lambda value:255 if value>TRANSPARENT_EDGE_ALPHA_THRESHOLD else 0)
    bbox=visible.getbbox()
    if bbox is None or bbox==(0,0,im.width,im.height):return im
    return im.crop(bbox)

def ingest_image(store,raw,*,trim_transparent_padding=False):
    if not raw or len(raw)>MAX_BYTES:raise ValidationError('Choose an image smaller than 64 MB.')
    cache=getattr(store,'_image_ingest_cache',None)
    key=(hashlib.sha256(raw).digest(),bool(trim_transparent_padding)) if cache is not None else None
    if cache is not None:
        with store._image_ingest_lock:
            ident=cache.pop(key,None)
            if ident:cache[key]=ident
        if ident:
            asset=store.asset(ident)
            if asset:return asset
            with store._image_ingest_lock:cache.pop(key,None)
    with timing(store,'image.decode',bytes=len(raw)):im=decode_image(raw)
    if trim_transparent_padding:im=trim_transparent_edges(im)
    out=io.BytesIO()
    with timing(store,'image.encode-png',width=im.width,height=im.height):im.save(out,'PNG')
    asset=store.add_asset(out.getvalue(),'image/png',im.width,im.height)
    if cache is not None:
        with store._image_ingest_lock:
            cache[key]=asset['id']
            while len(cache)>128:cache.popitem(last=False)
    return asset

def ingest_render_png(store,raw,expected_size):
    """Validate native canvas PNGs without recompressing their existing pixels."""
    if not raw or len(raw)>MAX_BYTES:raise ValidationError('Choose an image smaller than 64 MB.')
    with timing(store,'render.validate-png',bytes=len(raw)):
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG':raise ValidationError('The native renderer must return a PNG image.')
                if im.width*im.height>MAX_PIXELS:raise ValidationError('Image exceeds the 48 megapixel limit.')
                if list(im.size)!=list(expected_size):raise ValidationError('Rendered canvas size did not match its template. Nothing was marked ready.')
                im.verify()
            #Verify chunk integrity and decode the pixels before accepting the file.
            with Image.open(io.BytesIO(raw)) as im:im.load()
        except ValidationError:raise
        except (UnidentifiedImageError,OSError,ValueError,SyntaxError) as exc:
            raise ValidationError('The native renderer returned an invalid PNG image.') from exc
    return store.add_asset(raw,'image/png',*expected_size)

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
