"""Short, worker-owned SOURCE/MANAGED protection; no UI/session lifetime lock.

Claiming a protected observation is a historical event, never validity after
revocation. Only the acquiring thread closes handles. Other threads may revoke
and wake it; cancellation cannot close a file under an in-flight worker read.
"""
from threading import Event, Lock, get_ident
from math import isfinite
from time import monotonic

from . import windows_file_identity as native


DELIVERY_TIMEOUT_SECONDS = 5.0
# Entire selected assessment + delivery, equal to the existing per-decode
# limit. Expiry revokes validity; cooperative readers stop at their next check.
# An OS call already in progress is not forcibly interrupted or closed under.
PROTECTION_TIMEOUT_SECONDS = 120.0
_UNCERTAIN_OWNERS=[]
_QUARANTINE_LOCK=Lock()


class LeaseCleanupError(OSError):
    def __init__(self,owner,errors):
        self.owner=owner
        super().__init__('WINDOWS_LEASE_CLOSE_FAILED; uncertain handles='+repr(owner.failed_handles)
            +': '+'; '.join(map(str,errors)))


class WindowsOutputLease:
    def __init__(self, paths, api):
        self.paths=tuple(paths);self.material=()
        self._api=api;self._owner=get_ident();self._handles=[]
        self._lock=Lock();self._done=Event();self._active=False
        self._revoked=False;self._close_attempted=False;self._acked=False
        self._claimed=False;self._reason='PREPARING';self._failed=()
        self._deadline=monotonic()+PROTECTION_TIMEOUT_SECONDS

    def _adopt_handle(self,h):
        if get_ident()!=self._owner:raise RuntimeError('LEASE_OWNER_THREAD_REQUIRED')
        self._handles.append(h)

    @property
    def active(self):
        with self._lock:return self._live_locked()

    def _live_locked(self):
        if self._active and not self._revoked and monotonic()>=self._deadline:
            self._revoked=True;self._active=False;self._reason='PROTECTION_TIMEOUT';self._done.set()
        return self._active and not self._revoked and not self._close_attempted

    def cancelled(self):
        return not self.active

    @property
    def accepted(self):
        """Historical fact only; callers MUST NOT use this as current authority."""
        with self._lock:return self._claimed

    @property
    def reason(self):
        with self._lock:return self._reason

    @property
    def owned_count(self):
        with self._lock:return len(self._handles)

    @property
    def failed_handles(self):
        with self._lock:return self._failed

    def active_for(self, paths, material):
        with self._lock:
            return (self._live_locked()
                and tuple(paths)==self.paths and tuple(material)==self.material)

    def claim(self, material):
        """Linearize one consumption while both objects are still protected.

        The consumer may copy an explicitly unconfirmed historical observation.
        This method neither extends protection nor authorizes later file I/O.
        """
        with self._lock:
            if (not self._live_locked()
                    or self._claimed or tuple(material)!=self.material):return False
            self._claimed=True
            return True

    def revoke(self, reason):
        with self._lock:
            if not self._revoked:
                self._revoked=True;self._active=False;self._reason=reason
            self._done.set()

    def acknowledge(self):
        """GUI has finished consuming or refusing this packet; never closes it."""
        with self._lock:
            self._live_locked()
            if not self._revoked:
                self._acked=True;self._revoked=True;self._active=False;self._reason='DELIVERED'
            self._done.set()

    def wait_for_delivery(self, timeout=DELIVERY_TIMEOUT_SECONDS):
        if get_ident()!=self._owner:raise RuntimeError('LEASE_OWNER_THREAD_REQUIRED')
        try:
            if (type(timeout) not in (int,float) or not isfinite(timeout)
                    or not 0<=timeout<=DELIVERY_TIMEOUT_SECONDS):
                raise ValueError('BOUNDED_DELIVERY_DEADLINE_REQUIRED')
            remaining=max(0.,min(float(timeout),self._deadline-monotonic()))
            if not self._done.wait(remaining):
                if self.active:self.revoke('DELIVERY_TIMEOUT')
            with self._lock:return self._acked
        finally:self.close()

    def close(self):
        if get_ident()!=self._owner:raise RuntimeError('LEASE_OWNER_THREAD_REQUIRED')
        with self._lock:
            if self._close_attempted:return
            self._close_attempted=True;self._active=False;self._revoked=True
            if self._reason=='PREPARING':self._reason='CLOSED'
            handles=tuple(self._handles);self._done.set()
        errors=[];failed=[]
        for h in reversed(handles):
            try:self._api.close(h)
            except OSError as exc:errors.append(exc);failed.append(h)
        with self._lock:
            self._handles=list(reversed(failed));self._failed=tuple(self._handles)
        if errors:
            # An unsuccessful close is uncertain, not permission to retry a
            # possibly reused HANDLE. Retain explicit ownership for diagnostics
            # and refuse all further positive acquisition until process exit.
            with _QUARANTINE_LOCK:
                if not any(owner is self for owner in _UNCERTAIN_OWNERS):_UNCERTAIN_OWNERS.append(self)
            raise LeaseCleanupError(self,errors)


def _acquire_pair(paths, api):
    """Internal API seam for protocol tests, not a positive-acceptance bypass."""
    paths=tuple(str(native._lexical(p)) for p in paths)
    if len(paths)!=2 or paths[0].casefold()==paths[1].casefold():
        raise ValueError('SOURCE_MANAGED_PAIR_REQUIRED')
    lease=WindowsOutputLease(paths,api)
    try:
        proofs=[]
        for path in paths:
            proof,_=native._open_path(path,api,owner=lease)
            proofs.append(proof)
        if proofs[0].leaf.object_identity==proofs[1].leaf.object_identity:
            raise ValueError('SOURCE_MANAGED_SAME_OBJECT')
        lease.material=tuple(proofs);lease._active=True;lease._reason='ACTIVE'
        return lease
    except BaseException:
        lease.close();raise


def acquire_output_lease(source, managed):
    with _QUARANTINE_LOCK:
        if _UNCERTAIN_OWNERS:raise OSError('WINDOWS_LEASE_CLEANUP_UNCERTAIN_RESTART_REQUIRED')
    if not native.positive_acceptance_enabled():
        raise OSError('WINDOWS_POSITIVE_ACCEPTANCE_NOT_VERIFIED')
    paths=tuple(str(native._lexical(p)) for p in (source,managed))
    if any(not p.lower().endswith('.mp3') for p in paths):
        raise ValueError('ONLY_ADOPTED_MP3_SUPPORTED')
    return _acquire_pair(paths,native._WinAPI())
