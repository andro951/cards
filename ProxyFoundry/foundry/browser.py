"""In-browser adapter for the existing workspace API.

Pyodide runs this module in a dedicated Web Worker. No HTTP server is started.
"""
from __future__ import annotations

from .timing import timed
import json
import hashlib
import mimetypes
import re
import sqlite3
from contextlib import contextmanager,closing
import time
import traceback
import urllib.parse
from pathlib import Path
from types import GeneratorType

from .domain import ConflictError, ValidationError, uid
from .network import Network
from .github_setup import import_github_setup_steps,import_symbol_folder_steps
from .storage import Store
from . import server


def browser_error(exc):
    if isinstance(exc,OSError) and exc.errno==51:
        return 'Workspace storage is full. Completed images are saved. Free space or remove unused decks, or export a backup and move to a workspace folder, then retry.'
    return str(exc)


class BrowserHeaders(dict):
    """Fetch Headers are lowercase; the HTTP handler uses canonical names."""

    def __init__(self, headers):
        super().__init__((str(key).lower(), value) for key, value in headers.items())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


class BrowserStore(Store):
    """Persist a complete SQLite snapshot after each mutation, never after reads."""
    def __init__(self,home,persist=lambda path:None,copy_file=None):
        self.persist=persist
        self.copy_file=copy_file
        self._checkpoint_digest=None
        self._render_batch=False
        self._render_rollback=[]
        self._render_cleanup=[]
        super().__init__(home)

    def copy_render_file(self,source,destination):
        if self.copy_file is None:return super().copy_render_file(source,destination)
        self.copy_file(str(source),str(destination))

    def write_render_file(self,source,output,previous_source=None):
        if self.copy_file is None:super().write_render_file(source,output,previous_source)
        else:
            #The prior file must survive a reload before the new metadata checkpoint.
            if previous_source:
                original=output
                while output.exists():output=original.with_name(original.stem+' ('+uid()[:8]+')'+original.suffix)
                previous_source=None
            self.copy_render_file(source,output)
        if self._render_batch:
            self._render_rollback.append(lambda:self.copy_render_file(previous_source,output) if previous_source else output.unlink(missing_ok=True))
        return output

    def remove_render_file(self,path):
        if self._render_batch:self._render_cleanup.append(path)
        else:super().remove_render_file(path)

    def asset_written(self,ident,path):
        if not self._render_batch:return
        with closing(sqlite3.connect(self.home/'.render-save.sqlite3')) as previous:
            existed=previous.execute('SELECT 1 FROM assets WHERE id=?',(ident,)).fetchone()
        if not existed:self._render_rollback.append(lambda:self.remove_render_file(path))

    @contextmanager
    def render_save(self):
        if self._render_batch:raise RuntimeError('A render save is already active.')
        snapshot=self.home/'.render-save.sqlite3'
        with closing(sqlite3.connect(self.db_path)) as source, closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
        self._render_batch=True
        try:
            yield
            self._render_batch=False
            self.checkpoint()
        except BaseException:
            self._render_batch=False
            with closing(sqlite3.connect(snapshot)) as source, closing(sqlite3.connect(self.db_path)) as destination:
                source.backup(destination)
            for restore in reversed(self._render_rollback):
                try:restore()
                except Exception as error:
                    if getattr(self,'timing_logger',None):self.timing_logger.warning('Render file rollback failed: %s',error)
            self._checkpoint_digest=None
            #Retry the prior metadata state if persistence failed after accepting a write.
            try:self.checkpoint()
            except Exception as error:
                if getattr(self,'timing_logger',None):self.timing_logger.warning('Render rollback checkpoint failed: %s',error)
            raise
        else:
            for path in self._render_cleanup:
                try:super().remove_render_file(path)
                except Exception as error:
                    if getattr(self,'timing_logger',None):self.timing_logger.warning('Obsolete render file cleanup failed: %s',error)
        finally:
            self._render_batch=False
            self._render_rollback.clear();self._render_cleanup.clear()
            snapshot.unlink(missing_ok=True)

    @contextmanager
    def connect(self):
        changed=False
        with super().connect() as db:
            yield db
            changed=db.total_changes>0
        if changed:self.checkpoint()

    @timed('storage.checkpoint')
    def checkpoint(self):
        if self._render_batch:return
        hasher=hashlib.sha256(self.db_path.read_bytes())
        #Committed changes can still be in SQLite's WAL while a connection is open.
        wal=Path(str(self.db_path)+'-wal')
        if wal.is_file():hasher.update(wal.read_bytes())
        digest=hasher.digest()
        if digest==self._checkpoint_digest:return
        snapshot=self.home/'.checkpoint.sqlite3'
        try:
            with closing(sqlite3.connect(self.db_path)) as source, closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination)
            self.persist(str(snapshot))
            self._checkpoint_digest=digest
        finally:snapshot.unlink(missing_ok=True)


class BrowserJobs:
    """Queue Python work; the browser's separate control plane stays responsive."""
    def __init__(self, store, publish=lambda job:None, cancelled=lambda ident:False):
        self.store=store;self.jobs={};self.pending={}
        self.publish=publish;self.cancelled=cancelled

    def _publish(self,job):
        (self.store.home/'logs'/('job-'+job['id']+'.json')).write_text(
            json.dumps(job,ensure_ascii=False,default=str),encoding='utf-8')
        self.publish(dict(job))

    def start(self,kind,operation,*,priority=0):
        if priority not in {0,1}:raise ValueError('Use foreground or background job priority.')
        ident=uid()
        job={'id':ident,'kind':kind,'state':'queued','done':0,'total':0,
             'message':'Queued','events':[],'cancelled':False,'startedAt':time.time(),'priority':priority}
        self.jobs[ident]=job;self.pending[ident]=operation
        self._publish(job)
        return {'id':ident}

    def run_pending(self,limit=None):
        """Run bounded safe chunks; the worker yields to requests between calls."""
        steps=0
        while self.pending and (limit is None or steps<limit):
            #Cancelled tasks release their resources promptly; foreground chunks
            #take priority over background preparation. Equal priorities rotate.
            ident=min(self.pending,key=lambda key:(
                not (self.jobs[key]['cancelled'] or self.cancelled(key)),self.jobs[key]['priority']))
            self._step(ident);steps+=1
        return bool(self.pending)

    def _step(self,ident):
        operation=self.pending.pop(ident);job=self.jobs[ident]
        def cancel():
            job['cancelled']=job['cancelled'] or self.cancelled(ident)
            return job['cancelled']
        def update(done,total,message):
            job.update(done=done,total=total,message=str(message))
            job['events'].append({'at':time.time(),'done':done,'total':total,'message':str(message)})
            job['events']=job['events'][-200:]
            self._publish(job)
        try:
            if cancel():raise ValidationError('Task cancelled. Completed work is saved.')
            if job['state']=='queued':
                job.update(state='running',message='Starting');self._publish(job)
                operation=operation(update,cancel)
            result=operation
            if isinstance(operation,GeneratorType):
                try:
                    next(operation)
                except StopIteration as finished:
                    result=finished.value
                else:
                    if cancel():raise ValidationError('Task cancelled. Completed work is saved.')
                    #Reinsert at the end so other queued jobs also get a turn.
                    self.pending[ident]=operation
                    return
            if cancel():raise ValidationError('Task cancelled. Completed work is saved.')
            job.update(state='done',result=result,message='Complete')
        except Exception as exc:
            job.update(state='cancelled' if job['cancelled'] else 'failed',
                       error=browser_error(exc),message=browser_error(exc),trace=traceback.format_exc())
            if isinstance(operation,GeneratorType):
                try:operation.close()
                except Exception as cleanup_error:
                    job['error']+=' Cleanup failed: '+browser_error(cleanup_error)
                    job['message']=job['error']
                    job['trace']+='\n'+traceback.format_exc()
        finally:
            if ident not in self.pending:
                job['finishedAt']=time.time();self._publish(job);job.pop('result',None)
                completed=[key for key,row in self.jobs.items() if row['state'] in {'done','failed','cancelled'}]
                for key in completed[:-20]:self.jobs.pop(key)

    def get(self,ident):
        if ident not in self.jobs:
            saved=self.store.home/'logs'/('job-'+ident+'.json')
            if not saved.is_file():raise ValidationError('This task belongs to an earlier browser session. Completed images are saved.')
            job=json.loads(saved.read_text(encoding='utf-8'))
            if job['state'] in {'running','queued'}:
                job.update(state='failed',message='Task interrupted by browser reload. Completed work is saved.',error='Task interrupted by browser reload. Completed work is saved.')
            return job
        job=self.jobs[ident]
        if job['state']=='done' and 'result' not in job:
            return json.loads((self.store.home/'logs'/('job-'+ident+'.json')).read_text(encoding='utf-8'))
        return dict(job)

    def cancel(self,ident):
        if ident in self.jobs:self.jobs[ident]['cancelled']=True
        return {'ok':True}

    def close(self):
        for job in self.jobs.values():
            if job['state'] in {'running','queued'}:job['cancelled']=True


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
        if self.app.store.home in path.parents:
            self.send_bytes(b'',kind,filename=filename)
            self.response['file']=path.relative_to(self.app.store.home).as_posix()
        else:self.send_bytes(path.read_bytes(),kind,filename=filename)

    def post(self, path, query):
        if path in {'/api/setup/github-import','/api/setup/symbols/github'}:
            data=self.data()
            operation=import_github_setup_steps if path.endswith('github-import') else import_symbol_folder_steps
            return self.respond(self.app.jobs.start('Import GitHub setup' if path.endswith('github-import') else 'Import GitHub set symbols',
                lambda update,cancel:operation(self.app.ws,data,update,cancel)))
        if path == '/api/orders/build':
            data=self.data()
            return self.respond(self.app.jobs.start('Package paired order',
                lambda update,cancel:self.app.orders.build_steps(data.get('deckIds',[]),bool(data.get('acknowledge')),update,cancel)))
        export=re.fullmatch(r'/api/decks/([-a-f0-9]{36})/(originals|cropped-art|review-images)',path)
        if export:
            self.data()
            operation={'originals':self.app.ws.original_images_steps,'cropped-art':self.app.ws.cropped_art_steps,'review-images':self.app.ws.review_images_steps}[export[2]]
            return self.respond(self.app.jobs.start('Export deck images',
                lambda update,cancel:operation(export[1],update,cancel)))
        if path == '/api/decks/import':
            data=self.data()
            return self.respond(self.app.jobs.start('Import deck',
                lambda update,cancel:self.app.ws.create_steps(data,update,cancel)))
        add=re.fullmatch(r'/api/decks/([-a-f0-9]{36})/add',path)
        if add:
            data=self.data()
            return self.respond(self.app.jobs.start('Add cards',
                lambda update,cancel:self.app.ws.add_cards_steps(add[1],data,update,cancel)))
        if path == '/api/runtime/prepare':
            self.data()
            return self.respond(self.app.jobs.start('Load CardConjurer',self.app.runtime.prepare_steps,priority=1))
        prepare=re.fullmatch(r'/api/decks/([-a-f0-9]{36})/prepare',path)
        if prepare:
            self.data()
            return self.respond(self.app.jobs.start('Prepare deck',
                lambda update,cancel:self.app.prepare_deck_steps(prepare[1],update,cancel),priority=1))
        if path == '/api/cleanup/retry':
            for queue in self.app.store.list('cleanup'):
                queue.pop('error',None)
                self.app.store.put('cleanup',queue,queue['revision'])
            return self.respond({'ok':True})
        match=re.fullmatch(r'/api/orders/([-a-f0-9]{36})/delete',path)
        if match:
            data=self.data()
            result=self.app.store.begin_delete('orders',match[1],data.get('revision'))
            with self.app.lock:
                self.app.transfers={k:v for k,v in self.app.transfers.items() if v.get('order')!=match[1]}
            return self.respond(result)
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
                lambda update,cancel:self.app.backups.export_steps(update,cancel,include_renders=include)))
        match = re.fullmatch(r'/api/decks/([-a-f0-9]{36})/delete', path)
        if match:
            data = self.data()
            return self.respond(self.app.store.begin_delete('decks', match[1], data.get('revision')))
        return super().post(path, query)

    def get(self, path, query):
        match=re.fullmatch(r'/api/decks/([-a-f0-9]{36})/orders',path)
        if match:
            return self.respond(self.app.store.blocking_orders(match[1]))
        if path == '/api/backups/estimate':
            stats=self.app.store.stats()
            base=max(0,stats['assetBytes']-stats['renderBytes'])
            return self.respond({'withoutRenders':base+1024*1024,
                                 'withRenders':stats['assetBytes']+1024*1024})
        if path == '/api/bootstrap':
            with self.app.store.connect() as db:
                db.execute("INSERT OR IGNORE INTO meta VALUES ('workspace_id',?)",(uid(),))
                workspace_id=db.execute("SELECT value FROM meta WHERE key='workspace_id'").fetchone()[0]
            self.respond({'version':'2.0.0','browser':True,'pipelineVersion':server.PIPELINE_VERSION,
                          'workspaceId':workspace_id,'storageType':self.app.store.storage_type,
                          'csrf':self.app.csrf,'runtimeOrigin':self.app.runtime_origin,
                          'groups':server.GROUP_LABELS,'settings':self.app.ws.global_settings(),
                          'stats':self.app.store.stats(),'backs':self.app.ws.backs.catalog()})
            return
        return super().get(path, query)


def create_app(home, transport, origin, publish=lambda job:None, cancelled=lambda ident:False, persist=lambda path:None,storage_type='browser',copy_file=None):
    store = BrowserStore(Path(home),persist,copy_file)
    store.storage_type=storage_type
    app = server.App(store, Network(store, transport=transport),
                     jobs_factory=lambda store:BrowserJobs(store,publish,cancelled))
    app.origin = origin
    app.runtime_origin = origin
    app.runtime.parent_origin = origin
    return app


@timed('api.request')
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
    except OSError as exc:
        handler.respond({'error': browser_error(exc)}, 507 if exc.errno==51 else 500)
    except Exception as exc:
        app.log.exception('Browser request failed: %s', path)
        handler.respond({'error': str(exc)}, 500)
    return handler.response
