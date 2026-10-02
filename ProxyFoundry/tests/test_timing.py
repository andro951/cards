"""Timing diagnostics preserve results/errors and include slow cache reads."""
import io
import json
import logging
from types import SimpleNamespace

import pytest
from foundry import timing
from foundry.network import Network
from foundry.storage import Store


def capture(store):
    stream=io.StringIO();logger=logging.Logger('timing-test');logger.addHandler(logging.StreamHandler(stream))
    store.timing_logger=logger
    return stream


def rows(stream):
    return [json.loads(line.removeprefix('TIMING ')) for line in stream.getvalue().splitlines()]


def test_slow_operation_and_error_are_timed_without_changing_behavior(monkeypatch):
    store=SimpleNamespace();stream=capture(store)
    ticks=iter([0,.05,1,1.25,2,2.5]);monkeypatch.setattr(timing.time,'perf_counter',lambda:next(ticks))
    with timing.timing(store,'fast'):pass
    with timing.timing(store,'slow',card='Example'):pass
    with pytest.raises(ValueError,match='original error'):
        with timing.timing(store,'failure'):raise ValueError('original error')
    logged=rows(stream)
    assert len(logged)==2
    assert logged[0]['seconds']==.25 and logged[0]['card']=='Example' and logged[0]['outcome']=='ok'
    assert logged[1]['seconds']==.5 and logged[1]['outcome']=='ValueError'


def test_network_log_distinguishes_download_from_cache_and_includes_bytes(tmp_path,monkeypatch):
    store=Store(tmp_path);stream=capture(store)
    monkeypatch.setattr(timing,'THRESHOLD_SECONDS',0)
    net=Network(store,transport=lambda url:(b'{"name":"Example"}','application/json',{}))
    url='https://api.scryfall.com/cards/named?exact=Example'
    assert net.fetch(url)[0]==net.fetch(url)[0]
    fetches=[row for row in rows(stream) if row['stage']=='network.fetch']
    assert [row['cache'] for row in fetches]==[False,True]
    assert all(row['bytes']==18 and row['url']==url for row in fetches)
    assert len([row for row in rows(stream) if row['stage']=='network.download'])==1
    assert any(row['stage']=='storage.asset' for row in rows(stream))


def test_logger_failure_does_not_break_work(monkeypatch):
    class Broken:
        def info(self,*args):raise OSError('log full')
    monkeypatch.setattr(timing,'THRESHOLD_SECONDS',0)
    with timing.timing(SimpleNamespace(timing_logger=Broken()),'operation'):pass


@pytest.mark.parametrize('storage_type',['browser','selected-folder','local-folder'])
def test_timings_and_diagnostics_identify_storage_type(tmp_path,monkeypatch,storage_type):
    from foundry.browser import create_app,request
    app=create_app(tmp_path,lambda url:(b'{}','application/json',{}),'http://127.0.0.1',storage_type=storage_type)
    stream=capture(app.store);monkeypatch.setattr(timing,'THRESHOLD_SECONDS',0)
    with timing.timing(app.store,'test.operation'):pass
    assert rows(stream)[-1]['storageType']==storage_type
    assert app.diagnostic_data()['workspace']['storageType']==storage_type
    response=request(app,'GET','/api/bootstrap')
    assert json.loads(response['body'])['storageType']==storage_type
    request(app,'POST','/api/render-diagnostic',json.dumps({'stage':'timing','diagnostic':{'stage':'native.first-draw','seconds':1,'storageType':'incorrect'}}).encode())
    log=(app.store.home/'logs/app.log').read_text(encoding='utf-8')
    assert '"storageType":"'+storage_type+'"' in log