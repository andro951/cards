"""A real browser filesystem log failure must not stop the Python engine."""
import os
import pytest
from test_browser_storage import static_browser

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Opt-in isolated browser filesystem')


@pytest.mark.parametrize('static_browser',['msedge'],indirect=True)
def test_progress_log_io_failure_keeps_results_and_engine_available(static_browser):
    directory,context,origin=static_browser
    files=directory/'web/workspace-files.js';source=files.read_text(encoding='utf-8')
    source=source.replace('    close = async path => {','''    close = async path => {
        if(/^logs\\/job-/.test(path)) {
            const writer=this.writers.get(path);
            this.writers.delete(path);await writer?.abort().catch(()=>{});
            throw new DOMException('Injected stale-state progress log failure','InvalidStateError');
        }
''')
    files.write_text(source,encoding='utf-8')
    hook='''
original_log_test_request=request
def request(app,method,url,body,headers):
    if url=='/api/__test__/log-failure':
        def work(update,cancel):
            for n in range(3):update(n+1,3,'Preparing');yield
            return {'preserved':42}
        return {'status':200,'mime':'application/json','body':json.dumps(app.jobs.start('Log failure test',work)).encode(),'headers':{}}
    return original_log_test_request(app,method,url,body,headers)
'''
    worker=directory/'web/engine-worker.js';source=worker.read_text(encoding='utf-8')
    worker.write_text(source.replace('def browser_request(method, url, body, headers):',hook+'\ndef browser_request(method, url, body, headers):'),encoding='utf-8')
    page=context.new_page();page.goto(origin);page.locator('#import-deck').wait_for(timeout=90000)
    result=page.evaluate('''async()=>{
        const ui=await import('/site/ui.js');
        const result=await ui.job('/api/__test__/log-failure',{}, {label:'Log failure test'});
        await ui.api('/api/decks');
        const report=(await import('/site/diagnostics.js')).browserDiagnosticReport();
        return {result,engine:report.engineStatus,warning:report.entries.some(e=>e.kind==='job log warning')};
    }''')
    assert result=={'result':{'preserved':42},'engine':'Ready','warning':True}
