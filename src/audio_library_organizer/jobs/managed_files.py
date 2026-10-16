"""Read planning and worker revalidation; never a managed binding producer.

FileFacts are observations, including historical SQLite observations. Only an
independent explicit ManagedReadBinding can attest ownership. No name, cache,
source hash or fingerprint creates that attestation. Plans perform no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib
import ntpath
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys
from typing import Callable

from audio_library_organizer.domain.file_state import FileAvailability, FileFacts, Ownership
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.storage.source_registry import SourceRoot


class ReadPurpose(StrEnum):
    PLAYBACK = 'PLAYBACK'
    WAVEFORM = 'WAVEFORM'
    COVER_READ = 'COVER_READ'
    AUDIO_IDENTIFICATION = 'AUDIO_IDENTIFICATION'
    AUDIO_PROPERTIES = 'AUDIO_PROPERTIES'
    METADATA_EDITOR_READ = 'METADATA_EDITOR_READ'


class MaterialKind(StrEnum):
    SOURCE = 'SOURCE'
    MANAGED = 'MANAGED'


def lexical_locator(raw: str | Path) -> str:
    """A comparison key only: no resolve/stat/expanduser or alias claims."""
    text = str(raw)
    if not text or '\x00' in text or text.startswith('~'):
        raise ValueError('An absolute read locator is required.')
    if ntpath.splitdrive(text)[0] or text.startswith('\\\\'):
        path = PureWindowsPath(ntpath.normpath(text))
        if not path.is_absolute():
            raise ValueError('Relative Windows read locator.')
        return 'windows:' + ntpath.normcase(str(path))
    if not PurePosixPath(text).is_absolute():
        raise ValueError('Relative read locator.')
    return 'posix:' + os.path.normpath(text)


def track_identity(track: TrackRecord | None, library_id: str = '') -> str | None:
    """Persisted consumers use UUID; legacy standalone records use a local key."""
    if track is None:
        return None
    if track.track_id:
        return f'uuid:{library_id}:{track.track_id}'
    # Compatibility for unsaved records/local-file widgets, not a UUID producer.
    return str(track.path).casefold()


def source_material_revision(track: TrackRecord) -> tuple:
    """Cached audio revision for atomic writes; never a fresh presence proof."""
    return (track.size_bytes, track.mtime_ns, track.sha256,
            track.fingerprint, track.fingerprint_duration)


@dataclass(frozen=True, slots=True)
class ManagedReadBinding:
    """An input attested elsewhere, never constructed from a cache by readers.

    The future producer must own this contract. Stage 2.3 production supplies no
    such bindings; tests explicitly inject earlier-confirmed synthetic proofs.
    Full SHA is the expected output bytes, independent of the source SHA.
    """
    library_id: str
    track_id: str
    locator: str
    sha256: str
    revision: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v for v in
                   (self.library_id, self.track_id, self.locator, self.revision)):
            raise ValueError('Managed read proof has incomplete identity.')
        lexical_locator(self.locator)
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(c not in '0123456789abcdef' for c in self.sha256.lower())):
            raise ValueError('Managed read requires an expected full output digest.')


@dataclass(frozen=True, slots=True)
class SourceReadMaterial:
    """Cached selection revision, never fresh presence or ownership evidence."""
    track_id: str
    locator: str
    source_id: str | None
    relative_path: str | None
    size_bytes: int
    mtime_ns: int
    sha256: str | None

    @classmethod
    def from_track(cls, track: TrackRecord):
        return cls(track.track_id or '', str(track.path), track.source_id,
                   track.source_relative_path, track.size_bytes, track.mtime_ns, track.sha256)

    @property
    def revision(self):
        return f'{self.size_bytes}:{self.mtime_ns}:{self.sha256 or ""}'


@dataclass(frozen=True, slots=True)
class ReadContext:
    library_id: str
    library_root: str
    sources: tuple[SourceRoot, ...] = ()
    facts: tuple[FileFacts, ...] = ()
    managed_bindings: tuple[ManagedReadBinding, ...] = ()
    source_materials: tuple[SourceReadMaterial, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadResolution:
    library_id: str
    track_id: str
    purpose: ReadPurpose
    locator: str | None = None
    kind: MaterialKind | None = None
    reason_code: str = 'UNRESOLVED'
    evidence_freshness: str = 'UNOBSERVED'
    unresolved: bool = True
    generation: int = 0
    revision: str = ''
    root: str | None = None
    expected_sha256: str | None = None
    is_verified: bool = False
    material_identity: tuple = ()
    foreign_owner_locators: tuple[str, ...] = ()
    fallback: ReadResolution | None = None

    @property
    def requires_recheck(self) -> bool:
        return not self.is_verified

    @property
    def safe_for_file_mutation(self) -> bool:
        return False

    @property
    def guard_key(self) -> tuple:
        return (self.library_id, self.track_id, self.purpose, self.generation,
                self.kind, self.locator, self.revision, self.foreign_owner_locators)


@dataclass(frozen=True, slots=True)
class ReadResult:
    resolution: ReadResolution
    value: object = None


def local_read_plan(path: Path, purpose: ReadPurpose, *, generation: int = 0) -> ReadResolution:
    """Explicit standalone/local-file compatibility, not a library binding."""
    return ReadResolution('', 'local:' + str(path), purpose, str(path), MaterialKind.SOURCE,
                          'LOCAL_FILE_RECHECK_REQUIRED', generation=generation,
                          revision=str(path), root=str(path.parent))


def _contained(locator, root) -> bool:
    try:
        key, root_key = lexical_locator(locator), lexical_locator(root)
        if key.split(':', 1)[0] != root_key.split(':', 1)[0]:
            return False
        cls = PureWindowsPath if key.startswith('windows:') else PurePosixPath
        path, parent = cls(key.split(':', 1)[1]), cls(root_key.split(':', 1)[1])
        return path != parent and path.is_relative_to(parent)
    except (ValueError, TypeError):
        return False


def resolve_read_path(track: TrackRecord, context: ReadContext, purpose: ReadPurpose,
                      *, generation: int = 0) -> ReadResolution:
    """Select a candidate from immutable evidence, never declare fresh presence.

    All current purposes allow an unambiguous source fallback. A managed plan
    additionally requires explicit ownership and a separate output identity.
    Unknown/offline observations permit rechecking a trusted managed locator;
    they do not become confirmed absence or establish ownership.
    """
    if not isinstance(purpose, ReadPurpose):
        raise ValueError('Unknown read purpose.')
    base = ReadResolution(context.library_id, track.track_id or '', purpose, generation=generation)
    if not context.library_id or not track.track_id:
        return replace(base, reason_code='RECORD_IDENTITY_REQUIRED')
    observations = [f for f in context.facts if f.track_id == track.track_id]
    if len(observations) > 1:
        return replace(base, reason_code='AMBIGUOUS_FACTS')
    facts = observations[0] if observations else None
    materials = [m for m in context.source_materials if m.track_id == track.track_id]
    if len(materials) > 1:
        return replace(base, reason_code='AMBIGUOUS_SOURCE_REVISION')
    material = materials[0] if materials else SourceReadMaterial.from_track(track)
    source = None
    roots = [s for s in context.sources if s.library_id == context.library_id
             and s.source_id == track.source_id and s.active]
    if len(roots) == 1 and track.source_relative_path:
        root = roots[0]
        try:
            relative = track.source_relative_path.replace('\\', '/')
            if (relative.startswith('/') or '..' in PurePosixPath(relative).parts
                    or ntpath.splitdrive(relative)[0]):
                raise ValueError('Unsafe source relative locator.')
            joined = str(PureWindowsPath(root.root_path) / relative) if lexical_locator(root.root_path).startswith('windows:') else str(PurePosixPath(root.root_path) / relative)
            bound = lexical_locator(joined) == lexical_locator(track.path) and _contained(track.path, root.root_path)
            bound = (bound and lexical_locator(material.locator) == lexical_locator(track.path)
                     and material.source_id == track.source_id and material.relative_path == track.source_relative_path)
            obs = facts.source if facts else None
            matches = obs is None or (obs.track_id == track.track_id and obs.source_id == track.source_id
                                      and lexical_locator(obs.locator) == lexical_locator(track.path))
            if obs is not None and not obs.is_current and not matches:
                # A historical observation of the previous binding cannot veto
                # the current UUID/registry binding or attest its availability.
                obs = None
                matches = True
            blocked = obs is not None and obs.is_current and obs.availability in (
                FileAvailability.MISSING, FileAvailability.OFFLINE, FileAvailability.ERROR)
            if bound and matches and not blocked:
                source = replace(base, locator=str(track.path), kind=MaterialKind.SOURCE,
                                 reason_code='SOURCE_RECHECK_REQUIRED', root=root.root_path,
                                 revision=f'{root.source_id}:{relative}:{material.revision}:{obs.checked_at if obs else ""}',
                                 evidence_freshness='HISTORICAL' if obs and not obs.is_current else 'PENDING_RECHECK')
        except (ValueError, TypeError):
            pass
    proofs = [p for p in context.managed_bindings if p.library_id == context.library_id
              and p.track_id == track.track_id]
    managed = facts.managed if facts else None
    trusted = (len(proofs) == 1 and facts is not None and facts.managed_expected is True
               and facts.ownership == Ownership.CONFIRMED and facts.owner_track_id == track.track_id
               and facts.conflict is None and managed is not None and managed.track_id == track.track_id
               and managed.source_id is None)
    if trusted:
        proof = proofs[0]
        try:
            trusted = (lexical_locator(proof.locator) == lexical_locator(managed.locator)
                       and _contained(proof.locator, context.library_root))
            owners = {(p.library_id, p.track_id) for p in context.managed_bindings
                      if lexical_locator(p.locator) == lexical_locator(proof.locator)}
            trusted = trusted and owners == {(context.library_id, track.track_id)}
        except (ValueError, TypeError):
            trusted = False
        if trusted and not (managed.is_current and managed.availability == FileAvailability.MISSING):
            return replace(base, locator=proof.locator, kind=MaterialKind.MANAGED,
                           reason_code='MANAGED_RECHECK_REQUIRED', root=context.library_root,
                           expected_sha256=proof.sha256.lower(), revision=f'{proof.revision}:{proof.sha256.lower()}',
                           evidence_freshness='HISTORICAL' if not facts.is_current or not managed.is_current else 'PENDING_RECHECK',
                           foreign_owner_locators=tuple(sorted(p.locator for p in context.managed_bindings
                               if (p.library_id, p.track_id) != (context.library_id, track.track_id))),
                           fallback=source)
    return source or replace(base, reason_code='NO_TRUSTED_READ_LOCATOR')


def _failed(plan: ReadResolution, reason: str) -> ReadResolution:
    return replace(plan, is_verified=False, unresolved=True, reason_code=reason,
                   evidence_freshness='UNRESOLVED', material_identity=())


def _stamp(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _opened_stat_matches(before, opened):
    if os.name != 'nt':
        return _stamp(opened) == _stamp(before)
    # CPython 3.11 exposes CreationTime as integer ctime in both APIs.
    # Other Windows runtimes require explicit birthtime because fstat ctime
    # can mean metadata change time. Persisted and same-API tokens stay intact.
    creation_field = ('st_ctime_ns' if sys.implementation.name == 'cpython'
                      and sys.version_info[:2] == (3, 11) else 'st_birthtime_ns')
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_nlink', creation_field)
    tokens = [tuple(getattr(value, name, None) for name in fields)
              for value in (before, opened)]
    for token in tokens:
        if (any(type(value) is not int for value in token) or token[0] < 0
                or token[1] <= 0 or token[2] < 0 or token[4] <= 0):
            raise ValueError('Insufficient Windows file identity evidence.')
    return tokens[0] == tokens[1]


def recheck_read_path(plan: ReadResolution, *, cancelled: Callable[[], bool] | None = None) -> ReadResolution:
    """Worker-only read preflight, including root aliases and output bytes.

    This is a bounded-in-time observation for reads, not a lock or a no-race
    authorization to mutate files. Managed stat equality alone is insufficient.
    """
    if cancelled and cancelled():
        return _failed(plan, 'CANCELLED')
    if plan.locator is None or plan.root is None:
        return _failed(plan, plan.reason_code)
    try:
        if os.name != 'nt' and lexical_locator(plan.locator).startswith('windows:'):
            return _failed(plan, 'UNSUPPORTED_LOCATOR_PLATFORM')
        root = Path(plan.root).resolve(strict=True)
        path = Path(plan.locator).resolve(strict=True)
        if path == root or not path.is_relative_to(root):
            return _failed(plan, 'READ_LOCATOR_OUTSIDE_ROOT')
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            return _failed(plan, 'NOT_A_REGULAR_FILE')
        digest = ''
        if plan.kind == MaterialKind.MANAGED:
            if not plan.expected_sha256:
                return _failed(plan, 'MANAGED_IDENTITY_UNPROVEN')
            for locator in plan.foreign_owner_locators:
                if cancelled and cancelled():
                    return _failed(plan, 'CANCELLED')
                try:
                    other = Path(locator).resolve(strict=True)
                    other_stat = other.stat()
                except FileNotFoundError:
                    continue
                if other == path or (before.st_ino and other_stat.st_ino
                        and (before.st_dev, before.st_ino) == (other_stat.st_dev, other_stat.st_ino)):
                    return _failed(plan, 'MANAGED_OWNER_ALIAS_CONFLICT')
                if not before.st_ino or not other_stat.st_ino:
                    return _failed(plan, 'MANAGED_ALIAS_IDENTITY_UNPROVEN')
            h = hashlib.sha256()
            with path.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                if not _opened_stat_matches(before, opened):
                    return _failed(plan, 'MATERIAL_CHANGED_DURING_READ')
                while chunk := stream.read(1024 * 1024):
                    if cancelled and cancelled():
                        return _failed(plan, 'CANCELLED')
                    h.update(chunk)
                if _stamp(os.fstat(stream.fileno())) != _stamp(opened):
                    return _failed(plan, 'MATERIAL_CHANGED_DURING_READ')
            digest = h.hexdigest()
            if digest != plan.expected_sha256:
                return _failed(plan, 'MANAGED_IDENTITY_CHANGED')
        if cancelled and cancelled():
            return _failed(plan, 'CANCELLED')
        if _stamp(path.stat()) != _stamp(before) or Path(plan.locator).resolve(strict=True) != path:
            return _failed(plan, 'MATERIAL_CHANGED_DURING_READ')
        return replace(plan, is_verified=True, unresolved=False, evidence_freshness='CURRENT',
                       reason_code=f'{plan.kind.value}_VERIFIED_FOR_READ',
                       material_identity=(str(path), *_stamp(before), digest))
    except FileNotFoundError:
        return _failed(plan, 'READ_MATERIAL_UNAVAILABLE')
    except (OSError, RuntimeError, ValueError):
        return _failed(plan, 'READ_RECHECK_ERROR')


def read_material(plan: ReadResolution, reader: Callable[[Path], object],
                  *, cancelled: Callable[[], bool] | None = None) -> ReadResult:
    """Use a rechecked locator; reject a changed material after the read too."""
    checked = recheck_read_path(plan, cancelled=cancelled)
    if not checked.is_verified:
        if plan.fallback is not None and checked.reason_code != 'CANCELLED':
            return read_material(plan.fallback, reader, cancelled=cancelled)
        return ReadResult(checked)
    try:
        value = reader(Path(checked.locator))
    except (OSError, RuntimeError, ValueError):
        return ReadResult(_failed(checked, 'MATERIAL_READ_ERROR'))
    after = recheck_read_path(checked, cancelled=cancelled)
    if not after.is_verified or after.material_identity != checked.material_identity:
        return ReadResult(_failed(after, 'CANCELLED' if after.reason_code == 'CANCELLED' else 'MATERIAL_CHANGED_DURING_READ'))
    return ReadResult(after, value)
