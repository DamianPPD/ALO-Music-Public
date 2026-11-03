"""Transient, worker-only assessment of ONE approved adopted MP3.

No cache write, adoption, export, tagging or automatic scan. The bounded GUI
consumer uses a separate validated session delivery, never this result alone.
No batch loop: existing resolver/preflight owner checks are linear per selected
record. A library-wide bulk consumer needs a separately reviewed batch design.
"""
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import stat
import sqlite3
import time
from uuid import UUID

from audio_library_organizer.audio.identity import _tags, inspect_audio
from audio_library_organizer.domain.file_state import FileFacts, evaluate_file_state
from audio_library_organizer.metadata.change_history import metadata_revision
from audio_library_organizer.metadata.mp3_output import build_mp3_spec, observed_adoption_spec, compare_specs, TEXT_FIELDS
from audio_library_organizer.domain.output_spec import NAMESPACE, VERSION
from audio_library_organizer.storage.managed_bindings import evidence_digest
from audio_library_organizer.safety import windows_file_identity as windows_identity
from .legacy_adoption import _active_root, _source_context, _guard_file, _snapshot_value, binding_facts
from .managed_files import ReadContext, ReadPurpose, MaterialKind, SourceReadMaterial, resolve_read_path, recheck_read_path


@dataclass(frozen=True, slots=True)
class AssessmentRequest:
    library_id: str
    track_id: str
    binding_id: str
    operation_id: str
    generation: int
    policy_revision: str

    def __post_init__(self):
        for value in (self.library_id,self.track_id,self.binding_id,self.operation_id):
            UUID(value)
        if type(self.generation) is not int or self.generation < 0 or not self.policy_revision:
            raise ValueError('Incomplete live operation/policy context.')


@dataclass(frozen=True, slots=True)
class AssessmentGuard:
    request: AssessmentRequest
    metadata_revision: str
    binding_revision: str
    source_context: str
    material_identity: tuple
    contract: tuple = (NAMESPACE, VERSION)
    source_identity: tuple = ()
    owners_revision: str = ''
    windows_material: tuple = ()
    windows_database: object = None


@dataclass(frozen=True, slots=True)
class AdoptedAssessment:
    evaluation: object
    reason: str
    guard: AssessmentGuard | None = None
    difference: object = None


def _snapshot_key(snapshot):
    track = snapshot.track
    return evidence_digest({'library':snapshot.library_id,
        'metadata':metadata_revision(track) if track else None,
        'source':_source_context(track,snapshot.sources,snapshot.library_id) if track else None,
        'owners':[asdict(b) for b in snapshot.managed_bindings]})


def _no_reparse(path, root):
    # CPython3.11 has no Path.is_junction(). Inspect native attributes as well.
    path,root=Path(path).absolute(),Path(root).absolute()
    for p in (root,*reversed(path.parents[:len(path.relative_to(root).parts)-1]),path):
        if getattr(p.lstat(),'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise ValueError('REPARSE_POINT')
    return _guard_file(path,root)


def assess_adopted_mp3(repository, library_root, request: AssessmentRequest, *, current_request,
                       cancelled=None) -> AdoptedAssessment:
    """Point-in-time evidence; consumers MUST revalidate live context on delivery.

    current_request is a thread-safe live operation/configuration guard, never a
    default lambda supplied by production here. No asynchronous UI integration is
    implied: returning this result does not authorize caching it as current.
    This read preflight cannot lock out malicious concurrent processes.
    """
    at=time.time_ns()
    def refuse(reason):
        evaluation=evaluate_file_state(FileFacts(request.track_id,at))
        return AdoptedAssessment(replace(evaluation,reason=reason),reason)
    def live():
        return current_request is not None and current_request()==request and not (cancelled and cancelled())
    try:
        if not live(): return refuse('LIVE_CONTEXT_REQUIRED_OR_CHANGED')
        native_database=(windows_identity.capture(repository.database_path,mutable=True)
            if windows_identity.on_windows() else None)
        root=_active_root(repository,library_root)
        snapshot=repository.adopted_assessment_snapshot(request.track_id)
        if snapshot.library_id!=request.library_id or snapshot.track is None:
            return refuse('RECORD_OR_LIBRARY_MISMATCH')
        track=snapshot.track
        owners=[b for b in snapshot.managed_bindings if b.track_id==track.track_id]
        if len(owners)!=1 or owners[0].binding_id!=request.binding_id:
            return refuse('APPROVED_BINDING_REQUIRED')
        binding=owners[0];path=Path(binding.locator(root))
        if path.suffix.lower()!='.mp3': return refuse('ONLY_ADOPTED_MP3_SUPPORTED')
        # Positive, narrow placement contract. No prefix ignore rule and no
        # claim that an arbitrary nested historical directory is final output.
        if path.parent not in (root/'GOTOWE',root/'DO_SPRAWDZENIA',root/'NIE_WYBRANE'):
            return refuse('FINAL_PLACEMENT_UNCONFIRMED')
        source_context=_source_context(track,snapshot.sources,snapshot.library_id)
        expected_source={'locator':str(track.path),'source_id':track.source_id,
            'relative_path':track.source_relative_path,'source_context':source_context}
        if binding.source_binding!=expected_source:
            return refuse('SOURCE_CONTEXT_CHANGED')
        sources=[s for s in snapshot.sources if s.source_id==track.source_id and s.active]
        if len(sources)!=1: return refuse('SOURCE_CONTEXT_UNAVAILABLE')
        # Bind native change evidence to the material actually read below, not
        # to a later path observation at delivery preparation.
        native_before=(() if not windows_identity.on_windows() else (
            windows_identity.capture(track.path),windows_identity.capture(path)))
        source_stamp=_no_reparse(track.path,Path(sources[0].root_path))
        source_proof=inspect_audio(track.path,cancelled=cancelled)
        if (source_proof.status!='VALID' or source_proof.full_sha256!=track.sha256
                or source_proof.algorithm!=binding.audio_algorithm or source_proof.audio_digest!=binding.audio_digest
                or source_proof.stat_identity!=source_stamp or source_stamp[2:4]!=(track.size_bytes,track.mtime_ns)):
            return refuse('SOURCE_MATERIAL_UNCONFIRMED')
        stamp=_no_reparse(path,root)
        if stamp!=binding.stat_identity: return refuse('MANAGED_MATERIAL_CHANGED')
        payload=binding.applied_snapshot
        tags=payload.get('tag_snapshot')
        if (payload.get('version')!=1 or not isinstance(tags,dict)
                or any(not isinstance(tags.get(k),str) for k in (*TEXT_FIELDS,'cover_sha256'))
                or payload.get('relative_path')!=binding.relative_path
                or payload.get('full_sha256')!=binding.expected_sha256
                or payload.get('audio_algorithm')!=binding.audio_algorithm or payload.get('audio_digest')!=binding.audio_digest
                or payload.get('value')!=_snapshot_value(tags,binding.relative_path)):
            return refuse('APPLIED_SNAPSHOT_INCOMPLETE_OR_INCONSISTENT')
        facts=binding_facts(binding,track,root,at=at,current=True)
        context=ReadContext(snapshot.library_id,str(root),snapshot.sources,(facts,),
            tuple(b.read_proof(root) for b in snapshot.managed_bindings),
            (SourceReadMaterial.from_track(track),))
        plan=resolve_read_path(track,context,ReadPurpose.AUDIO_PROPERTIES,generation=request.generation)
        if plan.kind!=MaterialKind.MANAGED: return refuse('MANAGED_RESOLUTION_REQUIRED')
        proof=recheck_read_path(plan,cancelled=cancelled)
        if not proof.is_verified: return refuse(proof.reason_code)
        observed=_tags(path)
        if any(observed[k]!=tags[k] for k in (*TEXT_FIELDS,'cover_sha256')):
            return refuse('APPLIED_TAGS_INCONSISTENT')
        comparison=compare_specs(build_mp3_spec(track),observed_adoption_spec(payload))
        # Finish with a second actual SHA preflight; stat/name equality alone is
        # not accepted as a fresh confirmation after the metadata read.
        after=recheck_read_path(plan,cancelled=cancelled)
        if not after.is_verified or after.material_identity!=proof.material_identity:
            return refuse('MATERIAL_CHANGED_DURING_ASSESSMENT')
        if _no_reparse(path,root)!=stamp or _no_reparse(track.path,Path(sources[0].root_path))!=source_stamp:
            return refuse('MATERIAL_CHANGED_DURING_ASSESSMENT')
        if native_before:
            native_after=(windows_identity.capture(track.path),windows_identity.capture(path))
            if not all(windows_identity.same_material(a,b) for a,b in zip(native_before,native_after)):
                return refuse('WINDOWS_MATERIAL_CHANGED_DURING_ASSESSMENT')
        latest=repository.adopted_assessment_snapshot(request.track_id)
        if native_database is not None and not windows_identity.same_database(native_database,
                windows_identity.capture(repository.database_path,mutable=True)):
            return refuse('WINDOWS_DATABASE_CHANGED_DURING_ASSESSMENT')
        if _snapshot_key(latest)!=_snapshot_key(snapshot) or not live():
            return refuse('STALE_ASSESSMENT_CONTEXT')
        guard=AssessmentGuard(request,metadata_revision(track),evidence_digest(asdict(binding)),
                              source_context,after.material_identity,source_identity=source_stamp,
                              owners_revision=evidence_digest([asdict(b) for b in snapshot.managed_bindings]),
                              windows_material=native_before,windows_database=native_database)
        difference=comparison.as_difference(track.track_id,at)
        evaluation=evaluate_file_state(facts,difference=difference)
        return AdoptedAssessment(evaluation,'CONFIRMED_FIELD_DIFFERENCE' if difference else 'PARTIAL_MATCH_ONLY',guard,difference)
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,sqlite3.Error) as exc:
        # Fail closed, retain a classified diagnostic. No source fallback, no
        # automatic ownership and no cleanup on an uncertain read.
        return refuse('ASSESSMENT_UNRESOLVED:'+type(exc).__name__+':'+str(exc))
