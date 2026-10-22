"""Classic colorless token material derived from the pinned white frame."""
from __future__ import annotations

import io
import re

from PIL import Image

from .domain import CC_COMMIT

PREFIX = '/img/frames/proxy-foundry/token-classic/'
VERSION = 'desaturated-white-v1'


def material(path):
    match = re.fullmatch(re.escape(PREFIX) + r'(regular|textless)-c\.png', path)
    if not match:
        return None
    source = f'/img/frames/token/m15/{match[1]}/w.png'
    return source, f'derived:{CC_COMMIT}:classic-token:{VERSION}:{source}'


def desaturate_white_png(raw):
    """Keep native geometry, luminance, and alpha; remove only frame color."""
    with Image.open(io.BytesIO(raw)) as source:
        rgba = source.convert('RGBA')
        gray = rgba.convert('L')
        result = Image.merge('RGBA', (gray, gray, gray, rgba.getchannel('A')))
        output = io.BytesIO()
        result.save(output, 'PNG')
    return output.getvalue()
