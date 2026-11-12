"""Controlled Qt/Python weak-receiver expiry, independent of MP3 and SQLite."""
from pathlib import Path
from threading import Event, get_native_id
import gc
import json
import os
import sys
import time
import faulthandler
from PySide6.QtCore import QObject, QRunnable, QThreadPool, SIGNAL
from PySide6.QtWidgets import QApplication

app=QApplication([])
directory=Path(sys.argv[1]); mode=sys.argv[2]
log=(directory/'cleanup-probe.jsonl').open('a',buffering=1)
fault=(directory/'cleanup-probe-fault.log').open('w')
faulthandler.enable(fault,all_threads=True)
faulthandler.dump_traceback_later(10,repeat=True,file=fault)
def record(**row):
    log.write(json.dumps({'pid':os.getpid(),'native_thread':get_native_id(),'time':time.monotonic(),**row})+'\n')
    log.flush()
record(stage='start',mode=mode)
sender=QObject(); pool=QThreadPool(); pool.setMaxThreadCount(4)

class Drop(QRunnable):
    def __init__(self,token,release):
        super().__init__();self.token=token;self.release=release
    def run(self):
        self.release.wait(10)

class Stable:
    def __init__(self): self.current=None
    def __call__(self,*args):
        if self.current:self.current.set()

stable=Stable()
if mode=='stable': sender.destroyed.connect(stable)
previous=None
try:
    for i in range(10000):
        token=Event(); release=Event()
        if previous: previous.set()
        if i%100==0:record(stage='before-connect',iteration=i)
        if mode=='weak':sender.destroyed.connect(token.set)
        else:stable.current=token
        pool.start(Drop(token,release))
        del token
        previous=release
    previous.set()
    record(stage='before-pool-finish',iteration=i+1)
    assert pool.waitForDone(10000),'Pool failed to finish'
    gc.collect();app.processEvents()
    record(stage='end',iteration=i+1,connections=sender.receivers(SIGNAL('destroyed()')))
finally:
    if previous:previous.set()
faulthandler.cancel_dump_traceback_later()
