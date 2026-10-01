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
