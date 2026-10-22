"""Stronger classic land rules colors, derived once from native textures."""
from __future__ import annotations

import io
import re

from PIL import Image

from .domain import CC_COMMIT

VERSION = 'colored-texture-v2'
PREFIX = f'/img/frames/proxy-foundry/land-rules/{VERSION}/'
# Light enough for black rules text, including the darkest native texture areas.
TINTS = {'W': (255, 235, 178), 'U': (166, 210, 249), 'B': (205, 183, 214),
         'R': (249, 167, 131), 'G': (173, 211, 145)}


def material(path):
    match = re.fullmatch(re.escape(PREFIX) + r'm15Frame([WUBRG])\.png', path)
    if not match:
        return None
    code = match[1]
    source = f'/img/frames/m15/regular/m15Frame{code}.png'
    return source, f'derived:{CC_COMMIT}:dual-land-rules:{VERSION}:{code}', code


def colored_rules_png(raw, code):
    """Tint every light texture pixel while retaining shading and exact alpha."""
    with Image.open(io.BytesIO(raw)) as source:
        rgba = source.convert('RGBA')
        gray = rgba.convert('L')
        channels = [gray.point([(value * tint + 127) // 255 for value in range(256)]) for tint in TINTS[code]]
        result = Image.merge('RGBA', (*channels, rgba.getchannel('A')))
        output = io.BytesIO()
        result.save(output, 'PNG')
    return output.getvalue()
