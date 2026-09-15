"""Transactional local workspace, immutable asset store and HTTP cache metadata."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .domain import ConflictError, ValidationError, uid


def default_home() -> Path:
    override = os.environ.get('PROXY_FOUNDRY_HOME')
    if override:
        return Path(override).expanduser().resolve()
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'ProxyFoundry'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'ProxyFoundry'


class Store:
    def __init__(self, home: Path | None = None):
        self.home = Path(home or default_home()).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        for name in ('assets', 'runtime', 'orders', 'logs', 'backups', 'tmp'):
            (self.home / name).mkdir(exist_ok=True)
        self.db_path = self.home / 'workspace.sqlite3'
        with self.connect() as db:
            db.executescript('''
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
                    width INTEGER NOT NULL, height INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('schema_version','1');
            ''')
            version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
            if version != '1':
                raise ValidationError('This workspace was created by a newer Proxy Foundry. Upgrade before opening it.')

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

    def render_get(self, key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM renders WHERE render_key=?', (key,)).fetchone()
        if row and self.asset_path(row['asset_id']).is_file():
            return {**dict(row), 'url': '/api/assets/' + row['asset_id']}
        return None

    def render_put(self, key: str, asset: dict[str, Any]) -> dict[str, Any]:
        if not asset.get('width') or not asset.get('height'):
            raise ValidationError('A render must be a decoded image.')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO renders VALUES (?,?,?,?,?)',
                       (key, asset['id'], asset['width'], asset['height'], time.time()))
        return self.render_get(key)

    def stats(self) -> dict[str, Any]:
        with self.connect() as db:
            cache_count = db.execute('SELECT count(*) FROM http_cache').fetchone()[0]
            assets = db.execute('SELECT count(*),coalesce(sum(size),0) FROM assets').fetchone()
            renders = db.execute('SELECT count(*) FROM renders').fetchone()[0]
        return {'cacheEntries': cache_count, 'assets': assets[0], 'assetBytes': assets[1], 'renders': renders,
                'home': str(self.home)}

    def snapshot(self, target: Path) -> None:
        with self.connect() as db, sqlite3.connect(target) as out:
            db.backup(out)
