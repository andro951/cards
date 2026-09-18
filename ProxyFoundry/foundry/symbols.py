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
    'common': {'file': 'common.webp', 'size': (92, 128), 'sha256': '76954ff3ca0176845c1ccbd15fece5a8a76bed5cf99b26919fbde4e0157406db'},
    'uncommon': {'file': 'uncommon.webp', 'size': (92, 128), 'sha256': '684b550f3842d681877133971125aa3f10276acc4795e637d697078096a63cc2'},
    'rare': {'file': 'rare.webp', 'size': (93, 128), 'sha256': '28df76a9a37d68b74d2ac0c746863549cc20521a777ecf47027bd15d3aa3aef2'},
    'mythic': {'file': 'mythic.webp', 'size': (93, 128), 'sha256': '80c445e1b16f02722af5328767c6c17eab2acb8576198e71f791f278376e63c1'},
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
