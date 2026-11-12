import os

if os.environ.get('ALO_RESTART_TRACE_DIR'):
    if os.environ.get('ALO_RESTART_TRACE_MODE') == 'stacks':
        import stack_only
        stack_only.install()
    else:
        import trace_restart
        trace_restart.install()
