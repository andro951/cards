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
    'common': {'file': 'common.webp', 'size': (92, 128), 'sha256': 'edf28920933fae71a7a8a3c404bb3ded697412126b07d9f3a45a56a6a1973f87'},
    'uncommon': {'file': 'uncommon.webp', 'size': (92, 128), 'sha256': 'cf2d3bc00d4f280b1819a6b32f6edff8d470717cfb82a740afcc761e1557a40c'},
    'rare': {'file': 'rare.webp', 'size': (93, 128), 'sha256': 'cc554cbc4e32b3f5b86b578f5b3945f3c2871ee1e333933451e9959cf8e96497'},
    'mythic': {'file': 'mythic.webp', 'size': (93, 128), 'sha256': '7c8fd85c9009a3918679dd09b3b5355d17ef51b486ce929b569de933d869dfeb'},
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
