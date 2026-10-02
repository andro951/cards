"""Low-overhead slow-operation timings in the existing rotating app log."""
import functools
import inspect
import json
import time
from contextlib import contextmanager

THRESHOLD_SECONDS=.1


def record_timing(store,stage,started,outcome='ok',**details):
    seconds=time.perf_counter()-started
    logger=getattr(store,'timing_logger',None)
    if seconds<THRESHOLD_SECONDS or logger is None:return
    payload={'at':time.time(),'stage':stage,'seconds':round(seconds,4),'outcome':outcome,**details}
    #Diagnostic logging must not turn successful work into an application error.
    try:logger.info('TIMING %s',json.dumps(payload,ensure_ascii=False,default=str))
    except Exception:pass


@contextmanager
def timing(store,stage,**details):
    started=time.perf_counter();outcome='ok'
    try:yield details
    except BaseException as error:
        outcome=type(error).__name__
        raise
    finally:record_timing(store,stage,started,outcome,**details)


def timed(stage):
    def decorate(operation):
        signature=inspect.signature(operation)
        @functools.wraps(operation)
        def measured(self,*args,**kwargs):
            store=getattr(self,'store',None) or getattr(getattr(self,'net',None),'store',None)
            if store is None and hasattr(self,'home'):store=self
            if getattr(store,'timing_logger',None) is None:return operation(self,*args,**kwargs)
            values=signature.bind(self,*args,**kwargs).arguments
            details={}
            for key in ('url','source','kind','ident','key','art_id','art_origin','policy','refresh'):
                value=values.get(key)
                if isinstance(value,(str,bool,int)):details[key]=value[:300] if isinstance(value,str) else value
            for key in ('sf','face','c','d','data'):
                value=values.get(key)
                if isinstance(value,dict) and value.get('name'):details[key+'Name']=str(value['name'])[:200]
            if isinstance(values.get('content'),bytes):details['bytes']=len(values['content'])
            with timing(store,stage,**details) as info:
                result=operation(self,*args,**kwargs)
                if stage.startswith('network.') and isinstance(result,tuple):
                    info.update(bytes=len(result[0]),cache=bool(result[2].get('cache')))
                return result
        return measured
    return decorate