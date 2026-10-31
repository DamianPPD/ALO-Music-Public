"""Local, point-in-time acceptance of one adopted OutputSpec observation.

No content I/O in acceptance, no cache writes or file mutation. Metadata-only
revalidation is required on GUI delivery; watcher events are not that proof.
The bounded single-record API must NOT be looped over all managed bindings.
"""
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import Event, Lock
import os
import re
import sys

from .adopted_output import AssessmentRequest, _no_reparse
from .legacy_adoption import _source_context
from audio_library_organizer.domain.file_state import FileState
from audio_library_organizer.domain.output_spec import NAMESPACE, VERSION
from audio_library_organizer.metadata.change_history import metadata_revision
from audio_library_organizer.storage.managed_bindings import evidence_digest
from audio_library_organizer.safety import windows_file_identity as windows_identity


def output_policy(settings):
    # No API keys or private provider settings in the policy token or logs.
    return evidence_digest({'contract':(NAMESPACE,VERSION),
        'filename_template':settings.filename_template,'folder_organization':settings.folder_organization})


class OutputCheckOperation:
    """Immutable policy/generation plus a thread-safe revocation latch."""
    def __init__(self, library_id, operation_id, generation, policy_revision, track_id=None):
        self.library_id,self.operation_id,self.generation=library_id,operation_id,generation
        self.policy_revision,self.track_id=policy_revision,track_id
        self._cancelled=Event();self._lock=Lock();self._request=None
        self._windows_lease=None

    def invalidate(self):
        self._cancelled.set()
        with self._lock:lease=self._windows_lease
        if lease is not None:lease.revoke('OPERATION_INVALIDATED')

    def attach_windows_lease(self, lease):
        with self._lock:
            if self._cancelled.is_set() or self._windows_lease is not None:
                lease.revoke('OPERATION_INVALIDATED')
                return False
            self._windows_lease=lease
            return True

    def owns_windows_lease(self, lease):
        with self._lock:
            return not self._cancelled.is_set() and self._windows_lease is lease

    def detach_windows_lease(self, lease):
        with self._lock:
            if self._windows_lease is lease:self._windows_lease=None

    def choose(self, bindings):
        # Deliberately bounded. With several bindings require one selected row.
        candidates=[b for b in bindings if self.track_id is None or b.track_id==self.track_id]
        with self._lock:
            if len(candidates)==1 and not self._cancelled.is_set():
                b=candidates[0]
                self._request=AssessmentRequest(self.library_id,b.track_id,b.binding_id,
                    self.operation_id,self.generation,self.policy_revision)
            return self._request

    def current_request(self):
        with self._lock:
            return None if self._cancelled.is_set() else self._request


def local_filesystem(path):
    """Worker-only Linux-local capability gate; unknown/network is refused.

    Windows ctime is creation time, not change time. Until a native, tested
    change token exists, positive GUI delivery is deliberately unsupported.
    """
    path=Path(path).absolute()
    try:
        device=path.lstat().st_dev
        if not sys.platform.startswith('linux'):return None
        mounts=[]
        def unescape(value):
            return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            before,after=line.split(' - ',1);point=Path(unescape(before.split()[4]))
            if path==point or point in path.parents:mounts.append((len(point.parts),point,after.split()[0]))
        _,point,fs=max(mounts,key=lambda m:m[0])
        return ('linux',fs,str(point),device) if fs in {'ext2','ext3','ext4','xfs','btrfs','tmpfs','overlay'} else None
    except (OSError,ValueError,IndexError):
        return None


@dataclass(frozen=True, slots=True)
class OutputDelivery:
    pending: object
    root: str
    source_root: str
    source_locator: str
    managed_locator: str
    source_stamp: tuple
    managed_stamp: tuple
    local_capabilities: tuple
    database_locator: str
    database_identity: tuple
    windows_material: tuple = ()
    windows_database: object = None
    windows_lease: object = None

    @property
    def watch_paths(self):
        return tuple(dict.fromkeys((self.source_locator,self.managed_locator,
            str(Path(self.source_locator).parent),str(Path(self.managed_locator).parent),
            self.database_locator,str(Path(self.database_locator).parent))))


def context_matches(delivery, snapshot, request):
    """Pure matching of a fresh SQLite snapshot, never cache-derived ownership."""
    pending=delivery.pending;guard=pending.assessment.guard;track=snapshot.track
    if (guard is None or request is None or request!=pending.request or guard.request!=request
            or guard.contract!=(NAMESPACE,VERSION) or snapshot.library_id!=request.library_id
            or track is None or track.track_id!=request.track_id or track.manual_cover_path
            or metadata_revision(track)!=guard.metadata_revision
            or _source_context(track,snapshot.sources,snapshot.library_id)!=guard.source_context
            or evidence_digest([asdict(b) for b in snapshot.managed_bindings])!=guard.owners_revision):
        return False
    owners=[b for b in snapshot.managed_bindings if b.track_id==track.track_id]
    roots=[s.root_path for s in snapshot.sources if s.source_id==track.source_id and s.active]
    if len(owners)!=1 or roots!=[delivery.source_root]:return False
    b=owners[0]
    return (b.binding_id==request.binding_id and evidence_digest(asdict(b))==guard.binding_revision
        and delivery.windows_material==guard.windows_material
        and ((delivery.windows_database is None and guard.windows_database is None)
             or windows_identity.same_database(guard.windows_database,delivery.windows_database))
        and b.locator(delivery.root)==delivery.managed_locator
        and str(track.path)==delivery.source_locator
        and b.stat_identity==delivery.managed_stamp
        and guard.source_identity==delivery.source_stamp
        and tuple(guard.material_identity)==(delivery.managed_locator,*delivery.managed_stamp[:5],b.expected_sha256))


def material_matches(delivery):
    """Metadata only on known local paths. No MP3 open/read/hash/decode."""
    try:
        if windows_identity.on_windows():
            return (windows_identity.positive_acceptance_enabled() and delivery.windows_lease is not None
                and delivery.windows_lease.active_for((delivery.source_locator,delivery.managed_locator),delivery.windows_material)
                and len(delivery.windows_material)==2
                and all(windows_identity.same_material(old,windows_identity.capture(path))
                    for old,path in zip(delivery.windows_material,(delivery.source_locator,delivery.managed_locator))))
        if delivery.windows_material:return False
        return (_no_reparse(delivery.source_locator,delivery.source_root)==delivery.source_stamp
            and _no_reparse(delivery.managed_locator,delivery.root)==delivery.managed_stamp)
    except (OSError,ValueError,RuntimeError):return False


def database_safe(delivery):
    """Reject replaced/aliased DB paths before any GUI SQLite connection.

    Ignore mutable DB size/timestamps: ordinary cache writes change them.
    """
    try:
        if windows_identity.on_windows():
            return (windows_identity.positive_acceptance_enabled() and delivery.windows_database is not None
                and windows_identity.same_database(delivery.windows_database,
                    windows_identity.capture(delivery.database_locator,mutable=True)))
        if delivery.windows_database is not None:return False
        return _no_reparse(delivery.database_locator,delivery.root)[:2]==delivery.database_identity
    except (OSError,ValueError,RuntimeError):return False


def prepare_delivery(repository, root, pending, request, *, windows_lease=None):
    """Worker-only capability preparation after the ordinary reconciliation."""
    if (pending is None or not pending.evaluation.is_confirmed
            or pending.evaluation.state!=FileState.NEEDS_UPDATE or pending.assessment.guard is None):
        return None
    is_windows=windows_identity.on_windows()
    if is_windows and (not windows_identity.positive_acceptance_enabled() or windows_lease is None):return None
    snapshot=repository.adopted_assessment_snapshot(pending.request.track_id)
    t=snapshot.track
    if t is None:return None
    roots=[s.root_path for s in snapshot.sources if s.source_id==t.source_id and s.active]
    owners=[b for b in snapshot.managed_bindings if b.track_id==t.track_id]
    if len(roots)!=1 or len(owners)!=1:return None
    binding=owners[0];guard=pending.assessment.guard
    paths=(str(t.path),binding.locator(root),str(repository.database_path))
    try:database_stamp=_no_reparse(paths[2],root)
    except (OSError,ValueError,RuntimeError):return None
    # Acceptance resolves root/ancestor metadata too. A local leaf nested below
    # a remote/unknown root is not enough to make that GUI operation local.
    metadata_paths=tuple(dict.fromkeys(str(q) for p in paths for q in (Path(p),*Path(p).parents)))
    native_database=None
    if is_windows:
        # No locality/token fallback to stat. The module checks the full chain
        # on the handle's actual fixed NTFS volume; all paths must qualify.
        if len(guard.windows_material)!=2:return None
        try:native_database=windows_identity.capture(paths[2],mutable=True)
        except (OSError,ValueError,RuntimeError):return None
        if not windows_identity.same_database(guard.windows_database,native_database):return None
        caps=tuple(('windows','NTFS',p.leaf.volume_guid) for p in (*guard.windows_material,native_database))
    else:
        caps=tuple(local_filesystem(p) for p in metadata_paths)
    if not all(caps):return None
    d=OutputDelivery(pending,str(root),roots[0],*paths[:2],guard.source_identity,binding.stat_identity,caps,
        paths[2],database_stamp[:2],guard.windows_material,native_database,windows_lease)
    return d if context_matches(d,snapshot,request) and material_matches(d) else None


@dataclass(frozen=True, slots=True)
class OutputHistory:
    """Non-authoritative display observation; never contains a delivery/lease."""
    evaluation: object
    library_id: str
    track_id: str
    binding_id: str
    operation_id: str
    policy_revision: str
    metadata_revision: str
    binding_revision: str
    owners_revision: str
    source_context: str
    root: str
    source_locator: str
    managed_locator: str
    database_locator: str

    @property
    def watch_paths(self):
        return tuple(dict.fromkeys((self.source_locator,self.managed_locator,
            str(Path(self.source_locator).parent),str(Path(self.managed_locator).parent),
            self.database_locator,str(Path(self.database_locator).parent))))


def history_from_delivery(delivery):
    """Copy only after protected acceptance; the result cannot renew validity."""
    request=delivery.pending.request;guard=delivery.pending.assessment.guard
    evaluation=replace(delivery.pending.evaluation,is_confirmed=False,
        reason='HISTORICAL_PROTECTED_OUTPUT_OBSERVATION')
    return OutputHistory(evaluation,request.library_id,request.track_id,request.binding_id,
        request.operation_id,request.policy_revision,guard.metadata_revision,guard.binding_revision,
        guard.owners_revision,guard.source_context,delivery.root,delivery.source_locator,
        delivery.managed_locator,delivery.database_locator)


def history_matches(history, snapshot, root, policy):
    """Pure context check for display, NOT a physical file/ownership preflight."""
    track=snapshot.track
    if (history.evaluation.is_confirmed or str(root)!=history.root or policy!=history.policy_revision
            or snapshot.library_id!=history.library_id or track is None or track.track_id!=history.track_id
            or str(track.path)!=history.source_locator or metadata_revision(track)!=history.metadata_revision
            or _source_context(track,snapshot.sources,snapshot.library_id)!=history.source_context
            or evidence_digest([asdict(b) for b in snapshot.managed_bindings])!=history.owners_revision):
        return False
    owners=[b for b in snapshot.managed_bindings if b.track_id==history.track_id]
    return (len(owners)==1 and owners[0].binding_id==history.binding_id
        and owners[0].locator(root)==history.managed_locator
        and evidence_digest(asdict(owners[0]))==history.binding_revision)
