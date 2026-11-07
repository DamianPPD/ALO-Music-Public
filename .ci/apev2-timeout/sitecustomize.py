import os

if os.environ.get('ALO_RESTART_TRACE_DIR'):
    import trace_restart
    trace_restart.install()
