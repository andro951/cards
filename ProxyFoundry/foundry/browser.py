"""In-browser adapter for the existing workspace API.

Pyodide runs this module in a dedicated Web Worker. No HTTP server is started.
"""
from __future__ import annotations

import json
import mimetypes
import re
import time
import traceback
import urllib.parse
from pathlib import Path

from .domain import ConflictError, ValidationError, uid
from .network import Network
from .storage import Store
from . import server


class BrowserHeaders(dict):
    """Fetch Headers are lowercase; the HTTP handler uses canonical names."""

    def __init__(self, headers):
        super().__init__((str(key).lower(), value) for key, value in headers.items())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


class BrowserJobs:
    def __init__(self, store):
        self.store = store
        self.jobs = {}

    def start(self, kind, operation):
        ident = uid()
        job = {'id': ident, 'kind': kind, 'state': 'running', 'done': 0,
               'total': 0, 'message': 'Starting', 'events': [], 'cancelled': False}
        self.jobs[ident] = job

        def update(done, total, message):
            job.update(done=done, total=total, message=str(message))
            job['events'].append({'at': time.time(), 'done': done, 'total': total,
                                  'message': str(message)})

        try:
            job['result'] = operation(update, lambda: job['cancelled'])
            job.update(state='done', message='Complete')
        except Exception as exc:
            job.update(state='failed', message=str(exc), error=str(exc),
                       trace=traceback.format_exc())
        job['finishedAt'] = time.time()
        return {'id': ident}

    def get(self, ident):
        if ident not in self.jobs:
            raise ValidationError('This job belongs to an earlier browser session.')
        return dict(self.jobs[ident])

    def cancel(self, ident):
        if ident in self.jobs:
            self.jobs[ident]['cancelled'] = True
        return {'ok': True}

    def close(self):
        pass


class BrowserHandler(server.Handler):
    def __init__(self, app, method, path, body, headers):
        self._app = app
        self.command = method
        self.path = path
        self._body = body
        self.headers = BrowserHeaders(headers)
        self.response = None

    @property
    def app(self):
        return self._app

    def body(self, limit=server.MAX_BODY):
        if len(self._body) > limit:
            raise ValidationError(f'Upload limit is {limit // (1024 ** 2)} MB.')
        return self._body

    def send_bytes(self, content, mime='application/json', status=200, *, filename=None, headers=None):
        self.response = {'status': status, 'mime': mime, 'body': bytes(content),
                         'filename': filename, 'headers': headers or {}}

    def file(self, path, mime=None, filename=None, *, allow_range=False):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError('The saved file is missing.')
        kind=mime or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        requested=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers.get('Range',''))
        if requested:
            start,end=map(int,requested.groups())
            size=path.stat().st_size
            if start>=size or end<start or end-start>=8*1024*1024:
                raise ValidationError('Choose a valid bounded download range.')
            count=min(end,size-1)-start+1
            with path.open('rb') as source:
                source.seek(start)
                content=source.read(count)
            return self.send_bytes(content,kind,206,filename=filename,headers={
                'Accept-Ranges':'bytes','Content-Range':f'bytes {start}-{start+len(content)-1}/{size}'})
        self.send_bytes(path.read_bytes(),kind,filename=filename)

    def post(self, path, query):
        if path == '/api/backups/inspect':
            if len(self._body)>2*1024**3:raise ValidationError('Backup upload limit is 2 GB.')
            token=uid()
            saved=self.app.store.home/'tmp'/('backup-'+token+'.zip')
            saved.write_bytes(self._body)
            try:
                catalog=self.app.backups.catalog(saved)
            except Exception:
                saved.unlink(missing_ok=True)
                raise
            return self.respond({'token':token,'objects':catalog['objects'],
                                 'includesRenders':catalog['includesRenders'],'createdAt':catalog['createdAt']})
        if path == '/api/backups/import-selected':
            data=self.data()
            token=str(data.get('token') or '')
            if not re.fullmatch(r'[-a-f0-9]{36}',token):raise ValidationError('Choose a backup first.')
            saved=self.app.store.home/'tmp'/('backup-'+token+'.zip')
            if not saved.is_file():raise FileNotFoundError('That staged backup is missing.')
            def run(update,cancel):
                try:return self.app.backups.import_selected(saved,data.get('selected'),data.get('replace'),update,cancel)
                finally:saved.unlink(missing_ok=True)
            return self.respond(self.app.jobs.start('Import from Backup',run))
        if path == '/api/backups/export':
            data=self.data()
            include=data.get('includeRenders') is True
            return self.respond(self.app.jobs.start('Export workspace backup',
                lambda update,cancel:self.app.backups.export(update,cancel,include_renders=include)))
        match = re.fullmatch(r'/api/decks/([-a-f0-9]{36})/delete', path)
        if match:
            data = self.data()
            return self.respond(self.app.store.purge('decks', match[1], data.get('revision')))
        return super().post(path, query)

    def get(self, path, query):
        if path == '/api/backups/estimate':
            stats=self.app.store.stats()
            base=max(0,stats['assetBytes']-stats['renderBytes'])
            return self.respond({'withoutRenders':base+1024*1024,
                                 'withRenders':stats['assetBytes']+1024*1024})
        if path == '/api/bootstrap':
            self.respond({'version':'2.0.0','browser':True,'pipelineVersion':server.PIPELINE_VERSION,
                          'csrf':self.app.csrf,'runtimeOrigin':self.app.runtime_origin,
                          'groups':server.GROUP_LABELS,'settings':self.app.ws.global_settings(),
                          'stats':self.app.store.stats(),'backs':self.app.ws.backs.catalog()})
            return
        return super().get(path, query)


def create_app(home, transport, origin):
    server.Jobs = BrowserJobs
    store = Store(Path(home))
    app = server.App(store, Network(store, transport=transport))
    app.origin = origin
    app.runtime_origin = origin
    app.runtime.parent_origin = origin
    return app


def request(app, method, url, body=b'', headers=None):
    parsed = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(parsed.path)
    query = urllib.parse.parse_qs(parsed.query)
    handler = BrowserHandler(app, method, url, body, headers or {})
    try:
        if path.startswith(('/runtime/', '/js/', '/img/', '/fonts/', '/css/', '/creator/')):
            handler.runtime_get(path, query)
        elif method == 'POST':
            handler.post(path, query)
        else:
            handler.get(path, query)
    except ConflictError as exc:
        handler.respond({'error': str(exc)}, 409)
    except PermissionError as exc:
        handler.respond({'error': str(exc)}, 403)
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        handler.respond({'error': str(exc)}, 400)
    except FileNotFoundError as exc:
        handler.respond({'error': str(exc)}, 404)
    except Exception as exc:
        app.log.exception('Browser request failed: %s', path)
        handler.respond({'error': str(exc)}, 500)
    return handler.response
