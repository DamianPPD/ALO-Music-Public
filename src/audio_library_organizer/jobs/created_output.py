"""Receipts for files published by this export, never adoption of existing files.

The private-stage handle remains open across publication. Windows hands that
identity to deny-write/delete final-path protection before the SQLite transaction.
Only the current item finishes on stop; the next item is never started.
"""
from contextlib import contextmanager, ExitStack, closing
from dataclasses import asdict, replace
import ctypes
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from mutagen.id3 import ID3
from audio_library_organizer.audio.identity import inspect_audio, stat_identity, _tags
from audio_library_organizer.domain.file_state import OutputSnapshot, FileState
from audio_library_organizer.domain.output_spec import OutputSpec, OutputField, FieldAction, compare_specs
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.metadata.change_history import metadata_revision
from audio_library_organizer.metadata.mp3_output import build_mp3_spec
from audio_library_organizer.storage.managed_bindings import canonical_json, evidence_digest, read_managed_bindings, safe_relative
from audio_library_organizer.storage.source_registry import list_sources
from audio_library_organizer.storage.database import require_current_schema
from audio_library_organizer.safety import windows_file_identity as native
from audio_library_organizer.safety.windows_output_lease import WindowsOutputLease, guard_database_identity
from .legacy_adoption import (_active_root, _descriptors, _known_state, _source_context,
                              _guard_file, _snapshot_value, binding_facts)

PRODUCER = 'alo-export/v1'


def is_producer(binding):
    return binding.evidence.get('producer') == PRODUCER


def _native_object(proof):
    node=proof.leaf
    return [node.volume_guid,node.volume_serial,node.file_id.hex(),node.creation_time,node.directory]


@contextmanager
def protected_file(path, *, publishing=False):
    """Keep native ownership/cleanup policy without changing 6.2D leases."""
    if not native.on_windows():
        fd=os.open(path, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        try: yield fd, stat_identity(os.fstat(fd))
        finally: os.close(fd)
        return
    # Refuse quarantined handles and unsupported Windows capability via the
    # existing acquisition boundary before constructing this producer guard.
    from audio_library_organizer.safety.windows_output_lease import _QUARANTINE_LOCK, _UNCERTAIN_OWNERS
    with _QUARANTINE_LOCK:
        if _UNCERTAIN_OWNERS: raise OSError('WINDOWS_LEASE_CLEANUP_UNCERTAIN_RESTART_REQUIRED')
    if not native.positive_acceptance_enabled(): raise OSError('WINDOWS_POSITIVE_ACCEPTANCE_NOT_VERIFIED')
    class API(native._WinAPI):
        def open(self, name, *, mutable):
            if publishing and str(native._lexical(name)) == str(native._lexical(path)):
                # READ_DATA|READ_ATTRIBUTES, share READ|DELETE: rename is allowed,
                # content writers are denied. This handle pins the produced object.
                handle=self.create(name,0x81,0x5,None,3,0x02000000|0x00200000,None)
                if handle is None or handle==ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                return handle
            return super().open(name,mutable=mutable)
    api=API();owner=WindowsOutputLease((str(path),),api)
    try:
        proof,handles=native._open_path(str(path),api,owner=owner)
        yield (api,handles[-1]),proof
    finally: owner.close()


def observed_spec(path, relative):
    values=_tags(path);tags=ID3(path)
    values.update(track_number=str(tags.get('TRCK','')),disc_number=str(tags.get('TPOS','')),
                  discogs_url='')
    links=[f.url for f in tags.getall('WXXX') if f.desc.casefold()=='discogs']
    if len(links)>1: raise ValueError('Ambiguous output URL.')
    if links:values['discogs_url']=links[0]
    values['relative_path']=relative
    return OutputSpec(tuple(OutputField(k,FieldAction.SET,values[k]) for k in
        ('artist','title','album','year','genre','bpm','comment','track_number','disc_number',
         'discogs_url','cover_sha256','relative_path')),provenance=PRODUCER)


def _spec_data(spec):
    return {f.name: f.value if f.action==FieldAction.SET else '' for f in spec.fields}


def _plan_key(plan):
    return evidence_digest({'items':[(i.track.track_id,str(i.track.path),i.track.source_id,
        i.track.source_relative_path,i.track.sha256,i.track.size_bytes,i.track.mtime_ns,
        metadata_revision(i.track),str(i.destination_dir),i.filename,i.category)for i in plan.items],
        'summary':plan.summary,'folder':plan.folder_organization,'policy':plan.policy_revision})


class ProducerOperation:
    def __init__(self, repository, root, plan, known_libraries=()):
        self.repository=repository;self.root=_active_root(repository,root)
        self.plan=plan;self.plan_key=_plan_key(plan);self.operation_id=str(uuid4())
        snapshot=repository.file_check_snapshot(timeout=0)
        self.library_id=snapshot.library_id;self.sources=snapshot.sources
        self.known=_descriptors(repository,self.root,known_libraries)
        self.records={t.track_id:t for t in snapshot.tracks}
        self.bindings={b.track_id:b for b in snapshot.managed_bindings}
        self.database_token=stat_identity(repository.database_path.stat())[:2]
        self.native_database=native.capture(repository.database_path,mutable=True) if native.on_windows() else None
        self.manual_inputs={t.track_id:self.manual_input(t) for t in snapshot.tracks if t.manual_cover_path}
        for item in plan.items:self.validate_item(item)

    @staticmethod
    def manual_input(track):
        path=Path(track.manual_cover_path)
        if not path.is_file():return None
        with path.open('rb') as stream:
            before=stat_identity(os.fstat(stream.fileno()))
            digest=hashlib.sha256(stream.read()).hexdigest()
            if stat_identity(path.stat())!=before:raise ValueError('Manual cover changed while reading.')
        return before,digest

    def validate_item(self,item,conn=None):
        if _plan_key(self.plan)!=self.plan_key:raise ValueError('Export plan changed.')
        track=item.track;original=self.records.get(track.track_id)
        if original is None:raise ValueError('Track not in pinned library.')
        if conn is None:
            snapshot=self.repository.adopted_assessment_snapshot(track.track_id,timeout=0)
            library_id,sources,current=snapshot.library_id,snapshot.sources,snapshot.track
        else:
            library_id=conn.execute('SELECT library_id FROM library_metadata WHERE singleton=1').fetchone()[0]
            sources=tuple(list_sources(conn))
            row=conn.execute('SELECT * FROM tracks WHERE track_id=?',(track.track_id,)).fetchone()
            current=self.repository._row_to_track(row) if row else None
        if (library_id!=self.library_id or sources!=self.sources or current is None
                or metadata_revision(current)!=metadata_revision(original)
                or metadata_revision(track)!=metadata_revision(original)
                or _source_context(current,sources,library_id)!=_source_context(original,self.sources,self.library_id)
                or _source_context(track,sources,library_id)!=_source_context(original,self.sources,self.library_id)):
            raise ValueError('Pinned library, track, metadata or source binding changed.')
        if current.manual_cover_path and self.manual_input(current)!=self.manual_inputs[current.track_id]:
            raise ValueError('Pinned manual cover changed.')
        from .exporter import ExportPlan
        expected=ExportPlan.from_tracks([current],LibraryPaths(self.root),folder_organization=self.plan.folder_organization).items[0]
        if (item.destination_dir,item.filename,item.category)!=(expected.destination_dir,expected.filename,expected.category):
            raise ValueError('Output routing changed.')
        if stat_identity(self.repository.database_path.stat())[:2]!=self.database_token:
            raise ValueError('Library database replaced.')
        if self.native_database is not None and not native.same_database(self.native_database,
                native.capture(self.repository.database_path,mutable=True)):
            raise ValueError('Native library database replaced.')
        return current

    @contextmanager
    def item(self,item):
        self.validate_item(item)
        with protected_file(item.track.path) as source_pin:
            source=next(s for s in self.sources if s.source_id==item.track.source_id and s.active)
            stamp=_guard_file(item.track.path,source.root_path)
            proof=inspect_audio(item.track.path)
            if (proof.status!='VALID' or proof.full_sha256!=item.track.sha256
                    or proof.stat_identity!=stamp or stamp[2:4]!=(item.track.size_bytes,item.track.mtime_ns)
                    or (not native.on_windows() and stat_identity(os.fstat(source_pin[0]))!=stamp)):
                raise ValueError('Source audio identity unverified.')
            yield Receipt(self,item,source,proof,source_pin)


class Receipt:
    def __init__(self,operation,item,source,proof,source_pin):
        self.operation=operation;self.item=item;self.source=source;self.source_proof=proof
        self.cover=None;self.final_sha='';self.binding=None
        self.source_pin=source_pin

    @contextmanager
    def publication(self,staged):
        with protected_file(staged,publishing=True) as pin:
            staged_proof=inspect_audio(staged)
            if (staged_proof.status!='VALID' or staged_proof.full_sha256!=self.final_sha
                    or staged_proof.audio_digest!=self.source_proof.audio_digest):
                raise ValueError('Produced audio did not match source and final SHA.')
            self.staged_proof=staged_proof
            self.spec=observed_spec(staged,'pending')
            expected=build_mp3_spec(self.item.track,cover_bytes=self.cover[0] if self.cover else None,relative_path='pending')
            fields=[]
            for field in expected.fields:
                if field.action==FieldAction.PRESERVE:
                    field=OutputField(field.name,FieldAction.SET,self.source_proof.tag_snapshot[field.name])
                elif field.name=='cover_sha256' and field.action==FieldAction.UNKNOWN:
                    field=OutputField(field.name,FieldAction.SET,self.source_proof.tag_snapshot['cover_sha256'])
                fields.append(field)
            if not compare_specs(OutputSpec(tuple(fields)),self.spec).complete_match:
                raise ValueError('Produced OutputSpec differs from the pinned writer policy.')
            yield lambda target:self.register(target,pin)

    def register(self,target,pin):
        op=self.operation;repo=op.repository;target=Path(target)
        # Hand off the still-open producer object to final-path deny-delete/write.
        with ExitStack() as guards:
            final_pin=guards.enter_context(protected_file(target))
            if native.on_windows():
                api,h=pin[0];produced=api.query(h);final=native.capture(target)
                if produced.object_identity!=pin[1].leaf.object_identity or produced!=final.leaf:
                    raise ValueError('Published object differs from producer handle.')
                for descriptor in op.known:guards.enter_context(guard_database_identity(descriptor.database))
            else:
                if stat_identity(os.fstat(pin[0]))[:2]!=pin[1][:2] or _guard_file(target,op.root)[:2]!=pin[1][:2]:
                    raise ValueError('Published object differs from producer descriptor.')
            stamp=_guard_file(target,op.root)
            if not native.on_windows() and (stamp[:2]!=pin[1][:2]
                    or stat_identity(os.fstat(pin[0]))!=stamp
                    or stat_identity(os.fstat(final_pin[0]))!=stamp):
                raise ValueError('Published object changed during producer handoff.')
            proof=inspect_audio(target)
            if (proof.status!='VALID' or proof.full_sha256!=self.final_sha or proof.stat_identity!=stamp
                    or proof.audio_digest!=self.source_proof.audio_digest):
                raise ValueError('Published MP3 changed or failed verification.')
            relative=target.relative_to(op.root).as_posix();safe_relative(relative)
            actual=observed_spec(target,relative)
            expected=replace(self.spec,fields=tuple(OutputField(f.name,FieldAction.SET,relative)
                if f.name=='relative_path' else f for f in self.spec.fields))
            if not compare_specs(expected,actual).complete_match:raise ValueError('Published OutputSpec changed.')
            with closing(sqlite3.connect(repo.database_path.absolute().as_uri()+'?mode=rw',uri=True,timeout=0))as conn,conn:
                conn.row_factory=sqlite3.Row;conn.execute('PRAGMA foreign_keys=ON');aliases={}
                for index,descriptor in enumerate(op.known):
                    alias='main' if Path(descriptor.database)==repo.database_path.absolute() else f'known_{index}'
                    if alias!='main':conn.execute(f'ATTACH DATABASE ? AS {alias}',(Path(descriptor.database).as_uri()+'?mode=rw',))
                    aliases[descriptor.database]=alias
                conn.execute('BEGIN IMMEDIATE');require_current_schema(conn)
                _,owners=_known_state(op.known,conn=conn,aliases=aliases)
                current=op.validate_item(self.item,conn)
                if conn.execute('SELECT 1 FROM managed_bindings WHERE track_id=?',(current.track_id,)).fetchone():
                    raise ValueError('Track already owns a managed output.')
                key=str(target)
                from .managed_files import lexical_locator
                key=lexical_locator(key)
                if any(key==lexical_locator(p) or stamp[:2]==(dev,ino)for _,_,p,dev,ino in owners):
                    raise ValueError('Published output already has an owner.')
                source_now=inspect_audio(current.path)
                if (source_now.status!='VALID' or source_now!=self.source_proof
                        or _guard_file(current.path,self.source.root_path)!=self.source_proof.stat_identity):
                    raise ValueError('Source changed before ownership commit.')
                at=time.time_ns();binding_id=str(uuid4())
                applied={'version':1,'tag_snapshot':proof.tag_snapshot,'relative_path':relative,
                    'value':_snapshot_value(proof.tag_snapshot,relative),'full_sha256':proof.full_sha256,
                    'audio_algorithm':proof.algorithm,'audio_digest':proof.audio_digest,
                    'producer_spec':_spec_data(actual)}
                source_context=_source_context(current,op.sources,op.library_id)
                source_binding={'locator':str(current.path),'source_id':current.source_id,
                    'relative_path':current.source_relative_path,'source_context':source_context}
                evidence={'producer':PRODUCER,'operation_id':op.operation_id,'plan_digest':op.plan_key,
                    'record_revision':metadata_revision(current),'policy_revision':op.plan.policy_revision,
                    'source_audio_digest':proof.audio_digest,'source_sha256':source_now.full_sha256}
                if native.on_windows():evidence['native_object']=_native_object(final)
                conn.execute('INSERT INTO managed_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (current.track_id,op.library_id,binding_id,relative,key,proof.full_sha256,proof.algorithm,
                     proof.audio_digest,stamp[0],stamp[1],canonical_json(stamp),canonical_json(source_binding),
                     canonical_json(applied),canonical_json(evidence),at))
                binding=next(b for b in read_managed_bindings(conn)if b.track_id==current.track_id)
                from audio_library_organizer.storage.file_state_cache import write_file_facts
                facts=producer_history(binding,current,op.root,at=at)
                from audio_library_organizer.domain.file_state import FileObservation, FileAvailability
                token=OutputSnapshot('alo.produced-mp3-spec',1,evidence_digest(_spec_data(actual)))
                facts=replace(facts,is_current=True,desired=token,applied=token,
                    managed=replace(facts.managed,is_current=True,reason='PRODUCER_OUTPUT_VERIFIED'),
                    source=FileObservation(current.track_id,str(current.path),FileAvailability.PRESENT,at,current.source_id,
                                           'PRODUCER_SOURCE_VERIFIED'))
                # A receipt is historical evidence. It never grants a P session.
                write_file_facts(conn,facts)
                op.validate_item(self.item,conn)
                if (_guard_file(target,op.root)!=stamp or _guard_file(current.path,self.source.root_path)!=source_now.stat_identity
                        or hashlib.sha256(target.read_bytes()).hexdigest()!=proof.full_sha256):
                    raise ValueError('Material changed before ownership commit.')
                if not native.on_windows() and (stat_identity(os.fstat(pin[0]))!=stamp
                        or stat_identity(os.fstat(final_pin[0]))!=stamp
                        or stat_identity(os.fstat(self.source_pin[0]))!=source_now.stat_identity):
                    raise ValueError('Producer descriptors changed before ownership commit.')
                conn.commit()  # Still inside every source, produced-file and DB guard.
                self.binding=binding


def producer_history(binding,track,root,*,at=None):
    """History only; neither a stored spec nor this function proves current P."""
    facts=binding_facts(binding,track,root,at=at,current=False)
    return facts


def producer_check(binding,track,root,*,at,policy_revision,cancelled):
    from audio_library_organizer.domain.file_state import FileAvailability, ConflictReason
    facts=producer_history(binding,track,root,at=at)
    if cancelled():return facts
    path=Path(binding.locator(root))
    try:
        with protected_file(path) as live_pin:
            stamp=_guard_file(path,root);proof=inspect_audio(path,cancelled=cancelled)
            native_changed=(native.on_windows() and binding.evidence.get('native_object') is not None
                            and _native_object(live_pin[1])!=binding.evidence['native_object'])
            if (native_changed or stamp[:2]!=binding.stat_identity[:2] or (proof.status=='VALID' and proof.stat_identity==stamp
                    and (proof.full_sha256!=binding.expected_sha256 or proof.audio_digest!=binding.audio_digest))):
                return replace(facts,is_current=True,conflict=ConflictReason.CONTRADICTORY_FACTS,
                    managed=replace(facts.managed,is_current=True,availability=FileAvailability.PRESENT,
                                    reason='PRODUCER_OUTPUT_IDENTITY_CHANGED'))
            if (proof.status!='VALID' or proof.stat_identity!=stamp or stamp!=binding.stat_identity
                    or (native.on_windows() and binding.evidence.get('native_object') is None)):
                raise ValueError('Producer output material changed.')
            payload=binding.applied_snapshot;spec=observed_spec(path,binding.relative_path)
            if _spec_data(spec)!=payload.get('producer_spec'):raise ValueError('Producer OutputSpec changed.')
            # This bulk check does not resolve today's cover/routing directives
            # or perform the bounded P delivery protocol. Keep the receipt H.
            return replace(facts,is_current=True,managed=replace(facts.managed,is_current=True,
                availability=FileAvailability.PRESENT,reason='PRODUCER_OUTPUT_RECHECKED'),desired=None)
    except (OSError,ValueError,RuntimeError,KeyError,sqlite3.Error) as exc:
        return replace(facts,is_current=True,managed=replace(facts.managed,is_current=True,
            availability=FileAvailability.UNKNOWN,reason='PRODUCER_RECHECK_REFUSED:'+str(exc)))
