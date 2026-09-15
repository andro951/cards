"""Built-in and icon backs: deterministic alpha composition, not image generation.

Only the two approved full-card backgrounds are application assets. User icons
live in the local content-addressed workspace, never in the application package.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
from PIL import Image

from .domain import ValidationError, stable_hash
from .images import decode_image

ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'backs'
COMPOSITION_VERSION = 'forge-icon-v1'
# Pixel coordinates in the unmodified 1055 × 1491 blank supplied by the user.
ICON_BOUNDS = {'x': 207, 'y': 450, 'size': 640}
BLANK_SIZE = (1055, 1491)
BUILTINS = {
    'default': {'file': 'forge_default.png', 'name': 'Bulk Proxy Forge · default',
                'size': (1061, 1482)},
    'blank': {'file': 'forge_blank.png', 'name': 'Bulk Proxy Forge · icon background',
              'size': BLANK_SIZE},
}


def compose_icon(blank: Image.Image, icon: Image.Image) -> tuple[Image.Image, dict]:
    """Contain all nontransparent pixels in the safe square. Never crop artwork.

    Transparent-only padding is removed before fitting. We do not remove opaque
    backgrounds, recolor, stretch, rotate, or place any pixel outside the square.
    """
    if blank.size != BLANK_SIZE:
        raise ValidationError('The icon background does not match the approved 1055 × 1491 template.')
    icon = icon.convert('RGBA')
    bbox = icon.getchannel('A').getbbox()
    if bbox is None:
        raise ValidationError('This icon is fully transparent. Choose an image with visible pixels.')
    alpha_min = icon.getchannel('A').getextrema()[0]
    cropped = icon.crop(bbox)
    side = ICON_BOUNDS['size']
    scale = min(side / cropped.width, side / cropped.height)
    width, height = [max(1, min(side, round(n * scale))) for n in cropped.size]
    fitted = cropped.resize((width, height), Image.Resampling.LANCZOS)
    left = ICON_BOUNDS['x'] + (side - width) // 2
    top = ICON_BOUNDS['y'] + (side - height) // 2
    output = blank.convert('RGBA').copy()
    output.alpha_composite(fitted, (left, top))
    warnings = []
    if alpha_min == 255:
        warnings.append('This icon has no transparency. Its rectangular background is kept; use a transparent PNG for a floating logo.')
    if scale > 1:
        warnings.append('This icon is smaller than the print area and has been enlarged. A higher-resolution icon may print more sharply.')
    return output, {'bounds': dict(ICON_BOUNDS), 'sourceSize': list(icon.size),
                    'sourceVisibleBounds': list(bbox), 'placedBounds': [left, top, width, height],
                    'trimTransparentPadding': True, 'fit': 'contain', 'warnings': warnings}


class Backs:
    def __init__(self, store, asset_root: Path | None = None):
        self.store = store
        self.root = Path(asset_root or ASSET_ROOT)
        self._assets = {}

    def builtin(self, kind: str) -> dict:
        if kind not in BUILTINS:
            raise ValidationError('Unknown built-in card back.')
        if kind in self._assets:
            return dict(self._assets[kind])
        spec = BUILTINS[kind]
        path = self.root / spec['file']
        if not path.is_file():
            raise ValidationError('The bundled card-back assets are missing. Extract the complete application ZIP, including assets/backs.')
        raw = path.read_bytes()
        manifest = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        if hashlib.sha256(raw).hexdigest() != manifest['files'][spec['file']]['sha256']:
            raise ValidationError('A bundled card back failed its integrity check. Use the unmodified assets from the full application ZIP.')
        image = decode_image(raw)
        if image.size != spec['size']:
            raise ValidationError('A bundled card back has incorrect dimensions.')
        # Keep the original uploaded bytes for the default/backdrop, not a re-encode.
        asset = self.store.add_asset(raw, 'image/png', *image.size)
        self._assets[kind] = {**asset, 'name': spec['name']}
        return dict(self._assets[kind])

    def catalog(self) -> dict:
        return {'default': self.builtin('default'), 'blank': self.builtin('blank'),
                'iconBounds': dict(ICON_BOUNDS), 'blankSize': list(BLANK_SIZE),
                'compositionVersion': COMPOSITION_VERSION}

    def icon(self, ident: str) -> dict:
        source = self.store.asset(ident)
        if not source or not source['mime'].startswith('image/'):
            raise ValidationError('The selected back icon is missing. Upload it again.')
        blank = self.builtin('blank')
        key = stable_hash({'version': COMPOSITION_VERSION, 'blank': blank['id'],
                           'icon': ident, 'bounds': ICON_BOUNDS})
        old = self.store.get('backComposites', key)
        if old and (asset := self.store.asset(old['assetId'])):
            return {**asset, 'design': old['design'], 'placement': old['placement'], 'cached': True}
        output, placement = compose_icon(decode_image(self.store.asset_path(blank['id']).read_bytes()),
                                          decode_image(self.store.asset_path(ident).read_bytes()))
        out = io.BytesIO()
        output.save(out, 'PNG')
        asset = self.store.add_asset(out.getvalue(), 'image/png', *output.size)
        design = {'mode': 'icon', 'iconAsset': ident, 'template': 'forge-blank-v1',
                  'compositionVersion': COMPOSITION_VERSION}
        self.store.put('backComposites', {'id': key, 'assetId': asset['id'],
                                         'design': design, 'placement': placement})
        return {**asset, 'design': design, 'placement': placement, 'cached': False}

    def settings(self, values: dict) -> dict:
        """Resolve a requested design to the compatible backAsset consumed by orders.

        A new deck inherits the built-in default. Older backAsset-only settings
        keep their exact custom image (or explicitly empty selection). Existing
        order snapshots and front render keys are never rewritten.
        """
        design = values.get('backDesign')
        if design is None:
            if values.get('backAsset'):
                design = {'mode': 'custom'}
            elif 'backAsset' in values:
                design = {'mode': 'none'}
            else:
                design = {'mode': 'default'}
        if not isinstance(design, dict):
            raise ValidationError('Invalid card-back selection.')
        mode = design.get('mode')
        if mode == 'default':
            return {'backAsset': self.builtin('default')['id'],
                    'backDesign': {'mode': 'default', 'template': 'forge-default-v1'}}
        if mode == 'icon':
            result = self.icon(design.get('iconAsset', ''))
            return {'backAsset': result['id'], 'backDesign': copy.deepcopy(result['design'])}
        if mode == 'custom':
            ident = values.get('backAsset')
            if not ident or not (asset := self.store.asset(ident)) or not asset['mime'].startswith('image/'):
                raise ValidationError('Upload a complete back image before saving.')
            return {'backAsset': ident, 'backDesign': {'mode': 'custom'}}
        if mode == 'none':
            return {'backAsset': None, 'backDesign': {'mode': 'none'}}
        raise ValidationError('Choose the default back, upload an icon, or upload a complete back.')
