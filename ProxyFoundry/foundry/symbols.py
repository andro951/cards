"""Bundled default rarity symbols with explicit per-rarity overrides."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from .domain import RARITIES, ValidationError
from .images import decode_image

ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'symbols'
SYMBOL_SET_VERSION = 'forge-symbols-v1'
BUILTINS = {
    'common': {'file': 'common.webp', 'size': (92, 128), 'sha256': 'cbefdf19c2171c3fbb2be0d43841bc01037f2ed09e3aa0ab8844c9d7b72dfe62'},
    'uncommon': {'file': 'uncommon.webp', 'size': (92, 128), 'sha256': 'de83b76135252d79dc9d4f5d546fb942ef81e3b392fd3128c613df4572a107bf'},
    'rare': {'file': 'rare.webp', 'size': (93, 128), 'sha256': 'fdaf47c959e9d194428d500d7fc1c735c77b78c814a52d802704c74be39a7dc3'},
    'mythic': {'file': 'mythic.webp', 'size': (93, 128), 'sha256': '047593e99666abdc659ae4ed0f6219fb183f0de4bbb1745661ed1380b9355b81'},
}


class Symbols:
    """Resolve the four bundled defaults, then apply only explicit overrides."""

    def __init__(self, store, asset_root: Path | None = None):
        self.store = store
        self.root = Path(asset_root or ASSET_ROOT)
        self._assets = {}

    def builtin(self, rarity: str) -> dict:
        if rarity not in BUILTINS:
            raise ValidationError('Unknown rarity symbol.')
        cached = self._assets.get(rarity)
        if cached and self.store.asset(cached['id']):
            return dict(cached)
        spec = BUILTINS[rarity]
        path = self.root / spec['file']
        if not path.is_file():
            raise ValidationError('The bundled set-symbol assets are missing. Extract the complete application ZIP, including assets/symbols.')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec['sha256']:
            raise ValidationError('A bundled set symbol failed its integrity check. Use the unmodified assets from the full application ZIP.')
        image = decode_image(raw)
        if image.size != spec['size']:
            raise ValidationError('A bundled set symbol has incorrect dimensions.')
        out = io.BytesIO()
        image.save(out, 'PNG', compress_level=9)
        asset = self.store.add_asset(out.getvalue(), 'image/png', *image.size)
        self._assets[rarity] = {**asset, 'rarity': rarity, 'builtin': True}
        return dict(self._assets[rarity])

    def defaults(self) -> dict:
        return {rarity: self.builtin(rarity)['id'] for rarity in RARITIES}

    def catalog(self) -> dict:
        defaults = {}
        for rarity in RARITIES:
            asset = self.builtin(rarity)
            defaults[rarity] = {k: asset[k] for k in ('id', 'url', 'width', 'height')}
        return {'version': SYMBOL_SET_VERSION, 'defaults': defaults}

    def settings(self, values: dict | None) -> dict:
        """Fill omitted rarities from bundled defaults; preserve explicit assets.

        Concrete asset IDs are saved into each deck, so later app updates cannot
        silently replace a deck's symbols. Changing them requires an explicit
        upload/generate/restore action.
        """
        values = values or {}
        if not isinstance(values, dict):
            raise ValidationError('Invalid deck settings.')
        requested = values.get('symbols') or {}
        if not isinstance(requested, dict):
            raise ValidationError('Invalid rarity-symbol selection.')
        unknown = sorted(set(requested) - set(RARITIES))
        if unknown:
            raise ValidationError('Unknown rarity symbol: ' + ', '.join(unknown))
        result = self.defaults()
        for rarity in RARITIES:
            ident = requested.get(rarity)
            if not ident:
                continue
            asset = self.store.asset(str(ident))
            if not asset or not asset['mime'].startswith('image/'):
                raise ValidationError('A selected rarity symbol is missing. Restore the built-in defaults or upload it again.')
            result[rarity] = str(ident)
        return result
