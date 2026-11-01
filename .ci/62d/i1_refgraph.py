"""Read-only bounded referrer snapshots; never collection, mutation or cleanup.

All measurement-owned references are labelled, never used to conclude leakage.
The caller's original weakref assertion runs after this function returns.
"""
import gc,types
from collections import Counter
import shiboken6
from PySide6.QtCore import QObject

def observe(owner_refs,window_refs,record):
    # This local dictionary deliberately pins this finite graph during inspection.
    # No object from it escapes; log payloads contain only scalar identities.
    targets={}
    for i,r in enumerate(owner_refs):
        if r() is not None:targets['lease-'+str(i)]=r()
    for i,r in enumerate(window_refs):
        w=r()
        if w is None:continue
        targets['window-'+str(i)]=w
        for field in ('library','last_reconciliation_result','_thread','_worker','_output_operation','_file_check_finished'):
            obj=getattr(w,field,None)
            if obj is not None:targets['window-'+str(i)+'.'+field]=obj
        p=getattr(w,'library',None)
        if p is not None:
            for field in ('_context_provider','_context_worker_reader'):
                obj=getattr(p,field,None)
                if obj is not None:targets['page-'+str(i)+'.'+field]=obj
        result=getattr(w,'last_reconciliation_result',None)
        d=getattr(result,'output_delivery',None)
        if d is not None:targets['delivery-'+str(i)]=d
    labels={id(o):n for n,o in targets.items()}
    dictionaries={id(o.__dict__):name+'.__dict__' for name,o in targets.items() if hasattr(o,'__dict__')}
    measurement_ids={id(targets),id(labels),id(dictionaries),id(owner_refs),id(window_refs)}
    for name,obj in targets.items():
        refs=gc.get_referrers(obj)
        details=[]
        for referrer in refs:
            item={'id':id(referrer),'type':type(referrer).__module__+'.'+type(referrer).__qualname__}
            if id(referrer) in measurement_ids:item['measurement']=True
            if id(referrer) in labels:item['target']=labels[id(referrer)]
            if id(referrer) in dictionaries:item['owner_dict']=dictionaries[id(referrer)]
            if isinstance(referrer,dict):
                item['direct_keys']=[k for k,v in referrer.items() if v is obj and isinstance(k,str)][:32]
                item['measurement']=item.get('measurement',False) or '__name__' in referrer and referrer.get('__name__')==__name__
            elif isinstance(referrer,types.MethodType):
                item['bound_self']=id(referrer.__self__);item['method']=referrer.__func__.__qualname__
            elif isinstance(referrer,types.CellType):
                # Determine functions that own this closure cell without invoking them.
                closures=[t for t in gc.get_referrers(referrer) if isinstance(t,tuple)]
                names=[]
                for closure in closures:
                    for f in gc.get_referrers(closure):
                        if isinstance(f,types.FunctionType) and f.__closure__ is closure:
                            names.append(f.__module__+'.'+f.__qualname__)
                item['closure_functions']=names
            elif isinstance(referrer,types.FrameType):
                item['frame']=referrer.f_code.co_name;item['measurement']=referrer.f_code.co_filename==__file__
            details.append(item)
        record('i1-referrers',name=name,object=id(obj),type=type(obj).__module__+'.'+type(obj).__qualname__,
            native_valid=shiboken6.isValid(obj) if isinstance(obj,QObject) else None,
            referrer_count=len(refs),types=dict(Counter(type(r).__name__ for r in refs)),
            details=details[:48],truncated=len(details)>48,
            observation_pins_graph=True,forced_gc=False)
