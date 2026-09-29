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
        self.headers = headers
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
        self.send_bytes(path.read_bytes(), mime or mimetypes.guess_type(path.name)[0]
                        or 'application/octet-stream', filename=filename)


def create_app(home, transport):
    server.Jobs = BrowserJobs
    store = Store(Path(home))
    app = server.App(store, Network(store, transport=transport))
    app.origin = '/'
    app.runtime_origin = '/'
    app.runtime.parent_origin = ''
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
