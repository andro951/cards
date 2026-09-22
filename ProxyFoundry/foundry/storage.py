"""Transactional local workspace, immutable asset store and HTTP cache metadata."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import string
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .domain import ConflictError, ValidationError, uid, SCHEMA_VERSION


def _platform_data_root() -> Path:
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))


def launcher_config_path() -> Path:
    return _platform_data_root() / 'BulkProxyForgeLauncher' / 'storage.json'


def configured_home() -> Path | None:
    override = os.environ.get('BULK_PROXY_FORGE_HOME') or os.environ.get('PROXY_FOUNDRY_HOME')
    if override:
        return Path(override).expanduser().resolve()
    config = launcher_config_path()
    if not config.is_file():
        return None
    try:
        payload = json.loads(config.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    value = str(payload.get('home') or '').strip()
    return Path(value).expanduser().resolve() if value else None


def save_configured_home(home: Path) -> Path:
    home = Path(home).expanduser().resolve()
    config = launcher_config_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({'home': str(home)}, ensure_ascii=False, indent=2), encoding='utf-8')
    return home


def fallback_home() -> Path:
    root = _platform_data_root()
    current = root / 'BulkProxyForge'
    legacy = root / 'ProxyFoundry'
    return legacy if legacy.exists() and not current.exists() else current


def candidate_drive_homes(default_path: Path) -> list[Path]:
    if os.name != 'nt':
        return [default_path]
    default_drive = str(os.environ.get('SystemDrive') or default_path.drive or 'C:').upper()
    roots = []
    for letter in string.ascii_uppercase:
        root = Path(f'{letter}:\\')
        if root.exists():
            roots.append(root)
    roots.sort(key=lambda root: (0 if root.drive.upper() == default_drive else 1, root.drive))
    return [root / 'BulkProxyForge' for root in roots] or [default_path]


def prompt_for_storage_home(default_path: Path) -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except Exception as exc:
        raise ValidationError('A storage location must be selected before Bulk Proxy Forge can start.') from exc

    choices = candidate_drive_homes(default_path)
    root = tk.Tk()
    root.title('Bulk Proxy Forge storage location')
    root.resizable(False, False)

    selected = tk.StringVar(value=str(choices[0]))
    planned = tk.StringVar(value=str(choices[0]))
    use_specific = tk.BooleanVar(value=False)
    specific = tk.StringVar(value='')
    chosen = {'path': None}

    frame = ttk.Frame(root, padding=18)
    frame.grid(sticky='nsew')
    ttk.Label(
        frame,
        text='Choose which drive Bulk Proxy Forge should use for decks, generated images, and cache.',
        wraplength=540,
        justify='left',
    ).grid(row=0, column=0, columnspan=4, sticky='w')
    ttk.Label(frame, text='Drive', font=('', 10, 'bold')).grid(row=1, column=0, columnspan=4, sticky='w', pady=(14, 4))

    drive_box = ttk.Frame(frame)
    drive_box.grid(row=2, column=0, columnspan=4, sticky='w')
    for i, path in enumerate(choices):
        ttk.Radiobutton(
            drive_box,
            text=path.drive or str(path),
            value=str(path),
            variable=selected,
            command=lambda: update_planned(),
        ).grid(row=i // 4, column=i % 4, padx=(0, 20), pady=2, sticky='w')

    ttk.Label(frame, text='Folder it will use:').grid(row=3, column=0, columnspan=4, sticky='w', pady=(14, 2))
    ttk.Label(frame, textvariable=planned, wraplength=540).grid(row=4, column=0, columnspan=4, sticky='w')

    specific_wrap = ttk.Frame(frame)
    specific_wrap.grid(row=5, column=0, columnspan=4, sticky='ew', pady=(14, 0))
    specific_row = ttk.Frame(specific_wrap)
    specific_row.columnconfigure(0, weight=1)
    entry = ttk.Entry(specific_row, textvariable=specific, width=58)
    entry.grid(row=0, column=0, sticky='ew')

    def update_planned(*_):
        value = specific.get().strip() if use_specific.get() and specific.get().strip() else selected.get()
        planned.set(value)

    def toggle_specific():
        if use_specific.get():
            specific_row.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        else:
            specific_row.grid_remove()
        update_planned()

    def browse():
        start = specific.get().strip() or selected.get() or str(default_path)
        picked = filedialog.askdirectory(initialdir=start, title='Choose Bulk Proxy Forge storage folder')
        if picked:
            specific.set(picked)
            use_specific.set(True)
            toggle_specific()

    ttk.Checkbutton(
        specific_wrap,
        text='Pick a specific folder',
        variable=use_specific,
        command=toggle_specific,
    ).grid(row=0, column=0, sticky='w')
    ttk.Button(specific_row, text='Browse…', command=browse).grid(row=0, column=1, padx=(8, 0))
    specific_row.grid(row=1, column=0, sticky='ew', pady=(8, 0))
    specific_row.grid_remove()

    def finish():
        value = planned.get().strip()
        if value:
            chosen['path'] = Path(value).expanduser().resolve()
            root.destroy()

    def cancel():
        root.destroy()

    specific.trace_add('write', update_planned)
    root.protocol('WM_DELETE_WINDOW', cancel)
    ttk.Button(frame, text='Continue', command=finish).grid(row=6, column=3, sticky='e', pady=(18, 0))

    root.update_idletasks()
    root.geometry(
        f'+{max((root.winfo_screenwidth()-root.winfo_width())//2,0)}'
        f'+{max((root.winfo_screenheight()-root.winfo_height())//3,0)}'
    )
    root.mainloop()
    if not chosen['path']:
        raise ValidationError('Choose a storage location to continue.')
    return chosen['path']


def ensure_storage_home_selected() -> Path:
    selected = configured_home()
    if selected:
        return selected
    return save_configured_home(prompt_for_storage_home(fallback_home()))


def default_home() -> Path:
    return configured_home() or fallback_home()


def display_name(text: str, fallback='item') -> str:
    value = ' '.join(str(text or '').strip().split()) or fallback
    value = re.sub(r'[<>:"/\\|?*]+', ' ', value).strip(' .')
    value = ' '.join(value.split())
    return value or fallback


class Store:
    def __init__(self, home: Path | None = None):
        self.home = Path(home or default_home()).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        for name in ('assets', 'renders', 'runtime', 'orders', 'logs', 'backups', 'tmp'):
            (self.home / name).mkdir(exist_ok=True)
        self.db_path = self.home / 'workspace.sqlite3'
        with self.connect() as db:
            db.executescript(f'''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    kind TEXT NOT NULL, id TEXT NOT NULL, rev INTEGER NOT NULL,
                    body TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, mime TEXT NOT NULL, size INTEGER NOT NULL,
                    width INTEGER, height INTEGER, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS http_cache (
                    url TEXT PRIMARY KEY, asset_id TEXT NOT NULL, mime TEXT NOT NULL,
                    fetched REAL NOT NULL, etag TEXT, last_modified TEXT);
                CREATE TABLE IF NOT EXISTS renders (
                    render_key TEXT PRIMARY KEY, asset_id TEXT NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL, created REAL NOT NULL,
                    deck_id TEXT, card_id TEXT, face_id TEXT UNIQUE, file_path TEXT NOT NULL UNIQUE);
                CREATE INDEX IF NOT EXISTS renders_deck_idx ON renders(deck_id);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('schema_version','{SCHEMA_VERSION}');
            ''')
            version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
            if version != str(SCHEMA_VERSION):
                raise ValidationError('This workspace uses a different Bulk Proxy Forge storage format. Choose a fresh storage folder for this version.')

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, kind: str, ident: str, include_deleted: bool = False) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM documents WHERE kind=? AND id=?', (kind, ident)).fetchone()
        if not row or (row['deleted'] and not include_deleted):
            return None
        data = json.loads(row['body'])
        return {**data, 'id': ident, 'revision': row['rev'], 'createdAt': row['created'],
                'updatedAt': row['updated'], 'deleted': bool(row['deleted'])}

    def list(self, kind: str, deleted: bool = False) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM documents WHERE kind=? AND deleted=? ORDER BY updated DESC',
                              (kind, int(deleted))).fetchall()
        return [{**json.loads(r['body']), 'id': r['id'], 'revision': r['rev'],
                 'createdAt': r['created'], 'updatedAt': r['updated'], 'deleted': bool(r['deleted'])} for r in rows]

    def put(self, kind: str, data: dict[str, Any], expected: int | None = None) -> dict[str, Any]:
        ident = data.get('id') or uid()
        now = time.time()
        body = {k: v for k, v in data.items() if k not in {'id', 'revision', 'createdAt', 'updatedAt', 'deleted'}}
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT rev,created FROM documents WHERE kind=? AND id=?', (kind, ident)).fetchone()
            if row and expected is not None and expected != row['rev']:
                raise ConflictError('This deck changed in another tab. Reload it before saving; your edits were not overwritten.')
            if not row and expected not in (None, 0):
                raise ConflictError('The item no longer exists. Reload before saving.')
            rev, created = (row['rev'] + 1, row['created']) if row else (1, now)
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?)',
                       (kind, ident, rev, encoded, created, now, int(bool(data.get('deleted', False)))))
        return self.get(kind, ident, include_deleted=True)

    def trash(self, kind: str, ident: str, expected: int | None = None, restore: bool = False) -> dict[str, Any]:
        old = self.get(kind, ident, include_deleted=True)
        if not old:
            raise ValidationError('That item no longer exists.')
        old['deleted'] = not restore
        return self.put(kind, old, expected)

    def purge(self, kind: str, ident: str, expected: int | None = None) -> dict[str, Any]:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT rev FROM documents WHERE kind=? AND id=?',(kind,ident)).fetchone()
            if not row:raise ValidationError('That item no longer exists.')
            if expected is not None and expected!=row['rev']:
                raise ConflictError('This deck changed in another tab. Reload before deleting it.')
            db.execute('DELETE FROM documents WHERE kind=? AND id=?',(kind,ident))
        if kind == 'decks':
            self.clear_deck_renders(ident)
        return {'id':ident,'permanent':True}

    def purge_trash(self, kind: str) -> dict[str, Any]:
        ids=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ids=[r[0] for r in db.execute('SELECT id FROM documents WHERE kind=? AND deleted=1',(kind,)).fetchall()]
            db.execute('DELETE FROM documents WHERE kind=? AND deleted=1',(kind,))
        if kind == 'decks':
            for ident in ids:
                self.clear_deck_renders(ident)
        return {'deleted':len(ids)}

    def asset_path(self, ident: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{64}', str(ident)):
            raise ValidationError('Invalid asset identifier.')
        return self.home / 'assets' / ident[:2] / ident

    def add_asset(self, content: bytes, mime: str, width: int | None = None, height: int | None = None) -> dict[str, Any]:
        if not content:
            raise ValidationError('The uploaded file is empty.')
        ident = hashlib.sha256(content).hexdigest()
        target = self.asset_path(ident)
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=target.parent, prefix='.upload-')
            try:
                with os.fdopen(fd, 'wb') as out:
                    out.write(content); out.flush(); os.fsync(out.fileno())
                os.replace(temp, target)
            finally:
                if os.path.exists(temp): os.unlink(temp)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?)',
                       (ident, mime, len(content), width, height, time.time()))
            if width and height:
                db.execute('UPDATE assets SET width=?,height=?,mime=? WHERE id=?', (width, height, mime, ident))
        return self.asset(ident)

    def asset(self, ident: str) -> dict[str, Any] | None:
        path = self.asset_path(ident)
        with self.connect() as db:
            row = db.execute('SELECT * FROM assets WHERE id=?', (ident,)).fetchone()
        return {**dict(row), 'url': '/api/assets/' + ident} if row and path.is_file() else None

    def cache_get(self, url: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM http_cache WHERE url=?', (url,)).fetchone()
        if row and self.asset_path(row['asset_id']).is_file():
            return dict(row)
        return None

    def cache_put(self, url: str, asset: dict[str, Any], fetched: float, headers: Any = None) -> None:
        headers = headers or {}
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?,?,?)',
                       (url, asset['id'], asset['mime'], fetched, headers.get('ETag'), headers.get('Last-Modified')))

    def _render_folder(self, deck_id: str | None, deck_name: str) -> Path:
        root=self.home/'renders'
        if deck_id:
            with self.connect() as db:
                row=db.execute('SELECT file_path FROM renders WHERE deck_id=? LIMIT 1',(deck_id,)).fetchone()
            if row:
                return (self.home/row['file_path']).parent
        base=display_name(deck_name,'Deck')
        candidate=root/base
        n=2
        while True:
            rel=str(candidate.relative_to(self.home)).replace('\\','/')+'/%'
            with self.connect() as db:
                conflict=db.execute('SELECT 1 FROM renders WHERE file_path LIKE ? AND (? IS NULL OR deck_id<>?) LIMIT 1',(rel,deck_id,deck_id)).fetchone()
            occupied=candidate.exists() and any(candidate.iterdir())
            if not conflict and not occupied:
                return candidate
            candidate=root/f'{base} ({n})';n+=1

    def _render_file(self, deck_id: str | None, deck_name: str, face_id: str | None, face_name: str) -> Path:
        folder=self._render_folder(deck_id,deck_name)
        base=display_name(face_name,'Card')
        candidate=folder/(base+'.png');n=2
        while True:
            rel=str(candidate.relative_to(self.home)).replace('\\','/')
            with self.connect() as db:
                row=db.execute('SELECT face_id FROM renders WHERE file_path=?',(rel,)).fetchone()
            if (not row or row['face_id']==face_id) and (not candidate.exists() or (face_id and row and row['face_id']==face_id)):
                return candidate
            candidate=folder/f'{base} ({n}).png';n+=1

    def _asset_is_render_only(self, ident: str) -> bool:
        with self.connect() as db:
            if db.execute('SELECT 1 FROM renders WHERE asset_id=? LIMIT 1',(ident,)).fetchone():
                return False
            if db.execute('SELECT 1 FROM http_cache WHERE asset_id=? LIMIT 1',(ident,)).fetchone():
                return False
        return True

    def _delete_render_asset_if_unused(self, ident: str) -> None:
        if not ident or not re.fullmatch(r'[0-9a-f]{64}',str(ident)) or not self._asset_is_render_only(ident):
            return
        with self.connect() as db:
            db.execute('DELETE FROM assets WHERE id=?',(ident,))
        path=self.asset_path(ident);path.unlink(missing_ok=True)
        try:path.parent.rmdir()
        except OSError:pass

    def render_get(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row=db.execute('SELECT * FROM renders WHERE render_key=?',(key,)).fetchone()
        if not row:return None
        path=self.home/row['file_path']
        if not path.is_file() or not self.asset_path(row['asset_id']).is_file():
            return None
        return {**dict(row),'url':'/api/assets/'+row['asset_id']}

    def render_put(self, key: str, asset: dict[str, Any], *, deck_id: str | None = None, card_id: str | None = None,
                   face_id: str | None = None, deck_name='Deck', face_name='Card') -> dict[str, Any]:
        if not asset.get('width') or not asset.get('height'):
            raise ValidationError('A render must be a decoded image.')
        old=None
        with self.connect() as db:
            if face_id:
                old=db.execute('SELECT * FROM renders WHERE face_id=?',(face_id,)).fetchone()
            if old is None:
                old=db.execute('SELECT * FROM renders WHERE render_key=?',(key,)).fetchone()
        output=self._render_file(deck_id,deck_name,face_id,face_name)
        output.parent.mkdir(parents=True,exist_ok=True)
        source=self.asset_path(asset['id'])
        temp=output.with_name('.'+output.name+'.'+uid()+'.tmp')
        try:
            try:os.link(source,temp)
            except OSError:shutil.copy2(source,temp)
            os.replace(temp,output)
        finally:
            temp.unlink(missing_ok=True)
        rel=str(output.relative_to(self.home)).replace('\\','/')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if old and old['render_key']!=key:
                db.execute('DELETE FROM renders WHERE render_key=?',(old['render_key'],))
            db.execute('INSERT OR REPLACE INTO renders VALUES (?,?,?,?,?,?,?,?,?)',
                       (key,asset['id'],asset['width'],asset['height'],time.time(),deck_id,card_id,face_id,rel))
        if old:
            old_path=self.home/old['file_path']
            if old_path!=output:
                old_path.unlink(missing_ok=True)
                try:old_path.parent.rmdir()
                except OSError:pass
            if old['asset_id']!=asset['id']:
                self._delete_render_asset_if_unused(old['asset_id'])
        return self.render_get(key)

    def clear_deck_renders(self, deck_id: str) -> int:
        with self.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM renders WHERE deck_id=?',(deck_id,)).fetchall()]
            db.execute('DELETE FROM renders WHERE deck_id=?',(deck_id,))
        for row in rows:
            path=self.home/row['file_path'];path.unlink(missing_ok=True)
            try:path.parent.rmdir()
            except OSError:pass
        for ident in {row['asset_id'] for row in rows}:
            self._delete_render_asset_if_unused(ident)
        return len(rows)

    def clear_renders(self) -> dict[str, Any]:
        with self.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM renders').fetchall()]
            db.execute('DELETE FROM renders')
        shutil.rmtree(self.home/'renders',ignore_errors=True)
        (self.home/'renders').mkdir(exist_ok=True)
        for ident in {row['asset_id'] for row in rows}:
            self._delete_render_asset_if_unused(ident)
        return {'deleted':len(rows)}

    def stats(self) -> dict[str, Any]:
        with self.connect() as db:
            cache_count=db.execute('SELECT count(*) FROM http_cache').fetchone()[0]
            assets=db.execute('SELECT count(*),coalesce(sum(size),0) FROM assets').fetchone()
            renders=db.execute('SELECT count(*) FROM renders').fetchone()[0]
            render_bytes=db.execute('SELECT coalesce(sum(size),0) FROM assets WHERE id IN (SELECT DISTINCT asset_id FROM renders)').fetchone()[0]
        return {'cacheEntries':cache_count,'assets':assets[0],'assetBytes':assets[1],'renders':renders,
                'renderBytes':render_bytes,'home':str(self.home)}

    def snapshot(self, target: Path) -> None:
        with self.connect() as db, sqlite3.connect(target) as out:
            db.backup(out)
