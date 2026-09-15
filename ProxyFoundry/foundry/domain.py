"""Pure, testable rules for the deck workspace. No network or filesystem effects."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
import uuid
from typing import Any
from urllib.parse import unquote, urlsplit

DAY = 86400
CACHE_NORMAL_SECONDS = 365 * DAY
CACHE_REFRESH_SECONDS = 7 * DAY
RARITIES = ('common', 'uncommon', 'rare', 'mythic')
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'}
CC_COMMIT = '2fcddba8966156d484cedf54d8214996748dd5e1'
CC_REPO = 'Investigamer/cardconjurer'
COMPAT_COMMIT = '47087b3fc21e2cef61c58b9ebf180968ee991658'
COMPAT_REPO = 'd1rtyskittl3z/Card-Cipherist'
SCHEMA_VERSION = 1


class ValidationError(ValueError):
    """A user-actionable validation failure."""


class ConflictError(ValidationError):
    """A newer deck revision exists; never overwrite it silently."""


def uid() -> str:
    return str(uuid.uuid4())


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def slug(text: str) -> str:
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace('Æ', 'AE').replace('æ', 'ae').replace('Œ', 'OE').replace('œ', 'oe')
    text = re.sub(r"['’]", '', text)
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_').lower()


def quantity(value: Any) -> int:
    try:
        parsed = int(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValidationError('Quantity must be a whole number.') from exc
    if isinstance(value, bool) or str(value).strip() != str(parsed):
        raise ValidationError('Quantity must be a whole number.')
    result = int(value)
    if not 1 <= result <= 9999:
        raise ValidationError('Quantity must be between 1 and 9,999.')
    return result


def cache_is_fresh(fetched_at: float | None, now: float, refresh: bool = False) -> bool:
    if fetched_at is None:
        return False
    return max(0.0, now - fetched_at) < (CACHE_REFRESH_SECONDS if refresh else CACHE_NORMAL_SECONDS)


def github_location(raw: str, branch: str | None = None) -> dict[str, str]:
    """Parse folder URLs without interpreting a Windows path as a repository.

    A branch containing / must be URL-encoded or supplied in the separate ref field.
    Bare owner/repo/folder defaults to main; the importer resolves the real default branch.
    """
    raw = str(raw).strip()
    if not raw or re.match(r'^[A-Za-z]:[\\/]', raw) or raw.startswith(('\\\\', 'file:')):
        raise ValidationError('Choose Computer folder for local files, or paste a GitHub folder URL.')
    defaulted = False
    if '://' not in raw:
        raw = 'https://github.com/' + raw.strip('/')
    u = urlsplit(raw)
    if u.scheme != 'https' or u.username or u.password or u.port:
        raise ValidationError('Use an HTTPS GitHub folder URL.')
    parts = [p for p in u.path.strip('/').split('/') if p]
    if u.hostname == 'raw.githubusercontent.com' and len(parts) >= 3:
        owner, repo, ref = map(unquote, parts[:3]); folder = '/'.join(map(unquote, parts[3:]))
    elif u.hostname in {'github.com', 'www.github.com'} and len(parts) >= 2:
        owner, repo = map(unquote, parts[:2])
        if len(parts) >= 4 and parts[2] in {'tree', 'blob'}:
            ref = unquote(parts[3]); folder = '/'.join(map(unquote, parts[4:]))
        else:
            ref = branch or 'main'; folder = '/'.join(map(unquote, parts[2:])); defaulted = not bool(branch)
    else:
        raise ValidationError('Use github.com/owner/repository/tree/ref/folder or owner/repository/folder.')
    if branch:
        ref = str(branch).strip()
    for component in [owner, repo, ref, *folder.split('/')]:
        if component in {'.', '..'} or '\\' in component or '\x00' in component:
            raise ValidationError('Invalid GitHub folder or ref.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo):
        raise ValidationError('Invalid GitHub owner or repository name.')
    return {'repo': f'{owner}/{repo.removesuffix(".git")}', 'ref': ref, 'folder': folder,
            'default_ref': defaulted}


def parse_deck_text(text: str, include_outside: bool = False) -> list[dict[str, Any]]:
    """Parse names, Scryfall links, UUIDs, and Arena set/collector deck exports."""
    section = 'mainboard'; result: list[dict[str, Any]] = []
    headings = {'commander', 'commanders', 'deck', 'mainboard', 'main deck', 'lands', 'nonlands',
                'sideboard', 'maybeboard', 'outside the game', 'outside_the_game', 'companion'}
    for lineno, line in enumerate(str(text).splitlines(), 1):
        line = line.strip().lstrip('\ufeff')
        if not line or line.startswith(('#', '//')):
            continue
        header = line.rstrip(':').strip().lower()
        if header in headings:
            section = header.replace(' ', '_'); continue
        if section in {'sideboard', 'maybeboard'} or (section == 'outside_the_game' and not include_outside):
            continue
        line = re.sub(r'\s+\*[A-Z]\*\s*$', '', line)
        match = re.match(r'^(\d+)\s*[xX]?\s+(.+)$', line)
        count, name = (quantity(match[1]), match[2].strip()) if match else (1, line)
        printing = re.match(r'^(.*?)\s+\(([A-Za-z0-9]+)\)\s+([A-Za-z0-9★†-]+)(?:\s+.*)?$', name)
        entry: dict[str, Any] = {'source': name, 'name': name, 'quantity': count, 'section': section, 'line': lineno}
        if printing:
            entry.update(name=printing[1], source=f'{printing[2].lower()}:{printing[3]}',
                         set=printing[2].lower(), collector_number=printing[3])
        result.append(entry)
    if not result:
        raise ValidationError('No cards were found. Paste one card per line, for example: 1 Sol Ring (CMM) 396.')
    if sum(r['quantity'] for r in result) > 10000:
        raise ValidationError('A deck may contain at most 10,000 physical cards.')
    return result


def type_group(face: dict[str, Any], parent: dict[str, Any] | None = None, index: int = 0) -> str:
    parent = parent or face
    layout = str(parent.get('layout') or face.get('scryfall_layout') or 'normal')
    tl = str(face.get('type_line') or '').lower()
    if not tl:
        tl = ' '.join(face.get('types', [])) + ' — ' + ' '.join(face.get('subtypes', []))
        tl = tl.lower()
        if face.get('legendary'):
            tl = 'legendary ' + tl
        if face.get('basic'):
            tl = 'basic ' + tl
    types, _, subtypes = tl.replace(' - ', ' — ').partition(' — ')
    if layout == 'modal_dfc': return 'modal-back' if index else 'modal-front'
    if layout in {'transform', 'double_faced_token', 'reversible_card'}: return 'transform-back' if index else 'transform-front'
    if layout in {'split', 'flip', 'adventure', 'meld', 'planar', 'scheme', 'vanguard', 'art_series', 'prototype'}:
        return layout.replace('_', '-')
    if layout == 'prepare' or face.get('prepared_spell'): return 'prepare'
    if 'saga' in subtypes: return 'saga-creature' if 'creature' in types else 'saga'
    if 'planeswalker' in types: return 'planeswalker'
    if 'battle' in types: return 'battle'
    for special in ('class', 'case', 'room'):
        if special in subtypes.split(): return special
    if 'land' in types:
        if 'creature' in types or 'enchantment' in types: return 'special-land'
        if 'basic' in types: return 'basic-land'
        return 'legendary-land' if 'legendary' in types else 'land'
    if layout in {'token', 'emblem'}: return layout
    return 'legendary' if 'legendary' in types else 'standard'


GROUP_LABELS = {
    'standard': 'Nonlegendary cards', 'legendary': 'Legendary cards', 'land': 'Nonlegendary lands',
    'legendary-land': 'Legendary lands', 'basic-land': 'Basic lands', 'modal-front': 'Modal DFC · front',
    'modal-back': 'Modal DFC · back', 'transform-front': 'Transform · front', 'transform-back': 'Transform · back',
    'saga': 'Sagas', 'saga-creature': 'Saga creatures', 'planeswalker': 'Planeswalkers', 'prepare': 'Prepare cards',
    'battle': 'Battles', 'class': 'Classes', 'case': 'Cases', 'room': 'Rooms', 'special-land': 'Special lands',
    'split': 'Split / aftermath', 'flip': 'Flip cards', 'adventure': 'Adventure cards', 'meld': 'Meld cards',
    'token': 'Tokens', 'emblem': 'Emblems', 'planar': 'Planes / phenomena', 'scheme': 'Schemes',
    'vanguard': 'Vanguards', 'art-series': 'Art series', 'prototype': 'Prototype cards',
}
ORDINARY_GROUPS = {'standard', 'legendary', 'land', 'legendary-land', 'basic-land'}


def is_legendary(face: dict[str, Any]) -> bool:
    return bool(face.get('legendary') or 'Legendary' in str(face.get('type_line', '')).split(' — ')[0].split())


def crop_metrics(iw: int, ih: int, data: dict[str, Any], threshold: float = .20) -> dict[str, Any]:
    if min(iw, ih) <= 0:
        raise ValidationError('Artwork has invalid dimensions.')
    bounds = data.get('artBounds') or {'x': 0, 'y': 0, 'width': 1, 'height': 1}
    cw, ch = int(data.get('width', 2010)), int(data.get('height', 2814))
    bw, bh = float(bounds['width']) * cw, float(bounds['height']) * ch
    if min(bw, bh) <= 0:
        raise ValidationError('The template has an invalid art window.')
    zoom = max(bw / iw, bh / ih)
    lost_x = max(0., min(1., 1 - bw / (iw * zoom)))
    lost_y = max(0., min(1., 1 - bh / (ih * zoom)))
    return {'width': iw, 'height': ih, 'windowWidth': round(bw), 'windowHeight': round(bh),
            'cropX': round(lost_x, 6), 'cropY': round(lost_y, 6),
            'warning': max(lost_x, lost_y) > threshold + 1e-9, 'threshold': threshold}


def render_key(data: dict[str, Any], art_digest: str = '') -> str:
    """Only front-face inputs. Quantity and deck/default backs must never enter this key."""
    return stable_hash({'renderer': CC_COMMIT, 'compiler': 'card-tools-v48', 'adapter': 1,
                        'art': art_digest, 'data': data})


def validate_template(entry: Any) -> dict[str, Any]:
    if isinstance(entry, list):
        if len(entry) != 1:
            raise ValidationError('Choose one template face at a time from this file.')
        entry = entry[0]
    if not isinstance(entry, dict):
        raise ValidationError('A template must be a CardConjurer object.')
    data = copy.deepcopy(entry.get('data', entry))
    if not isinstance(data.get('frames'), list) or not isinstance(data.get('text'), dict):
        raise ValidationError('The template needs frames[] and text{} from a CardConjurer save.')
    if len(data['frames']) > 200 or len(data['text']) > 100:
        raise ValidationError('This template has too many layers or text boxes.')
    for key in ('width', 'height'):
        n = data.get(key)
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 100 <= n <= 8192:
            raise ValidationError('Template canvas dimensions must be between 100 and 8,192 pixels.')
    if not all(k in data['text'] for k in ('title', 'type')):
        raise ValidationError('Templates need named title and type text boxes.')
    script_paths = [data.get('onload'), *(data.get('manaSymbols') or [])]
    for script in script_paths:
        if script and not re.fullmatch(r'/js/(?:frames|manaSymbols)/[A-Za-z0-9_./-]+\.js', str(script)):
            raise ValidationError('Template scripts must be paths in the pinned CardConjurer runtime, not external code.')
    def walk(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValidationError('Template numbers must be finite.')
        if isinstance(value, dict):
            for k, v in value.items():
                if k in {'__proto__', 'constructor', 'prototype'}:
                    raise ValidationError('Unsupported template property.')
                if k in {'src', 'artSource', 'setSymbolSource', 'watermarkSource'} and isinstance(v, str):
                    if v.lower().startswith(('javascript:', 'file:', 'blob:', 'data:text/')):
                        raise ValidationError('Templates may contain images, not executable or local-file URLs.')
                walk(v)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(data)
    return data
