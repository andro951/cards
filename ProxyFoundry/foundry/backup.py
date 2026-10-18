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

from .domain import ConflictError, ValidationError, uid, validate_template, quantity
from .images import decode_image
from .template_model import validate_model

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

    def export(self, progress=lambda *a: None, cancel=lambda: False, include_renders=True):
        steps=self.export_steps(progress,cancel,include_renders)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def export_steps(self, progress=lambda *a: None, cancel=lambda: False, include_renders=True):
        if cancel():raise ValidationError('Backup cancelled.')
        docs = {kind: self.store.list(kind) + self.store.list(kind, deleted=True)
                for kind in ('decks', 'templates', 'style-presets')}
        docs['settings'] = [self.ws.global_settings()]
        if not include_renders:
            docs = copy.deepcopy(docs)
            for deck in docs['decks']:
                for card in deck.get('cards', []):
                    for face in card.get('faces', []):
                        (face.get('compiled') or {}).pop('render', None)
        render_keys = set()
        for d in docs['decks']:
            for c in d.get('cards', []):
                for f in c.get('faces', []):
                    k = (f.get('compiled') or {}).get('renderKey')
                    if k: render_keys.add(k)
        renders = [r for k in render_keys if (r := self.store.render_get(k))] if include_renders else []
        ids = referenced_assets([docs, renders])
        assets = []
        for ident in sorted(ids):
            a = self.store.asset(ident)
            if a and a['mime'].startswith('image/'):
                assets.append(a)
        manifest = {'format': 'proxy-foundry-backup', 'schema': 1,
                    'createdAt': time.time(), 'documents': docs, 'renders': renders,
                    'includesRenders': bool(include_renders),
                    'assets': [{k: a.get(k) for k in ('id', 'mime', 'width', 'height', 'size')} for a in assets]}
        name = 'ProxyFoundry_Backup_' + time.strftime('%Y%m%d_%H%M%S') + '_' + uid()[:8] + '.zip'
        dest = self.store.home / 'backups' / name
        partial = dest.with_suffix('.partial')
        try:
            with self.store.pin_assets(a['id'] for a in assets),zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
                z.writestr('workspace.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False))
                for i, a in enumerate(assets):
                    if cancel(): raise ValidationError('Backup cancelled.')
                    z.write(self.store.asset_path(a['id']), 'assets/' + a['id'] + '.png')
                    progress(i + 1, len(assets), 'Saving workspace image ' + str(i + 1))
                    yield
            if cancel():raise ValidationError('Backup cancelled.')
            partial.replace(dest)
            return {'filename': name, 'download': '/api/backups/' + name,
                    'bytes': dest.stat().st_size, 'decks': len(docs['decks'])}
        finally:
            partial.unlink(missing_ok=True)

    def catalog(self, path: Path):
        try:
            with zipfile.ZipFile(path) as archive:
                members=archive.infolist()
                names=[member.filename for member in members]
                if len(members)>MAX_MEMBERS or len(names)!=len(set(names)) or sum(m.file_size for m in members)>MAX_BACKUP_BYTES:
                    raise ValidationError('Backup is too large or contains duplicate files.')
                if 'workspace.json' not in names or archive.getinfo('workspace.json').file_size>100*1024**2:
                    raise ValidationError('Backup workspace manifest is missing or too large.')
                if any(not re.fullmatch(r'(workspace\.json|assets/[0-9a-f]{64}\.png)',name) for name in names):
                    raise ValidationError('Backup contains an unexpected file path.')
                manifest=json.loads(archive.read('workspace.json'))
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            raise ValidationError('Choose a valid Bulk Proxy Forge backup ZIP.') from exc
        if manifest.get('format')!='proxy-foundry-backup' or manifest.get('schema')!=1:
            raise ValidationError('This is not a supported Bulk Proxy Forge backup.')
        documents=manifest.get('documents') or {}
        if any(not isinstance(documents.get(kind),list) for kind in ('decks','templates')):
            raise ValidationError('Backup document list is invalid.')
        documents.setdefault('style-presets',[])
        if not isinstance(documents['style-presets'],list):raise ValidationError('Backup style list is invalid.')
        catalog={}
        for kind in ('decks','templates','style-presets'):
            if len(documents[kind])>1000:raise ValidationError('Backup contains too many objects.')
            catalog[kind]=[]
            for entry in documents[kind]:
                ident=entry.get('id') if isinstance(entry,dict) else None
                if not isinstance(ident,str) or not re.fullmatch(r'[-a-f0-9]{36}',ident):
                    raise ValidationError('Backup contains an invalid object identifier.')
                if entry.get('deleted'):continue
                catalog[kind].append({'id':ident,'name':str(entry.get('name') or 'Untitled'),
                                      'collision':bool(self.store.get(kind,ident,include_deleted=True))})
        return {'objects':catalog,'includesRenders':bool(manifest.get('includesRenders',bool(manifest.get('renders')))),
                'createdAt':manifest.get('createdAt'),'manifest':manifest}

    def import_selected(self, path: Path, selected, replace=(), progress=lambda *a:None, cancel=lambda:False):
        catalog=self.catalog(path)
        manifest=catalog['manifest']
        documents=manifest['documents']
        if not isinstance(selected,dict):raise ValidationError('Choose backup objects to import.')
        picked={kind:set(selected.get(kind) or []) for kind in ('decks','templates','style-presets')}
        confirmed=set(replace or [])
        objects={}
        for kind in picked:
            choices={item['id'] for item in catalog['objects'][kind]}
            if not picked[kind]<=choices:raise ValidationError('Backup selection includes an unknown object.')
            objects[kind]=[copy.deepcopy(item) for item in documents[kind] if item['id'] in picked[kind]]
            for item in objects[kind]:
                if self.store.get(kind,item['id'],include_deleted=True) and item['id'] not in confirmed:
                    raise ConflictError('You already have '+str(item.get('name') or 'this item')+'. Confirm replacement before importing.')
        for item in objects['templates']:
            if item.get('schemaVersion') in {2,3}:item.update(validate_model(item))
            else:validate_template(item.get('data',{}))
        for item in objects['style-presets']:
            if not isinstance(item.get('settings'),dict):raise ValidationError('Backup contains an invalid style.')
        for deck in objects['decks']:
            if not isinstance(deck.get('cards'),list) or len(deck['cards'])>10000:
                raise ValidationError('Backup contains an invalid deck.')
            for card in deck['cards']:
                quantity(card.get('quantity'))
                if not isinstance(card.get('scryfall'),dict) or not isinstance(card.get('faces'),list):
                    raise ValidationError('Backup contains an invalid card.')
                for face in card['faces']:
                    if face.get('compiled'):validate_template(face['compiled']['data'])
        renders=[item for item in manifest.get('renders',[]) if item.get('deck_id') in picked['decks']]
        listed={asset.get('id'):asset for asset in manifest.get('assets',[]) if isinstance(asset,dict)}
        needed=(referenced_assets(objects)&set(listed))|{item.get('asset_id') for item in renders if item.get('asset_id')}
        with zipfile.ZipFile(path) as archive:
            for index,ident in enumerate(sorted(needed)):
                if cancel():raise ValidationError('Backup import cancelled.')
                if self.store.asset(ident):continue
                entry=listed.get(ident)
                filename='assets/'+ident+'.png'
                if not entry or filename not in archive.namelist() or archive.getinfo(filename).file_size>64*1024**2:
                    raise ValidationError('A required backup image is missing.')
                raw=archive.read(filename)
                if hashlib.sha256(raw).hexdigest()!=ident:raise ValidationError('A backup image failed its integrity check.')
                image=decode_image(raw)
                self.store.add_asset(raw,str(entry.get('mime') or 'image/png'),image.width,image.height)
                progress(index+1,len(needed),'Importing backup image '+str(index+1))
        counts={kind:0 for kind in objects}
        for kind in ('templates','style-presets','decks'):
            for item in objects[kind]:
                old=self.store.get(kind,item['id'],include_deleted=True)
                if old:self.store.purge(kind,item['id'])
                item.pop('deleted',None)
                self.store.put(kind,item)
                counts[kind]+=1
        deck_map={item['id']:item for item in objects['decks']}
        for render in renders:
            deck=deck_map.get(render.get('deck_id'))
            asset=self.store.asset(render.get('asset_id',''))
            if not deck or not asset:continue
            for card in deck.get('cards',[]):
                for face in card.get('faces',[]):
                    if face.get('id')==render.get('face_id'):
                        self.store.render_put(render['render_key'],asset,deck_id=deck['id'],card_id=card['id'],
                                              face_id=face['id'],deck_name=deck['name'],face_name=face['name'])
        return counts

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
            for t in templates:
                if t.get('schemaVersion') in {2,3}:t.update(validate_model(t))
                else:validate_template(t.get('data',{}))
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
