"""Procedural Godzilla artifact gray, persisted in the user's asset cache."""
from __future__ import annotations

import io
import re
import threading
import time

from PIL import Image

from .domain import CC_COMMIT, CC_REPO
from . import transform_crown
from . import dfc_material


ARTIFACT_GRAY_VERSION = 'neutral-gray-v1'
ARTIFACT_GRAY_PERCENT = 70
ARTIFACT_GRAY_PREFIX = '/img/frames/proxy-foundry/godzilla/gray-artifact/'


def apply_artifact_gray(data, sem):
    """Select the cached material only for neutral artifact Godzilla pieces.

    Colorless uses the same upstream A assets, so selection must use the card's
    semantics rather than globally replacing the native A resource.
    """
    types = set(sem.get('types', []))
    if 'Artifact' not in types or 'Land' in types or sem.get('colors'):
        return
    for frame in data.get('frames', []):
        src = str(frame.get('src') or '')
        body = src == '/img/frames/m15/nickname/m15NicknameFrameA.png'
        header = re.fullmatch(r'/img/frames/proxy-foundry/godzilla/(Title|TitleJoined|Crown|CrownJoined)A\.png', src)
        if body or header:
            frame['src'] = ARTIFACT_GRAY_PREFIX + ('Frame' if body else header[1]) + '.png'
        elif src in {transform_crown.PREFIX+'CrownJoinedA.png',transform_crown.PREFIX+'CrownJoinedBackA.png'}:
            frame['src'] = ARTIFACT_GRAY_PREFIX + ('TransformCrownJoinedBack.png' if 'Back' in src else 'TransformCrownJoined.png')
        elif src in {dfc_material.PREFIX+'TitleColoredA.png',dfc_material.PREFIX+'CrownJoinedColoredA.png'}:
            frame['src']=ARTIFACT_GRAY_PREFIX+src.rsplit('/',1)[-1].replace('A.png','.png')
        elif src=='/img/frames/m15/transform/crowns/floating/a.png':
            frame['src']=ARTIFACT_GRAY_PREFIX+'TransformCrownFloating.png'
        elif src==dfc_material.PREFIX+'CrownFloatingBackA.png':
            frame['src']=ARTIFACT_GRAY_PREFIX+'TransformCrownFloatingBack.png'


def gray_artifact_png(raw: bytes) -> bytes:
    """Tint native light rims neutral gray; preserve geometry and alpha exactly.

    Multiplication keeps pure black fills/outlines black and retains the source
    bevel shading instead of replacing it with a flat solid color.
    """
    with Image.open(io.BytesIO(raw)) as source:
        rgba = source.convert('RGBA')
        gray = rgba.convert('L').point([(value * ARTIFACT_GRAY_PERCENT + 50) // 100 for value in range(256)])
        image = Image.merge('RGBA', (gray, gray, gray, rgba.getchannel('A')))
        output = io.BytesIO()
        image.save(output, 'PNG')
    return output.getvalue()


class ArtifactFrameCache:
    """Generate once per pinned source/version, without adding raster repo assets."""
    def __init__(self, store):
        self.store = store
        self._lock = threading.Lock()
        self._source_locks = {}

    def fetch(self, source_path, load_source):
        key = f'derived:{CC_REPO}:{CC_COMMIT}:{ARTIFACT_GRAY_VERSION}:{ARTIFACT_GRAY_PERCENT}:{source_path}'
        if source_path.startswith(transform_crown.PREFIX):
            key += ':'+transform_crown.BEVEL_VERSION
            if 'Back' in source_path:key += ':'+transform_crown.BACK_VERSION
            if 'Colored' in source_path:key += ':'+dfc_material.VERSION
        with self._lock:
            lock = self._source_locks.setdefault(key, threading.Lock())
        with lock:
            cached = self.store.cache_get(key)
            if cached:
                return self.store.asset_path(cached['asset_id']).read_bytes(), True
            raw, _ = load_source(source_path)
            result = gray_artifact_png(raw)
            asset = self.store.add_asset(result, 'image/png')
            self.store.cache_put(key, asset, time.time())
            return result, False
