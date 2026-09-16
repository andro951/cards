"""Portable workspace backups. No runtime, font files, credentials or HTTP cache."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import time
import zipfile
from pathlib import Path

from .domain import ValidationError, uid, validate_template
from .images import decode_image

MAX_BACKUP_BYTES = 2 * 1024 ** 3
MAX_MEMBERS = 25000


def referenced_assets(value):
    found = set()
    def visit(item):
        if isinstance(item, dict):
            for v in item.values(): visit(v)
        elif isinstance(item, list):
            for v in item: visit(v)
        elif isinstance(item, str):
            if re.fullmatch(r'[0-9a-f]{64}', item): found.add(item)
            for match in re.finditer(r'/api/assets/([0-9a-f]{64})', item): found.add(match[1])
    visit(value)
    return found


class Backups:
    def __init__(self, workspace):
        self.ws = workspace
        self.store = workspace.store

    def export(self, progress=lambda *a: None, cancel=lambda: False):
        docs = {kind: self.store.list(kind) + self.store.list(kind, deleted=True)
                for kind in ('decks', 'templates')}
        docs['settings'] = [self.ws.global_settings()]
        render_keys = set()
        for d in docs['decks']:
            for c in d.get('cards', []):
                for f in c.get('faces', []):
                    k = (f.get('compiled') or {}).get('renderKey')
                    if k: render_keys.add(k)
        renders = [r for k in render_keys if (r := self.store.render_get(k))]
        ids = referenced_assets([docs, renders])
        assets = []
        for ident in sorted(ids):
            a = self.store.asset(ident)
            if a and a['mime'].startswith('image/'):
                assets.append(a)
        manifest = {'format': 'proxy-foundry-backup', 'schema': 1,
                    'createdAt': time.time(), 'documents': docs, 'renders': renders,
                    'assets': [{k: a.get(k) for k in ('id', 'mime', 'width', 'height', 'size')} for a in assets]}
        name = 'ProxyFoundry_Backup_' + time.strftime('%Y%m%d_%H%M%S') + '_' + uid()[:8] + '.zip'
        dest = self.store.home / 'backups' / name
        partial = dest.with_suffix('.partial')
        try:
            with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
                z.writestr('workspace.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False))
                for i, a in enumerate(assets):
                    if cancel(): raise ValidationError('Backup cancelled.')
                    z.write(self.store.asset_path(a['id']), 'assets/' + a['id'] + '.png')
                    progress(i + 1, len(assets), 'Saving workspace image ' + str(i + 1))
            partial.replace(dest)
            return {'filename': name, 'download': '/api/backups/' + name,
                    'bytes': dest.stat().st_size, 'decks': len(docs['decks'])}
        except Exception:
            partial.unlink(missing_ok=True)
            raise

    def restore(self, path: Path, apply_defaults=False, progress=lambda *a: None, cancel=lambda: False):
        # Validate before mutating the workspace. Existing decks are never replaced.
        try:
            z = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as e:
            raise ValidationError('Choose a Proxy Foundry backup ZIP.') from e
        with z:
            members = z.infolist()
            names = [x.filename for x in members]
            if len(members) > MAX_MEMBERS or len(set(names)) != len(names):
                raise ValidationError('Backup contains too many files or duplicate entries.')
            if sum(x.file_size for x in members) > MAX_BACKUP_BYTES:
                raise ValidationError('Backup exceeds the 2 GB expanded-size limit.')
            if 'workspace.json' not in names or z.getinfo('workspace.json').file_size > 100 * 1024 ** 2:
                raise ValidationError('Backup workspace manifest is missing or too large.')
            if any(not re.fullmatch(r'(workspace\.json|assets/[0-9a-f]{64}\.png)', n) for n in names):
                raise ValidationError('Backup contains an unexpected file path.')
            try: m = json.loads(z.read('workspace.json'))
            except (ValueError, UnicodeDecodeError) as e: raise ValidationError('Invalid backup manifest.') from e
            if m.get('format') != 'proxy-foundry-backup' or m.get('schema') != 1:
                raise ValidationError('This is not a supported Proxy Foundry backup.')
            docs = m.get('documents', {})
            if any(not isinstance(docs.get(k), list) for k in ('decks', 'templates', 'settings')):
                raise ValidationError('Backup documents are invalid.')
            if len(docs['decks']) > 1000 or len(docs['templates']) > 1000:
                raise ValidationError('Backup contains too many decks or templates.')
            templates = docs['templates']
            for t in templates: validate_template(t.get('data', {}))
            for d in docs['decks']:
                if not isinstance(d.get('cards'), list) or len(d['cards']) > 10000:
                    raise ValidationError('Backup card list is invalid.')
                from .domain import quantity
                for c in d['cards']:
                    quantity(c.get('quantity'))
                    if not isinstance(c.get('scryfall'), dict) or not isinstance(c.get('faces'), list):
                        raise ValidationError('Backup contains an invalid card.')
                    for f in c['faces']:
                        if f.get('compiled'): validate_template(f['compiled']['data'])
            staged = []
            for i, a in enumerate(m.get('assets', [])):
                if cancel(): raise ValidationError('Backup import cancelled.')
                ident = a.get('id', '')
                if not re.fullmatch(r'[0-9a-f]{64}', ident): raise ValidationError('Invalid backup image identifier.')
                filename = 'assets/' + ident + '.png'
                if filename not in names or z.getinfo(filename).file_size > 64 * 1024 ** 2:
                    raise ValidationError('A backup image is missing or too large.')
                raw = z.read(filename)
                if hashlib.sha256(raw).hexdigest() != ident: raise ValidationError('A backup image failed its integrity check.')
                im = decode_image(raw)
                # Store immutable validated assets. They are harmless if a later validation fails.
                asset = self.store.add_asset(raw, 'image/png', im.width, im.height)
                staged.append(asset['id'])
                progress(i + 1, len(m['assets']), 'Validating backup image ' + str(i + 1))
            template_map = {t['id']: uid() for t in templates}
            imported = []
            # One SQLite transaction for all restored document records and render mappings.
            import time as _time
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for kind in ('templates', 'decks'):
                    for src in docs[kind]:
                        d = copy.deepcopy(src)
                        ident = template_map[d['id']] if kind == 'templates' else uid()
                        for key in ('id', 'revision', 'createdAt', 'updatedAt'): d.pop(key, None)
                        deleted = int(bool(d.pop('deleted', False)))
                        if kind == 'decks':
                            d['name'] = str(d.get('name') or 'Recovered deck') + ' · restored'
                            rules = d.get('settings', {}).get('templateRules', {})
                            for group, value in rules.items(): rules[group] = template_map.get(value, value)
                            for c in d['cards']:
                                c['id'] = uid()
                                for f in c['faces']:
                                    f['id'] = uid()
                                    f['templateOverride'] = template_map.get(f.get('templateOverride'), f.get('templateOverride'))
                            imported.append(ident)
                        now = _time.time()
                        db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?)',
                                   (kind, ident, 1, json.dumps(d, ensure_ascii=False, allow_nan=False), now, now, deleted))
                for r in m.get('renders', []):
                    if re.fullmatch(r'[0-9a-f]{64}', r.get('render_key', '')) and r.get('asset_id') in staged:
                        a = self.store.asset(r['asset_id'])
                        db.execute('INSERT OR IGNORE INTO renders VALUES (?,?,?,?,?)',
                                   (r['render_key'], r['asset_id'], a['width'], a['height'], _time.time()))
            if apply_defaults and docs['settings']:
                defaults = docs['settings'][0]
                self.ws.set_global_settings({k: defaults[k] for k in ('refreshData', 'defaults') if k in defaults})
            return {'decks': len(imported), 'templates': len(templates), 'ids': imported}
