"""Loopback-only application and isolated CardConjurer runtime HTTP servers."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import logging
import mimetypes
import re
import secrets
import socket
import threading
import time
import traceback
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .backup import Backups
from .compiler import BUILTINS
from .domain import ValidationError, ConflictError, uid, slug, GROUP_LABELS
from .images import ingest_image, rarity_variants, sanitize_svg
from .jobs import Jobs
from .orders import Orders
from .runtime import Runtime
from .storage import Store
from .tools import CardTools
from .workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 64 * 1024 ** 2


class App:
    def __init__(self, store=None, network=None):
        self.store = store or Store()
        self.ws = Workspace(self.store, network)
        self.jobs = Jobs(self.store)
        self.orders = Orders(self.ws)
        self.tools = CardTools(self.ws)
        self.runtime = Runtime(self.ws.net)
        self.backups = Backups(self.ws)
        self.csrf = secrets.token_urlsafe(32)
        self.render_sessions = {}
        self.transfers = {}
        self.lock = threading.RLock()
        self.runtime_origin = ''
        self.origin = ''
        self.runtime_assets = set()
        self.log = logging.getLogger('proxy-foundry-' + uid())
        self.log.setLevel(logging.INFO)
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(self.store.home / 'logs' / 'app.log', maxBytes=2 * 1024 ** 2, backupCount=2, encoding='utf-8')
        self.log.addHandler(handler)

    def start_render_session(self, ids):
        plan = self.ws.render_targets(ids)
        ident = uid()
        now = time.time()
        targets = {x['key']: x for x in plan['targets']}
        with self.lock:
            self.render_sessions = {k: v for k, v in self.render_sessions.items() if now - v['created'] < 7200}
            self.render_sessions[ident] = {'targets': targets, 'created': now}
            for t in targets.values():
                from .backup import referenced_assets
                self.runtime_assets.update(referenced_assets(t['data']))
        return {'id': ident, 'targets': [{'key': t['key'], 'name': t['name']} for t in targets.values()],
                'cached': plan['cached'], 'errors': plan.get('errors', [])}

    def target(self, session, key):
        with self.lock:
            s = self.render_sessions.get(session)
            if not s or time.time() - s['created'] > 7200:
                raise ValidationError('Render session expired. Start rendering again; completed images are saved.')
            t = s['targets'].get(key)
            if not t: raise ValidationError('This image is not part of the render session.')
            return t

    def transfer(self, order_id):
        d = self.store.get('orders', order_id)
        p = self.store.home / 'orders' / (order_id + '.zip')
        if not d or not p.is_file(): raise ValidationError('This saved order package is missing. Build it again.')
        ident, secret = uid(), secrets.token_urlsafe(32)
        with self.lock:
            now = time.time()
            self.transfers = {k: v for k, v in self.transfers.items() if v['expires'] > now}
            self.transfers[ident] = {'secret': secret, 'expires': now + 3600, 'order': order_id,
                                    'path': p, 'count': d['count'], 'zipBytes': p.stat().st_size}
        return {'id': ident, 'secret': secret, 'origin': self.origin}

    def authorized_transfer(self, ident, secret):
        with self.lock:
            t = self.transfers.get(ident)
            if not t or t['expires'] < time.time() or not secrets.compare_digest(str(secret or ''), t['secret']):
                raise PermissionError('Print transfer expired or is not authorized. Open the order again from Proxy Foundry.')
            return dict(t)

    def order(self, ident):
        d = self.store.get('orders', ident)
        if not d: raise ValidationError('Order not found.')
        p = self.store.home / 'orders' / (ident + '.zip')
        return {**d, 'zipBytes': p.stat().st_size if p.is_file() else 0,
                'download': '/api/orders/' + ident + '/download'}

    def diagnostic_zip(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('diagnostics.json', json.dumps({'version': '1.2.0', 'runtime': self.runtime.diagnostic(),
                'workspace': {k: v for k, v in self.store.stats().items() if k != 'home'}}, indent=2))
            for p in (self.store.home / 'logs').glob('*.log'):
                z.writestr(p.name, p.read_text(encoding='utf-8', errors='replace')[-150000:])
            for p in sorted((self.store.home / 'logs').glob('job-*.json'), key=lambda p: p.stat().st_mtime)[-8:]:
                job = json.loads(p.read_text())
                job.pop('result', None)
                z.writestr(p.name, json.dumps(job, ensure_ascii=False))
        return b.getvalue()

    def close(self):
        self.jobs.close()
        for h in list(self.log.handlers): h.close(); self.log.removeHandler(h)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, app, port=0, *, runtime=False):
        self.app = app
        self.is_runtime = runtime
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)
        self.runtime_server = None
        if not runtime:
            app.origin = self.origin
            self.runtime_server = LocalServer(app, 0, runtime=True)
            app.runtime_origin = self.runtime_server.origin
            app.runtime.parent_origin = self.origin
            threading.Thread(target=self.runtime_server.serve_forever, name='cardconjurer-http', daemon=True).start()

    def server_close(self):
        if self.runtime_server:
            self.runtime_server.shutdown(); self.runtime_server.server_close(); self.runtime_server = None
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'ProxyFoundry/1.2'
    protocol_version = 'HTTP/1.1'

    @property
    def app(self): return self.server.app

    def log_message(self, fmt, *args):
        # Never log query-string transfer credentials or uploaded bodies.
        if args and isinstance(args[0], str): args = (args[0].split('?')[0],) + args[1:]
        self.app.log.info(fmt, *args)

    def send_bytes(self, content, mime='application/json', status=200, *, filename=None, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if filename: self.send_header('Content-Disposition', 'attachment; filename="' + re.sub(r'[^A-Za-z0-9_. -]', '_', filename) + '"')
        for k, v in (headers or {}).items(): self.send_header(k, str(v))
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(content)

    def respond(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str).encode(), status=status)

    def file(self, path, mime=None, filename=None, *, allow_range=False):
        path = Path(path)
        if not path.is_file(): raise FileNotFoundError('The saved file is missing.')
        size = path.stat().st_size
        start, end, status = 0, max(0, size - 1), 200
        if allow_range and self.headers.get('Range'):
            m = re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers['Range'])
            if not m: raise ValidationError('Invalid download range.')
            start, end = int(m[1]), min(int(m[2]), size - 1)
            if start >= size or end < start or end - start >= 2 * 1024 ** 2:
                raise ValidationError('Download range is outside the saved order or is too large.')
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', mime or mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(end - start + 1 if size else 0))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if allow_range: self.send_header('Accept-Ranges', 'bytes')
        if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if filename: self.send_header('Content-Disposition', 'attachment; filename="' + re.sub(r'[^A-Za-z0-9_. -]', '_', filename) + '"')
        self.end_headers()
        if self.command == 'HEAD': return
        remaining = end - start + 1 if size else 0
        with path.open('rb') as stream:
            stream.seek(start)
            while remaining > 0:
                chunk = stream.read(min(1024 ** 2, remaining))
                if not chunk: break
                self.wfile.write(chunk); remaining -= len(chunk)

    def guard(self, mutating=False):
        host = self.headers.get('Host', '')
        if host != '127.0.0.1:' + str(self.server.server_port):
            raise PermissionError('Use the exact local address opened by the launcher.')
        origin = self.headers.get('Origin')
        if mutating:
            if self.server.is_runtime: raise PermissionError('The renderer cannot change your workspace.')
            if origin and origin != self.server.origin: raise PermissionError('Cross-site changes are not allowed.')
            if not secrets.compare_digest(self.headers.get('X-Proxy-CSRF', ''), self.app.csrf):
                raise PermissionError('This page is from an earlier app session. Reload it before saving.')
        elif not self.path.startswith('/api/transfer/'):
            if origin and origin not in {self.server.origin, self.app.origin}:
                raise PermissionError('Cross-site access is not allowed.')
            if not self.server.is_runtime and self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise PermissionError('Cross-site access is not allowed.')

    def body(self, limit=MAX_BODY):
        if self.headers.get('Transfer-Encoding'): raise ValidationError('Chunked requests are not supported.')
        try: size = int(self.headers.get('Content-Length', '0'))
        except ValueError as e: raise ValidationError('Invalid upload size.') from e
        if size < 0 or size > limit: raise ValidationError(f'Upload limit is {limit // (1024 ** 2)} MB.')
        self.connection.settimeout(90)
        raw = self.rfile.read(size)
        if len(raw) != size: raise ValidationError('The upload was interrupted. Nothing was saved.')
        return raw

    def data(self):
        try: d = json.loads(self.body())
        except (ValueError, UnicodeDecodeError) as e: raise ValidationError('Invalid JSON request.') from e
        if not isinstance(d, dict): raise ValidationError('Expected a JSON object.')
        return d

    def do_OPTIONS(self):
        self.send_bytes(b'', 'text/plain', 403)

    def do_HEAD(self): self.do_GET()

    def do_GET(self): self.dispatch(False)
    def do_POST(self): self.dispatch(True)

    def dispatch(self, mutating):
        try:
            self.guard(mutating)
            u = urllib.parse.urlsplit(self.path)
            p = urllib.parse.unquote(u.path)
            q = urllib.parse.parse_qs(u.query)
            if self.server.is_runtime: return self.runtime_get(p, q)
            if mutating: return self.post(p, q)
            return self.get(p, q)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True
        except ConflictError as e: self.respond({'error': str(e)}, 409)
        except PermissionError as e: self.respond({'error': str(e)}, 403)
        except (ValidationError, ValueError, KeyError, TypeError) as e:
            self.app.log.warning('Validation %s: %s', self.path.split('?')[0], str(e))
            self.respond({'error': str(e)}, 400)
        except FileNotFoundError as e: self.respond({'error': str(e)}, 404)
        except Exception:
            self.app.log.exception('Request failed: %s', self.path.split('?')[0])
            self.respond({'error': 'The operation failed. Your saved decks are unchanged. See Settings → Diagnostics for the error log.'}, 500)

    def get(self, p, q):
        if p in ('/', '/index.html'):
            html = (ROOT / 'site/index.html').read_bytes()
            return self.send_bytes(html, 'text/html; charset=utf-8', headers={'Content-Security-Policy':
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://cards.scryfall.io; connect-src 'self'; frame-src " + self.app.runtime_origin + "; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
        if p.startswith('/site/'):
            name = p[6:]
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:css|js|svg|json)', name): raise FileNotFoundError('UI file not found.')
            return self.file(ROOT / 'site' / name)
        if p == '/api/bootstrap':
            return self.respond({'version': '1.2.0', 'csrf': self.app.csrf, 'runtimeOrigin': self.app.runtime_origin,
                                 'groups': GROUP_LABELS, 'settings': self.app.ws.global_settings(), 'stats': self.app.store.stats()})
        if p == '/api/decks': return self.respond(self.app.ws.list_decks())
        if p == '/api/templates': return self.respond(self.app.ws.templates())
        if p == '/api/templates/seed': return self.respond(self.app.ws.template_seed(q.get('kind', ['normal'])[0]))
        if p == '/api/settings': return self.respond(self.app.ws.global_settings())
        if p == '/api/stats': return self.respond(self.app.store.stats())
        if p == '/api/trash': return self.respond(self.app.store.list('decks', deleted=True))
        if p == '/api/orders':
            return self.respond([{k: v for k, v in self.app.order(x['id']).items() if k != 'cards'} for x in self.app.store.list('orders')])
        if p == '/api/diagnostics': return self.send_bytes(self.app.diagnostic_zip(), 'application/zip', filename='ProxyFoundry_Diagnostics.zip')
        if p == '/api/helper/download':
            b = io.BytesIO()
            with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in (ROOT / 'extension').iterdir():
                    if file.is_file() and file.suffix in {'.json', '.js', '.txt', '.md'}: z.write(file, 'extension/' + file.name)
            return self.send_bytes(b.getvalue(), 'application/zip', filename='ProxyFoundry_Print_Helper.zip')
        if m := re.fullmatch(r'/api/decks/([-a-f0-9]{36})', p): return self.respond(self.app.ws.deck(m[1]))
        if m := re.fullmatch(r'/api/jobs/([-a-f0-9]{36})', p): return self.respond(self.app.jobs.get(m[1]))
        if m := re.fullmatch(r'/api/assets/([0-9a-f]{64})', p):
            a = self.app.store.asset(m[1])
            if not a or not a['mime'].startswith('image/'): raise FileNotFoundError('Image not found.')
            return self.file(self.app.store.asset_path(m[1]), a['mime'])
        if m := re.fullmatch(r'/api/render-sessions/([-a-f0-9]{36})/([a-f0-9]{64})', p):
            return self.respond(self.app.target(m[1], m[2]))
        if m := re.fullmatch(r'/api/orders/([-a-f0-9]{36})', p): return self.respond(self.app.order(m[1]))
        if m := re.fullmatch(r'/api/orders/([-a-f0-9]{36})/download', p):
            self.app.order(m[1]); return self.file(self.app.store.home / 'orders' / (m[1] + '.zip'), 'application/zip', 'ProxyFoundry_Order_' + m[1][:8] + '.zip')
        if m := re.fullmatch(r'/api/(files|backups)/([A-Za-z0-9_.-]+\.zip)', p):
            return self.file(self.app.store.home / ('orders' if m[1] == 'files' else 'backups') / m[2], 'application/zip', m[2])
        if m := re.fullmatch(r'/api/transfer/([-a-f0-9]{36})/(metadata|zip)', p):
            t = self.app.authorized_transfer(m[1], self.headers.get('X-Proxy-Transfer-Token'))
            if m[2] == 'metadata': return self.respond({'count': t['count'], 'zipBytes': t['zipBytes'], 'filename': 'ProxyFoundry_Order.zip'})
            return self.file(t['path'], 'application/zip', allow_range=True)
        raise FileNotFoundError('That page or API endpoint does not exist.')

    def post(self, p, q):
        if p == '/api/uploads':
            raw = self.body(); a = ingest_image(self.app.store, raw)
            name = urllib.parse.unquote(self.headers.get('X-Filename', 'image.png'))
            a.update(filename=Path(name).name, stem=slug(Path(name).stem))
            return self.respond(a)
        if m := re.fullmatch(r'/api/render-sessions/([-a-f0-9]{36})/([a-f0-9]{64})', p):
            t = self.app.target(m[1], m[2]); d = t['data']
            size = [round(d['width'] * (1 + 2 * d.get('marginX', 0))), round(d['height'] * (1 + 2 * d.get('marginY', 0)))]
            return self.respond(self.app.ws.save_render(m[2], self.body(), size))
        if p == '/api/backups/import':
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 2 * 1024 ** 3: raise ValidationError('Backup upload limit is 2 GB.')
            path = self.app.store.home / 'tmp' / ('restore-' + uid() + '.zip')
            remaining = size; self.connection.settimeout(120)
            try:
                with path.open('wb') as out:
                    while remaining:
                        chunk = self.rfile.read(min(1024 ** 2, remaining))
                        if not chunk: raise ValidationError('Backup upload was interrupted.')
                        out.write(chunk); remaining -= len(chunk)
            except Exception: path.unlink(missing_ok=True); raise
            def restore(update, cancel):
                try: return self.app.backups.restore(path, q.get('defaults', ['false'])[0] == 'true', update, cancel)
                finally: path.unlink(missing_ok=True)
            return self.respond(self.app.jobs.start('Restore workspace backup', restore))
        d = self.data()
        if p == '/api/decks/import': return self.respond(self.app.jobs.start('Import deck', lambda u, c: self.app.ws.create(d, u, c)))
        if p == '/api/decks/new': return self.respond(self.app.ws.new_deck(d.get('name', 'Untitled deck')))
        if p == '/api/settings': return self.respond(self.app.ws.set_global_settings(d))
        if p == '/api/templates': return self.respond(self.app.ws.save_template(d))
        if p == '/api/symbols/generate': return self.respond(rarity_variants(self.app.store, d['assetId']))
        if p == '/api/svg/validate':
            raw = base64.b64decode(d.get('base64', ''), validate=True)
            return self.respond({'svg': sanitize_svg(raw).decode('utf-8')})
        if p == '/api/render-sessions': return self.respond(self.app.start_render_session(d.get('deckIds', [])))
        if p == '/api/runtime/prepare': return self.respond(self.app.jobs.start('Load CardConjurer', self.app.runtime.prepare))
        if p == '/api/orders/plan':
            plan = self.app.orders.plan(d.get('deckIds', []))
            for card in plan['cards']:
                card['frontUrl'] = '/api/assets/' + card['frontAsset']; card['backUrl'] = '/api/assets/' + card['backAsset']
            return self.respond(plan)
        if p == '/api/orders/build':
            return self.respond(self.app.jobs.start('Package paired order', lambda u, c: self.app.orders.build(d.get('deckIds', []), bool(d.get('acknowledge')), u, c)))
        if p == '/api/backups/export': return self.respond(self.app.jobs.start('Back up workspace', self.app.backups.export))
        if p == '/api/printings': return self.respond(self.app.ws.sources.printings(d['name'], bool(d.get('refresh')), d.get('nextPage')))
        if p == '/api/tools/copy-tokens': return self.send_bytes(self.app.tools.copy_tokens(d), 'application/json', filename='Copy_Tokens.cardconjurer')
        if p == '/api/tools/originals': return self.respond(self.app.jobs.start('Download original card images', lambda u, c: self.app.tools.originals(d, u, c)))
        if p == '/api/cardconjurer/export': return self.send_bytes(self.app.ws.export_cc(d.get('deckIds', [])), 'application/json', filename='ProxyFoundry_Cards.cardconjurer')
        if p == '/api/client-error':
            self.app.log.error('Browser: %s', str(d.get('error', ''))[:8000]); return self.respond({'ok': True})
        if m := re.fullmatch(r'/api/jobs/([-a-f0-9]{36})/cancel', p): return self.respond(self.app.jobs.cancel(m[1]))
        if m := re.fullmatch(r'/api/orders/([-a-f0-9]{36})/transfer', p): return self.respond(self.app.transfer(m[1]))
        if m := re.fullmatch(r'/api/templates/([-a-f0-9]{36})/delete', p): return self.respond(self.app.ws.delete_template(m[1], d.get('revision')))
        if m := re.fullmatch(r'/api/decks/([-a-f0-9]{36})/(save|prepare|add|duplicate|delete|restore|originals)', p):
            ident, action = m[1], m[2]
            if action == 'save': return self.respond(self.app.ws.save(ident, d))
            if action == 'prepare': return self.respond(self.app.jobs.start('Prepare deck', lambda u, c: self.app.ws.prepare(ident, u, c)))
            if action == 'add': return self.respond(self.app.jobs.start('Add cards', lambda u, c: self.app.ws.add_cards(ident, d, u, c)))
            if action == 'duplicate': return self.respond(self.app.ws.duplicate(ident))
            if action in {'delete', 'restore'}: return self.respond(self.app.store.trash('decks', ident, d.get('revision'), restore=action == 'restore'))
            if action == 'originals': return self.respond(self.app.jobs.start('Download original images', lambda u, c: self.app.ws.original_images(ident, u, c)))
        if m := re.fullmatch(r'/api/decks/([-a-f0-9]{36})/cards/([-a-f0-9]{36})(?:/(printing|token))?', p):
            if m[3] == 'printing': return self.respond(self.app.ws.replace_printing(m[1], m[2], d['source'], d['revision']))
            if m[3] == 'token': return self.respond(self.app.ws.copy_token(m[1], m[2], d.get('spec', {}), d['revision']))
            return self.respond(self.app.ws.mutate_card(m[1], m[2], d))
        raise FileNotFoundError('That API action does not exist.')

    def runtime_get(self, p, q):
        if p == '/runtime/host':
            return self.send_bytes(self.app.runtime.host(), 'text/html; charset=utf-8', headers={'Content-Security-Policy':
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors " + self.app.origin})
        if p == '/runtime/fonts.css': return self.send_bytes(self.app.runtime.fonts_css(), 'text/css')
        if p in ('/site/runtime-hooks.js', '/site/runtime-bridge.js'):
            return self.file(ROOT / p.lstrip('/'), 'application/javascript')
        if m := re.fullmatch(r'/api/assets/([a-f0-9]{64})', p):
            if m[1] not in self.app.runtime_assets: raise PermissionError('That image is not part of an active render session.')
            a = self.app.store.asset(m[1])
            if not a or not a['mime'].startswith('image/'): raise FileNotFoundError('Runtime image missing.')
            return self.file(self.app.store.asset_path(m[1]), a['mime'])
        if p == '/runtime/remote':
            url = q.get('url', [''])[0]
            alias = self.app.runtime.upstream_alias(url)
            if alias:
                raw, mime = self.app.runtime.fetch(alias)
                return self.send_bytes(raw, mime)
            raw, mime, _ = self.app.ws.net.fetch(url)
            if mime == 'image/svg+xml': raw = sanitize_svg(raw)
            elif not mime.startswith('image/'):
                # Raw GitHub often uses application/octet-stream for PNG files.
                from .images import decode_image
                decode_image(raw); mime = 'image/png'
            return self.send_bytes(raw, mime)
        if p.startswith(('/js/', '/img/', '/fonts/', '/css/', '/creator/')):
            raw, mime = self.app.runtime.fetch(p); return self.send_bytes(raw, mime)
        raise FileNotFoundError('The renderer has no access to that endpoint.')
