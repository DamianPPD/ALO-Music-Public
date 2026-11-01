"""One finite read-only wrapper snapshot. No objects escape, no GC/cleanup."""
import gc,types
import shiboken6

def direct_keys(mapping,obj):
    keys=[]
    for key,value in mapping.items():
        if value is obj and isinstance(key,str):keys.append(key)
    return keys[:24]

def observe(groups,record,phase):
    for kind,refs in groups.items():
        for index,reference in enumerate(refs):
            obj=reference()
            if obj is None:
                record('i1-wrapper',phase=phase,group=kind,index=index,python_alive=False)
                continue
            # obj pins only this inspected object until the next iteration.
            # get_referrers sees GC containers, not every C++ binding root.
            referred=gc.get_referrers(obj);details=[]
            for referrer in referred:
                row={'id':id(referrer),'type':type(referrer).__module__+'.'+type(referrer).__qualname__}
                if isinstance(referrer,types.MethodType):
                    row['method']=referrer.__func__.__qualname__;row['bound_self']=id(referrer.__self__)
                elif isinstance(referrer,dict):row['keys']=direct_keys(referrer,obj)
                details.append(row)
            record('i1-wrapper',phase=phase,group=kind,index=index,python_alive=True,
                object=id(obj),native_valid=shiboken6.isValid(obj),
                referrers=details[:32],truncated=len(details)>32,
                measurement_reference='local obj while this snapshot executes',forced_gc=False)
