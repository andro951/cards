"""Short-lived tasks with progress, cancellation, per-item errors and durable logs."""
import json,threading,time,traceback
from concurrent.futures import ThreadPoolExecutor
from .domain import uid,ValidationError
class Jobs:
    def __init__(self,store):self.store=store;self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='foundry');self.jobs={};self.lock=threading.Lock();self.condition=threading.Condition(self.lock)
    def start(self,kind,fn):
        ident=uid();job={'id':ident,'kind':kind,'state':'queued','done':0,'total':0,'message':'Queued','startedAt':time.time(),'cancelled':False,'events':[]}
        with self.lock:self.jobs[ident]=job
        def update(done,total,message):
            with self.lock:
                job.update(done=done,total=total,message=str(message))
                job['events'].append({'at':time.time(),'message':str(message),'done':done,'total':total})
                job['events']=job['events'][-200:]
        def cancelled():
            with self.condition:
                self.condition.wait_for(lambda:not job.get('paused') or job['cancelled'])
                return job['cancelled']
        def run():
            with self.lock:job['state']='running'
            try:
                result=fn(update,cancelled)
                with self.lock:job.update(state='done',result=result,message='Complete',finishedAt=time.time())
            except Exception as exc:
                with self.lock:job.update(state='cancelled' if job['cancelled'] else 'failed',error=str(exc),message=str(exc),finishedAt=time.time(),trace=traceback.format_exc())
            finally:
                (self.store.home/'logs'/('job-'+ident+'.json')).write_text(json.dumps(job,ensure_ascii=False,default=str),encoding='utf-8')
        self.pool.submit(run);return {'id':ident}
    def get(self,ident):
        with self.lock:
            if ident not in self.jobs:raise ValidationError('This job belongs to an earlier session. Completed images are still saved.')
            return dict(self.jobs[ident])
    def pause(self,ident):
        with self.lock:
            if ident in self.jobs:self.jobs[ident]['paused']=True
        return {'ok':True}
    def resume(self,ident):
        with self.condition:
            if ident in self.jobs:self.jobs[ident]['paused']=False
            self.condition.notify_all()
        return {'ok':True}
    def cancel(self,ident):
        with self.lock:
            if ident in self.jobs:self.jobs[ident]['cancelled']=True
            self.condition.notify_all()
        return {'ok':True}

    def close(self):
        with self.lock:
            for job in self.jobs.values():
                if job['state'] in {'running','queued'}: job['cancelled']=True
            self.condition.notify_all()
        self.pool.shutdown(wait=False, cancel_futures=True)
