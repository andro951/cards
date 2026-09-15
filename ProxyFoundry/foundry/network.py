"""Read-through cache and bounded, rate-limited network operations."""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .domain import ValidationError, cache_is_fresh, STATION_SCRIPT_URL
from .storage import Store

MAX_REMOTE_BYTES = 64 * 1024 * 1024
ALLOWED_HOSTS = {'api.scryfall.com', 'scryfall.com', 'raw.githubusercontent.com', 'api.github.com',
                 'cards.scryfall.io', 'c1.scryfall.com', 'c2.scryfall.com', 'c3.scryfall.com', 'c4.scryfall.com'}


def validate_remote_url(url: str) -> str:
    p = urllib.parse.urlsplit(str(url))
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValidationError('Only HTTPS public artwork/data URLs are accepted.')
    host = (p.hostname or '').lower()
    if host not in ALLOWED_HOSTS and str(url) != STATION_SCRIPT_URL:
        raise ValidationError(f'Unsupported asset host {host!r}. Use a GitHub folder or upload a computer folder.')
    if '\\' in p.path or any(x == '..' for x in urllib.parse.unquote(p.path).split('/')):
        raise ValidationError('Unsafe remote path.')
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_remote_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Network:
    def __init__(self, store: Store, *, transport: Callable | None = None,
                 clock: Callable[[], float] = time.time, sleeper: Callable[[float], None] = time.sleep):
        self.store = store
        self.clock, self.sleep = clock, sleeper
        self.transport = transport or self._transport
        self._lock = threading.Lock()
        self._last_scryfall = 0.0
        self._url_locks: dict[str, threading.Lock] = {}
        self.hits = 0; self.misses = 0

    def _transport(self, url: str) -> tuple[bytes, str, dict[str, Any]]:
        headers = {'User-Agent': 'ProxyFoundry/1.0 (local deck artwork workspace)',
                   'Accept': 'application/json;q=0.9,image/*;q=0.8,*/*;q=0.7'}
        if urllib.parse.urlsplit(url).hostname == 'api.github.com' and os.environ.get('GITHUB_TOKEN'):
            headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
        req = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener(SafeRedirect)
        for attempt in range(2):
            try:
                with opener.open(req, timeout=25) as response:
                    size = response.headers.get('Content-Length')
                    if size and int(size) > MAX_REMOTE_BYTES:
                        raise ValidationError('An individual asset exceeded the 64 MB download limit.')
                    body = response.read(MAX_REMOTE_BYTES + 1)
                    if len(body) > MAX_REMOTE_BYTES:
                        raise ValidationError('An individual asset exceeded the 64 MB download limit.')
                    return body, response.headers.get_content_type(), dict(response.headers)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 503) and attempt == 0:
                    try: delay = max(1., min(120., float(exc.headers.get('Retry-After', '10'))))
                    except ValueError: delay = 10.
                    self.sleep(delay); continue
                detail = f'HTTP {exc.code}'
                try:
                    parsed = json.loads(exc.read(4096))
                    detail += ': ' + str(parsed.get('details') or parsed.get('message') or '')
                except Exception: pass
                if exc.code == 404: detail += ' — the file or public deck was not found.'
                raise ValidationError(f'{detail}\n{url}') from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise ValidationError(f'Could not fetch {url}: {exc}') from exc
        raise ValidationError('Network request failed.')

    def fetch(self, url: str, *, refresh: bool = False, immutable: bool = False,
              ttl: float | None = None) -> tuple[bytes, str, dict[str, Any]]:
        url = validate_remote_url(url)
        with self._lock:
            lock = self._url_locks.setdefault(url, threading.Lock())
        with lock:
            old = self.store.cache_get(url)
            now = self.clock()
            fresh = old is not None and (immutable or (max(0, now - old['fetched']) < ttl if ttl is not None
                                                        else cache_is_fresh(old['fetched'], now, refresh)))
            if fresh:
                self.hits += 1
                return self.store.asset_path(old['asset_id']).read_bytes(), old['mime'], {'cache': True, 'fetchedAt': old['fetched']}
            if urllib.parse.urlsplit(url).hostname == 'api.scryfall.com':
                with self._lock:
                    remaining = .12 - (time.monotonic() - self._last_scryfall)
                    if remaining > 0: self.sleep(remaining)
                    self._last_scryfall = time.monotonic()
            body, mime, headers = self.transport(url)
            if not body:
                raise ValidationError('The server returned an empty file: ' + url)
            if 'json' in mime or urllib.parse.urlsplit(url).hostname == 'api.scryfall.com':
                try: value = json.loads(body)
                except (ValueError, UnicodeDecodeError) as exc: raise ValidationError('The server returned invalid JSON: ' + url) from exc
                if isinstance(value, dict) and value.get('object') == 'error':
                    raise ValidationError(str(value.get('details') or 'Scryfall rejected this request.'))
            asset = self.store.add_asset(body, mime)
            self.store.cache_put(url, asset, now, headers)
            self.misses += 1
            return body, mime, {'cache': False, 'fetchedAt': now}

    def json(self, url: str, *, refresh: bool = False, ttl: float | None = None) -> Any:
        raw, _, _ = self.fetch(url, refresh=refresh, ttl=ttl)
        try: return json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc: raise ValidationError('Invalid JSON response from ' + url) from exc
