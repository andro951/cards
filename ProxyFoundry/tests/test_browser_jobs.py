"""Browser jobs publish durable progress without running inside start()."""
from foundry.browser import BrowserJobs
from foundry.storage import Store


def test_start_returns_before_operation_and_persists_progress(tmp_path):
    store=Store(tmp_path);events=[];calls=[]
    jobs=BrowserJobs(store,publish=lambda job:events.append(job.copy()))
    def operation(update,cancel):
        calls.append('work')
        for i in range(210):update(i,210,'Working')
        return {'saved':True}
    ident=jobs.start('Test',operation)['id']
    assert not calls and jobs.get(ident)['state']=='queued'
    jobs.run_pending()
    assert jobs.get(ident)['result']=={'saved':True}
    assert len(jobs.get(ident)['events'])==200
    assert events[0]['state']=='queued' and events[-1]['state']=='done'
    assert BrowserJobs(store).get(ident)['state']=='done'


def test_browser_control_plane_can_cancel_at_a_checkpoint(tmp_path):
    control={'cancelled':False};completed=[]
    jobs=BrowserJobs(Store(tmp_path),cancelled=lambda ident:control['cancelled'])
    def operation(update,cancel):
        completed.append('first');update(1,2,'First saved')
        control['cancelled']=True
        if cancel():raise ValueError('Cancelled after saving first')
        completed.append('second')
    ident=jobs.start('Cancelable',operation)['id'];jobs.run_pending()
    assert completed==['first']
    assert jobs.get(ident)['state']=='cancelled'
    assert 'first' in jobs.get(ident)['error']


def test_reload_reports_interrupted_job_and_keeps_saved_log(tmp_path):
    store=Store(tmp_path);jobs=BrowserJobs(store)
    ident=jobs.start('Interrupted',lambda update,cancel:None)['id']
    previous=BrowserJobs(store).get(ident)
    assert previous['state']=='failed' and 'interrupted' in previous['error']



def test_completed_jobs_release_memory_and_keep_durable_results(tmp_path):
    jobs=BrowserJobs(Store(tmp_path));ident=None
    for index in range(30):
        result=jobs.start('Bounded history',lambda update,cancel:{'saved':'result'})['id']
        ident=ident or result;jobs.run_pending()
    assert len(jobs.jobs)==20
    assert ident not in jobs.jobs and jobs.get(ident)['result']=={'saved':'result'}



def test_quota_failure_has_recovery_guidance_and_durable_job_result(tmp_path):
    from foundry.browser import browser_error
    assert 'Completed images are saved' in browser_error(OSError(51,'Full'))
    assert browser_error(OSError(5,'Other')).endswith('Other')
    store=Store(tmp_path/'workspace');jobs=BrowserJobs(store)
    def fail(update,cancel):raise OSError(51,'Full')
    ident=jobs.start('Quota recovery',fail)['id'];jobs.run_pending()
    saved=jobs.get(ident)
    assert saved['state']=='failed' and 'Workspace storage is full' in saved['error']
    assert 'workspace folder' in saved['message']
    assert BrowserJobs(store).get(ident)['error']==saved['error']


def test_resumable_jobs_yield_preserve_results_and_share_turns(tmp_path):
    store=Store(tmp_path);jobs=BrowserJobs(store);steps=[]
    def work(name):
        def operation(update,cancel):
            for index in range(2):
                steps.append((name,index));update(index+1,2,name)
                yield
            return {'name':name}
        return operation
    first=jobs.start('First',work('first'))['id']
    second=jobs.start('Second',work('second'))['id']
    assert jobs.run_pending(limit=1)
    assert steps==[('first',0)] and jobs.get(first)['state']=='running'
    assert 'result' not in jobs.get(first) and 'finishedAt' not in jobs.get(first)
    assert BrowserJobs(store).get(first)['state']=='failed'
    jobs.run_pending(limit=1)
    assert steps==[('first',0),('second',0)]
    assert not jobs.run_pending()
    assert jobs.get(first)['result']=={'name':'first'}
    assert jobs.get(second)['result']=={'name':'second'}
    assert steps==[('first',0),('second',0),('first',1),('second',1)]


def test_resumable_job_cancel_closes_generator_without_next_chunk(tmp_path):
    jobs=BrowserJobs(Store(tmp_path));steps=[]
    def operation(update,cancel):
        try:
            steps.append('saved');update(1,2,'Saved first')
            yield
            steps.append('incorrect second')
        finally:steps.append('closed')
    ident=jobs.start('Cancelable',operation)['id']
    jobs.run_pending(limit=1);jobs.cancel(ident)
    assert not jobs.run_pending(limit=1)
    assert steps==['saved','closed']
    assert jobs.get(ident)['state']=='cancelled' and jobs.get(ident)['done']==1


def test_resumable_job_failure_does_not_stop_next_job(tmp_path):
    jobs=BrowserJobs(Store(tmp_path))
    def operation(update,cancel):
        yield
        raise OSError(51,'Storage full')
    failed=jobs.start('Failure',operation)['id']
    succeeded=jobs.start('Unrelated',lambda update,cancel:{'ok':True})['id']
    jobs.run_pending()
    assert jobs.get(failed)['state']=='failed'
    assert 'storage is full' in jobs.get(failed)['error']
    assert jobs.get(succeeded)['result']=={'ok':True}


def test_cancel_cleanup_failure_does_not_poison_worker_queue(tmp_path):
    jobs=BrowserJobs(Store(tmp_path))
    def operation(update,cancel):
        try:yield
        finally:raise OSError('Cleanup fault')
    ident=jobs.start('Cleanup fault',operation)['id'];jobs.run_pending(limit=1)
    jobs.cancel(ident)
    other=jobs.start('Unrelated',lambda update,cancel:{'ok':True})['id']
    jobs.run_pending()
    assert jobs.get(ident)['state']=='cancelled'
    assert 'Cleanup failed: Cleanup fault' in jobs.get(ident)['error']
    assert jobs.get(other)['result']=={'ok':True}
