"""Read-through cache and bounded, rate-limited network operations."""
from __future__ import annotations

from .timing import timed, timing
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .domain import ValidationError, cache_is_fresh
from .storage import Store

MAX_REMOTE_BYTES = 64 * 1024 * 1024

class PendingDownload(BaseException):
    """Suspend a replayable browser GET without holding the Python request lane."""
    def __init__(self,urls):self.urls=list(dict.fromkeys(urls))
ALLOWED_HOSTS = {'api.scryfall.com', 'scryfall.com', 'raw.githubusercontent.com', 'api.github.com',
                 'cards.scryfall.io', 'c1.scryfall.com', 'c2.scryfall.com', 'c3.scryfall.com', 'c4.scryfall.com',
                 'archidekt.com', 'www.archidekt.com', 'mtggoldfish.com', 'www.mtggoldfish.com'}


def validate_remote_url(url: str) -> str:
    p = urllib.parse.urlsplit(str(url))
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValidationError('Only HTTPS public artwork/data URLs are accepted.')
    host = (p.hostname or '').lower()
    if host not in ALLOWED_HOSTS:
        raise ValidationError(f'Unsupported asset host {host!r}. Use a GitHub folder or upload a computer folder.')
    if '\\' in p.path or any(x == '..' for x in urllib.parse.unquote(p.path).split('/')):
        raise ValidationError('Unsafe remote path.')
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_remote_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Network:
    @contextmanager
    def freshness_scope(self,ident):
        if ident is not None and (not isinstance(ident,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',ident)):
            raise ValidationError('Invalid generation check scope.')
        previous=getattr(self._freshness_local,'ident',None)
        self._freshness_local.ident=ident
        try:yield
        finally:self._freshness_local.ident=previous

    def scoped_steps(self,ident,steps):
        try:
            while True:
                with self.freshness_scope(ident):
                    try:wait=next(steps)
                    except StopIteration as done:return done.value
                yield wait
        finally:steps.close()

    def fresh_json(self,url):
        ident=getattr(getattr(self,'_freshness_local',None),'ident',None)
        if not ident:return self.json(url,ttl=0)
        #Only retain recent operations, never replace the next Generate's live check with a TTL.
        with self._lock:
            scopes=self._freshness_cache
            if ident not in scopes:
                if len(scopes)>=8:scopes.pop(next(iter(scopes)))
                scopes[ident]={'values':{},'locks':{}}
            values=scopes[ident]['values']
            lock=scopes[ident]['locks'].setdefault(url,threading.Lock())
        with lock:
            if url not in values:values[url]=self.json(url,ttl=0)
            return values[url]

    @contextmanager
    def deferred_downloads(self):
        previous=getattr(self,'_deferred_downloads',False)
        self._deferred_downloads=True
        try:yield
        finally:self._deferred_downloads=previous

    def register_downloads(self,rows):
        errors=getattr(self,'_deferred_errors',{})
        good=[]
        for row in rows:
            if row.get('error'):errors[row['url']]=(self.clock(),row['error'])
            else:errors.pop(row['url'],None);good.append(row)
        self._deferred_errors=errors
        if good:self.register_prefetch([row['url'] for row in good],good)

    def reset_failed_downloads(self):
        #Pinned 404s remain immutable; a new Generate may retry temporary network failures immediately.
        self._deferred_errors={url:row for url,row in getattr(self,'_deferred_errors',{}).items() if 'HTTP 404' in row[1]}

    def __init__(self, store: Store, *, transport: Callable | None = None,
                 clock: Callable[[], float] = time.time, sleeper: Callable[[float], None] = time.sleep):
        self.store = store
        self.clock, self.sleep = clock, sleeper
        self.transport = transport or self._transport
        self._lock = threading.Lock()
        self._freshness_local=threading.local();self._freshness_cache={}
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
                with timing(self.store,'network.attempt',url=url,attempt=attempt+1), opener.open(req, timeout=25) as response:
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
                    with timing(self.store,'network.retry-wait',url=url,status=exc.code,delay=delay):self.sleep(delay)
                    continue
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

    @timed('network.fetch')
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
            if fresh and self.store.asset(old['asset_id']):
                self.hits += 1
                return self.store.asset_path(old['asset_id']).read_bytes(), old['mime'], {'cache': True, 'fetchedAt': old['fetched']}
            if immutable and getattr(self,'_deferred_downloads',False):
                failed=getattr(self,'_deferred_errors',{}).get(url)
                if failed and ('HTTP 404' in failed[1] or now-failed[0]<30):raise ValidationError(failed[1])
                raise PendingDownload([url])
            if urllib.parse.urlsplit(url).hostname == 'api.scryfall.com':
                with self._lock:
                    remaining = .12 - (time.monotonic() - self._last_scryfall)
                    if remaining > 0:
                        with timing(self.store,'network.rate-wait',url=url,delay=remaining):self.sleep(remaining)
                    self._last_scryfall = time.monotonic()
            with timing(self.store,'network.download',url=url):body, mime, headers = self.transport(url)
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

    @timed('network.prefetch')
    def prefetch_immutable(self,urls):
        """Browser downloads land directly in the immutable asset cache, in bounded groups."""
        urls=list(dict.fromkeys(validate_remote_url(url) for url in urls))
        prefetch=getattr(self.transport,'prefetch',None)
        if not prefetch:return self.fetch_many_immutable(urls)
        if not urls:return
        if len(urls)>6:raise ValidationError('Artwork prefetch is limited to six files.')
        try:rows=prefetch(urls)
        except Exception as error:raise ValidationError('Artwork prefetch failed: '+str(error)) from error
        return self.register_prefetch(urls,rows)

    def register_prefetch(self,urls,rows):
        if not isinstance(rows,list) or len(rows)!=len(urls):raise ValidationError('Incomplete artwork prefetch.')
        now=self.clock()
        errors=[]
        for row in rows:
            if isinstance(row,dict) and row.get('error'):
                errors.append(str(row['error']));continue
            if not isinstance(row,dict) or not re.fullmatch('[a-f0-9]{64}',str(row.get('id',''))) or not isinstance(row.get('bytes'),int) or not 0<row['bytes']<=64*1024*1024:
                raise ValidationError('Invalid prefetched artwork.')
            if self.store.asset_path(row['id']).stat().st_size!=row['bytes']:raise ValidationError('Incomplete prefetched artwork.')
        with self.store.connect() as db:
            for row in rows:
                if row.get('error'):continue
                width,height=row.get('width'),row.get('height')
                if not (row.get('mime')=='image/png' and isinstance(width,int) and isinstance(height,int) and 0<width*height<=48000000):width=height=None
                db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?)',(row['id'],row.get('mime','application/octet-stream'),row['bytes'],width,height,now))
                if width and height:db.execute('UPDATE assets SET width=?,height=? WHERE id=? AND width IS NULL',(width,height,row['id']))
        for url,row in zip(urls,rows):
            if not row.get('error'):self.store.cache_put(url,row,now,{})
        self.misses+=len(rows)-len(errors)
        if errors:raise ValidationError('Artwork prefetch failed: '+errors[0])

    def fetch_many_immutable(self,urls):
        urls=list(dict.fromkeys(validate_remote_url(url) for url in urls))
        result={};missing=[]
        for url in urls:
            old=self.store.cache_get(url)
            if old and self.store.asset(old['asset_id']):result[url]=self.fetch(url,immutable=True)
            else:missing.append(url)
        if not missing:return result
        batch=getattr(self.transport,'fetch_many',None)
        if batch:
            received=batch(missing)
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(6,len(missing))) as pool:
                received=dict(zip(missing,pool.map(self.transport,missing)))
        # All downloads finish before any newly fetched response is committed.
        staged=Network(self.store,transport=lambda url:received[url])
        for url in missing:result[url]=staged.fetch(url,immutable=True)
        self.misses+=staged.misses
        return result

    @timed('network.transient')
    def fetch_transient(self, url: str) -> tuple[bytes, str, dict[str, Any]]:
        """Fetch a remote asset without adding it to the persistent workspace cache."""
        url = validate_remote_url(url)
        with timing(self.store,'network.download',url=url):body, mime, headers = self.transport(url)
        if not body:
            raise ValidationError('The server returned an empty file: ' + url)
        return body, mime, {'cache': False, 'transient': True}

    def json(self, url: str, *, refresh: bool = False, ttl: float | None = None, immutable: bool = False) -> Any:
        raw, _, _ = self.fetch(url, refresh=refresh, ttl=ttl, **({'immutable':True} if immutable else {}))
        try: return json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc: raise ValidationError('Invalid JSON response from ' + url) from exc
