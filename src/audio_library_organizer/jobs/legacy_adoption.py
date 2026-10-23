"""Read-only legacy output inventory and explicit, database-only adoption.

CSV, names, markers and fingerprints never create ownership. A proposal needs
one record, one verified MP3 and one matching source identity. Approval repeats
the whole inventory, reserves all known library databases, and validates again.
Only SQLite is written; music is never copied, tagged, renamed or removed.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from dataclasses import asdict, dataclass, replace
import csv
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from uuid import UUID, uuid4

from audio_library_organizer.audio.identity import ALGORITHM, inspect_audio, stat_identity
from audio_library_organizer.domain.settings import LibraryPaths
from audio_library_organizer.jobs.managed_files import lexical_locator, source_material_revision
from audio_library_organizer.metadata.change_history import metadata_revision
from audio_library_organizer.storage.database import require_current_schema
from audio_library_organizer.storage.managed_bindings import (
    ManagedBinding, canonical_json, evidence_digest, read_managed_bindings, safe_relative, valid_digest,
)
from audio_library_organizer.storage.source_registry import list_sources

AUDIO_SUFFIXES = {'.mp3','.wav','.flac','.m4a','.aac','.ogg','.opus','.aiff','.wma'}
MAX_KNOWN_DATABASES = 10  # SQLite's portable minimum for attached databases.


@dataclass(frozen=True, slots=True)
class KnownLibrary:
    root: str
    database: str
    library_id: str | None = None


@dataclass(frozen=True, slots=True)
class AdoptionProposal:
    proposal_id: str
    run_id: str
    library_id: str
    track_id: str | None
    source_id: str | None
    locator: str
    library_root: str
    status: str
    reason_codes: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    checked_at: int
    record_revision: str = ''
    source_context: str = ''
    full_sha256: str = ''
    audio_digest: str = ''
    audio_algorithm: str = ALGORITHM
    stat_identity: tuple = ()
    tag_snapshot: dict | None = None

    @property
    def can_adopt(self):
        return self.status == 'CANDIDATE' and bool(self.track_id)


@dataclass(frozen=True, slots=True)
class AdoptionInventory:
    run_id: str
    library_id: str
    library_root: str
    checked_at: int
    proposals: tuple[AdoptionProposal, ...]
    blocked_track_ids: tuple[str, ...]
    root_observations: tuple[tuple[str, str], ...]
    known_libraries: tuple[KnownLibrary, ...]
    context_digest: str
    source_references: tuple[tuple[str, dict], ...]
    cancelled: bool = False

    @property
    def statistics(self):
        result = {name.lower(): sum(p.status == name for p in self.proposals)
                  for name in ('CANDIDATE','CONFLICT','UNRESOLVED','UNSUPPORTED','ALREADY_BOUND')}
        result['adopted'] = 0
        return result


def _rw(repository):
    conn = sqlite3.connect(repository.database_path.absolute().as_uri()+'?mode=rw', uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def _guard_file(path, root):
    """Reject symlinks/junctions/hardlinks instead of claiming alias ownership."""
    root, path = Path(root).absolute(), Path(path).absolute()
    relative = path.relative_to(root)
    if not relative.parts or '..' in relative.parts:
        raise ValueError('Candidate outside declared root.')
    current = root
    for item in (None, *relative.parts):
        if item is not None:
            current = current/item
        value = current.lstat()
        if stat.S_ISLNK(value.st_mode) or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('SYMLINK_OR_REPARSE_ALIAS')
        if current != path and not stat.S_ISDIR(value.st_mode):
            raise ValueError('ROOT_NOT_A_DIRECTORY')
    value = path.stat()
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1 or not value.st_ino:
        raise ValueError('HARDLINK_OR_NONREGULAR_ALIAS')
    # Resolve only after all components have passed no-follow inspection.
    if root.resolve(strict=True) != root or path.resolve(strict=True) != path:
        raise ValueError('ROOT_OR_PATH_ALIAS')
    return stat_identity(value)


def _active_root(repository, root):
    root = Path(root).absolute()
    if lexical_locator(repository.database_path.absolute()) != lexical_locator(root/'.alo'/'library.sqlite3'):
        raise ValueError('Wrong library root/database context.')
    return root


def _source_context(track, sources, library_id):
    source = next((s for s in sources if s.source_id == track.source_id and s.library_id == library_id), None)
    return evidence_digest({'library_id':library_id, 'track_id':track.track_id,
        'locator':str(track.path), 'source_id':track.source_id, 'relative':track.source_relative_path,
        'source':asdict(source) if source else None, 'material':source_material_revision(track)})


def _descriptors(repository, root, known):
    items = [KnownLibrary(str(root), str(repository.database_path.absolute()))]
    items.extend(known)
    unique = {}
    for item in items:
        if not isinstance(item, KnownLibrary):
            raise ValueError('Known libraries require explicit root/database descriptors.')
        key = str(Path(item.database).resolve(strict=True))
        if key in unique:
            old = unique[key]
            if Path(old.root).resolve() != Path(item.root).resolve():
                raise ValueError('One known database has conflicting library roots.')
            if old.library_id and item.library_id and old.library_id != item.library_id:
                raise ValueError('One known database has conflicting library UUIDs.')
            if item.library_id and not old.library_id:
                unique[key] = replace(old, library_id=item.library_id)
            continue
        unique[key] = KnownLibrary(str(Path(item.root).absolute()), key, item.library_id)
    if len(unique) > MAX_KNOWN_DATABASES:
        raise ValueError('Known library set exceeds safe SQLite reservation capacity.')
    return tuple(sorted(unique.values(), key=lambda item:item.database))


class _SchemaReader:
    """Run existing read-only schema validators against a reserved attachment."""
    def __init__(self, connection, schema):
        if not re.fullmatch(r'(main|known_[0-9]+)', schema):
            raise ValueError('Invalid known database attachment.')
        self.connection, self.schema = connection, schema

    def execute(self, sql, parameters=()):
        if sql.startswith('PRAGMA '):
            sql = 'PRAGMA ' + self.schema + '.' + sql[7:]
        else:
            tables={'tracks','sources','library_metadata','file_state_cache','sqlite_master',
                    'source_audio_references','legacy_adoption_runs','legacy_adoption_proposals','managed_bindings'}
            def qualify(match):
                if match[2].lower() not in tables:
                    raise ValueError('Unexpected schema validation table.')
                return match[1] + ' ' + self.schema + '.' + match[2]
            sql = re.sub(r'(?i)\b(FROM|JOIN)\s+(\w+)', qualify, sql)
        return self.connection.execute(sql, parameters)


def _validate_known(reader, version):
    from audio_library_organizer.storage.database import check_integrity
    from audio_library_organizer.storage.migrations import validate_track_ids
    from audio_library_organizer.storage.source_registry import validate_source_schema
    from audio_library_organizer.storage.file_state_cache import validate_file_state_schema
    from audio_library_organizer.storage.managed_bindings import validate_managed_schema
    check_integrity(reader)
    validate_track_ids(reader)
    validate_source_schema(reader)
    validate_file_state_schema(reader)
    if version == 4:
        validate_managed_schema(reader)
        read_managed_bindings(reader)


def _known_state(descriptors, *, conn=None, aliases=None):
    states, owners = [], []
    for item in descriptors:
        own = conn is None
        reader = sqlite3.connect(Path(item.database).as_uri()+'?mode=ro',uri=True) if own else conn
        try:
            reader.row_factory = sqlite3.Row
            prefix = '' if own else aliases[item.database]+'.'
            version = reader.execute(f'PRAGMA {prefix}user_version').fetchone()[0]
            if version not in (3,4):
                raise ValueError('Unknown/newer known library schema.')
            _validate_known(reader if own else _SchemaReader(reader, aliases[item.database]), version)
            library_id = reader.execute(f'SELECT library_id FROM {prefix}library_metadata WHERE singleton=1').fetchone()[0]
            UUID(library_id)
            if item.library_id and library_id != item.library_id:
                raise ValueError('Known library identity changed.')
            rows = []
            if version == 4:
                rows = [dict(row) for row in reader.execute(f'SELECT * FROM {prefix}managed_bindings ORDER BY track_id')]
            observations=[]
            for row in rows:
                if row['library_id'] != library_id or not valid_digest(row['expected_sha256']):
                    raise ValueError('Invalid known library ownership evidence.')
                locator = str(Path(item.root).joinpath(*safe_relative(row['relative_path']).parts))
                if lexical_locator(locator)!=row['locator_key']:
                    raise ValueError('Known managed binding belongs to another library root.')
                owners.append((library_id,row['track_id'],locator,row['device'],row['inode']))
                try:
                    token=_guard_file(locator,item.root)
                except FileNotFoundError:
                    token=None
                if token is not None:
                    owners.append((library_id,row['track_id'],locator,token[0],token[1]))
                observations.append((row['track_id'],token))
            states.append({'root':item.root,'database':item.database,'library_id':library_id,'version':version,
                           'bindings':rows,'owned_observations':observations})
        finally:
            if own:
                reader.close()
    ids=[state['library_id'] for state in states]
    if len(set(ids))!=len(ids):
        raise ValueError('Duplicate library UUID in different known databases.')
    return states, tuple(owners)


def _context(repository, known_states, conn=None):
    own = conn is None
    if own:
        conn = sqlite3.connect(repository.database_path.absolute().as_uri()+'?mode=ro',uri=True)
        conn.row_factory=sqlite3.Row
        conn.execute('BEGIN')
    try:
        require_current_schema(conn)
        library_id=conn.execute('SELECT library_id FROM library_metadata WHERE singleton=1').fetchone()[0]
        sources=tuple(list_sources(conn))
        tracks=tuple(repository._row_to_track(row) for row in conn.execute('SELECT * FROM tracks ORDER BY track_id'))
        token=evidence_digest({'library_id':library_id,'sources':[asdict(s) for s in sources],
            'tracks':[(t.track_id,metadata_revision(t),_source_context(t,sources,library_id)) for t in tracks],
            'known':known_states})
        return library_id,sources,tracks,token
    finally:
        if own:
            conn.close()


def _report_evidence(root, files, *, cancelled=None):
    cancelled = cancelled or (lambda: False)
    evidence=defaultdict(list)
    directory=root/'raporty'
    if cancelled():
        return evidence
    if not directory.is_dir() or directory.is_symlink():
        return evidence
    for report in sorted(directory.glob('*.csv')):
        if cancelled():
            return evidence
        try:
            if report.is_symlink() or report.stat().st_size > 16*1024*1024:
                continue
            with report.open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream)
                if not {'source_path','destination_path'} <= set(reader.fieldnames or ()):
                    continue
                for i,row in enumerate(reader):
                    if cancelled():
                        return evidence
                    if i>100000:
                        break
                    try:
                        destination=lexical_locator(row.get('destination_path',''))
                    except ValueError:
                        continue
                    if destination in files:
                        evidence[destination].append('CSV:'+str(report)+':'+row.get('source_path',''))
        except (OSError,ValueError,UnicodeError,csv.Error):
            continue
    return evidence


def _physical_inventory(root, cancelled):
    files, outcomes = [], []
    for directory in (root/'GOTOWE',root/'DO_SPRAWDZENIA',root/'NIE_WYBRANE'):
        if cancelled():
            return files,outcomes
        try:
            root_stat=root.lstat()
            if not stat.S_ISDIR(root_stat.st_mode) or root.is_symlink():
                raise OSError('Library volume/root unavailable.')
            if not directory.exists():
                outcomes.append((str(directory),'EMPTY_ACCESSIBLE_ROOT'))
                continue
            failures=[]
            def onerror(error): failures.append(str(error))
            for parent,dirs,names in os.walk(directory,followlinks=False,onerror=onerror):
                if cancelled():
                    return files,outcomes
                safe_dirs=[]
                for name in sorted(dirs):
                    if cancelled():
                        return files,outcomes
                    child=Path(parent)/name
                    if child.is_symlink() or (hasattr(child,'is_junction') and child.is_junction()):
                        failures.append('Directory alias: '+str(child))
                    else:
                        safe_dirs.append(name)
                dirs[:]=safe_dirs
                for name in sorted(names):
                    if cancelled():
                        return files,outcomes
                    path=Path(parent)/name
                    if path.suffix.lower() in AUDIO_SUFFIXES:
                        files.append(path.absolute())
            outcomes.append((str(directory),'ERROR' if failures else 'SUCCESS'))
        except (OSError,RuntimeError):
            outcomes.append((str(directory),'OFFLINE'))
    return sorted(files),outcomes


def inventory_legacy_outputs(repository, *, library_root, known_libraries=(), cancelled=None,
                             progress=None, persist=True, phase=None) -> AdoptionInventory:
    cancelled=cancelled or (lambda:False)
    root=_active_root(repository,library_root)
    run_id=str(uuid4()); at=time.time_ns()
    library_id, descriptors, context = '', (), ''

    def stopped():
        # Partial evidence must never reach the creation/adoption guard as a
        # complete inventory. No observations are persisted on this path.
        return AdoptionInventory(run_id,library_id,str(root),at,(),(),(),descriptors,context,(),True)

    if cancelled():
        return stopped()
    if phase: phase('context')
    known_error=''
    try:
        descriptors=_descriptors(repository,root,known_libraries)
        states,owners=_known_state(descriptors)
    except (OSError,ValueError,sqlite3.Error,TypeError,RuntimeError) as exc:
        known_error='KNOWN_LIBRARY_UNAVAILABLE: '+str(exc)
        descriptors=(); states=[]; owners=()
    if cancelled():
        return stopped()
    library_id,sources,tracks,context=_context(repository,states)
    if cancelled():
        return stopped()
    bindings={b.track_id:b for b in repository.list_managed_bindings()}
    with closing(sqlite3.connect(repository.database_path.absolute().as_uri()+'?mode=ro',uri=True)) as conn:
        references={row[0]:(row[1],row[2]) for row in conn.execute('SELECT track_id,context_digest,evidence_json FROM source_audio_references')}
    trusted={}; fresh_references=[]
    if phase: phase('sources')
    for i,track in enumerate(tracks):
        if cancelled(): break
        if progress: progress(i,len(tracks),str(track.path))
        if cancelled(): break
        source=next((s for s in sources if s.source_id==track.source_id and s.library_id==library_id),None)
        key=_source_context(track,sources,library_id)
        previous=references.get(track.track_id)
        try:
            if source is None or not valid_digest(track.sha256):
                if progress: progress(i+1,len(tracks),str(track.path))
                continue
            if Path(track.path).exists():
                stamp=_guard_file(track.path,source.root_path)
                proof=inspect_audio(track.path,cancelled=cancelled)
                if (proof.status=='VALID' and proof.full_sha256==track.sha256
                        and stamp==proof.stat_identity and (stamp[2],stamp[3])==(track.size_bytes,track.mtime_ns)):
                    ref={'source_context':key,'full_sha256':proof.full_sha256,'audio_digest':proof.audio_digest,
                         'algorithm':proof.algorithm,'stat_identity':stamp,'source_id':track.source_id,
                         'source_locator':str(track.path),'library_id':library_id,'track_id':track.track_id,
                         'observed_at':at,'kind':'VERIFIED_SOURCE'}
                    trusted[track.track_id]=ref; fresh_references.append((track.track_id,ref))
            elif previous and previous[0]==key:
                ref=json.loads(previous[1])
                if (ref.get('source_context')==key and ref.get('full_sha256')==track.sha256
                    and ref.get('library_id')==library_id and ref.get('track_id')==track.track_id
                    and ref.get('source_id')==track.source_id and ref.get('source_locator')==str(track.path)
                    and ref.get('algorithm')==ALGORITHM and valid_digest(ref.get('audio_digest'))
                    and ref.get('kind')=='VERIFIED_SOURCE'):
                    trusted[track.track_id]=ref
        except (OSError,ValueError,RuntimeError,TypeError):
            pass
        if progress: progress(i+1,len(tracks),str(track.path))
    if cancelled():
        return stopped()
    if phase: phase('inventory')
    files,outcomes=_physical_inventory(root,cancelled)
    if cancelled():
        return stopped()
    if phase: phase('reports')
    reports=_report_evidence(root,{lexical_locator(p) for p in files},cancelled=cancelled)
    if cancelled():
        return stopped()
    if phase: phase('outputs')
    proposals=[]
    for index,path in enumerate(files):
        if cancelled(): break
        if progress: progress(index,len(files),str(path))
        if cancelled(): break
        locator=str(path); key=lexical_locator(path)
        evidence=tuple(reports.get(key,()))+('OUTPUT_INVENTORY',)
        reason=''; proof=None
        try:
            _guard_file(path,root)
            proof=inspect_audio(path,cancelled=cancelled)
        except (OSError,ValueError,RuntimeError) as exc:
            reason=str(exc)
        matching=[t for t in tracks if proof and proof.status=='VALID' and t.track_id in trusted
                  and trusted[t.track_id]['audio_digest']==proof.audio_digest
                  and trusted[t.track_id]['algorithm']==proof.algorithm]
        if not matching:
            status='CONFLICT' if reason else 'UNSUPPORTED' if proof and proof.status=='UNSUPPORTED' else 'UNRESOLVED'
            proposals.append(AdoptionProposal(str(uuid4()),run_id,library_id,None,None,locator,str(root),status,
                (reason or (proof.reason if proof and proof.status!='VALID' else 'NO_TRUSTED_SOURCE_MATCH'),),
                evidence,at,full_sha256=proof.full_sha256 or '' if proof else '',
                audio_digest=proof.audio_digest or '' if proof else '',stat_identity=proof.stat_identity if proof else ()))
            if progress: progress(index+1,len(files),str(path))
            continue
        for track in matching:
            reasons=[]
            status='CANDIDATE'
            if track.track_id in bindings:
                bound=bindings[track.track_id]
                status='ALREADY_BOUND' if key==bound.locator_key and proof.full_sha256==bound.expected_sha256 else 'CONFLICT'
                reasons.append('EXISTING_MANAGED_BINDING')
            if len(matching)>1:
                status='CONFLICT'; reasons.append('MULTIPLE_RECORD_OWNERS')
            if key==lexical_locator(track.path):
                status='CONFLICT'; reasons.append('SOURCE_AS_OUTPUT')
            for owner_library,owner_track,owner_path,device,inode in owners:
                if (key==lexical_locator(owner_path) or proof.stat_identity[:2]==(device,inode)) and (owner_library,owner_track)!=(library_id,track.track_id):
                    status='CONFLICT'; reasons.append('FOREIGN_OWNER')
            for state in states:
                if state['library_id']!=library_id and path.is_relative_to(Path(state['root'])):
                    status='CONFLICT'; reasons.append('FOREIGN_LIBRARY_ROOT')
            markers=(proof.tag_snapshot or {}).get('markers',{})
            marker_tracks=[value for name,values in markers.items() if 'TRACK' in name.upper() for value in values]
            marker_libraries=[value for name,values in markers.items() if 'LIBRARY' in name.upper() for value in values]
            if (any(value!=track.track_id for value in marker_tracks)
                    or any(value!=library_id for value in marker_libraries)):
                status='CONFLICT'; reasons.append('FOREIGN_UUID_MARKER')
            if known_error or any(status in ('OFFLINE','ERROR') for _,status in outcomes):
                status='UNRESOLVED'; reasons.append(known_error or 'INCOMPLETE_OUTPUT_INVENTORY')
            proposals.append(AdoptionProposal(str(uuid4()),run_id,library_id,track.track_id,track.source_id,
                locator,str(root),status,tuple(reasons or ['AUDIO_IDENTITY_MATCH']),
                evidence+('VERIFIED_SOURCE_AUDIO',),at,metadata_revision(track),
                _source_context(track,sources,library_id),proof.full_sha256,proof.audio_digest,proof.algorithm,
                proof.stat_identity,proof.tag_snapshot))
        if progress: progress(index+1,len(files),str(path))
    if cancelled():
        return stopped()
    if any(p.track_id is None and p.status=='CONFLICT' for p in proposals):
        proposals=[replace(p,status='CONFLICT',reason_codes=('UNRESOLVED_OUTPUT_ALIAS',))
                   if p.can_adopt else p for p in proposals]
    grouped=defaultdict(list)
    for i,p in enumerate(proposals):
        if p.track_id and p.locator: grouped[p.track_id].append(i)
    for positions in grouped.values():
        if len(positions)>1:
            for i in positions:
                if proposals[i].can_adopt:
                    proposals[i]=replace(proposals[i],status='CONFLICT',reason_codes=('MULTIPLE_LEGACY_OUTPUTS',))
    assigned={p.track_id for p in proposals if p.track_id}
    for track in tracks:
        if cancelled():
            return stopped()
        if track.track_id not in assigned:
            bound=bindings.get(track.track_id)
            status='ALREADY_BOUND' if bound else 'UNRESOLVED'
            proposals.append(AdoptionProposal(str(uuid4()),run_id,library_id,track.track_id,track.source_id,
                bound.locator(root) if bound else '',str(root),status,
                ('EXISTING_MANAGED_BINDING' if bound else 'NO_UNIQUE_TRUSTED_CANDIDATE',),(),at,
                metadata_revision(track),_source_context(track,sources,library_id)))
    result=AdoptionInventory(run_id,library_id,str(root),at,tuple(proposals),
        tuple(sorted({p.track_id for p in proposals if p.track_id and p.status in ('CONFLICT','UNRESOLVED','UNSUPPORTED')})),
        tuple(outcomes),descriptors,context,tuple(fresh_references),cancelled())
    if persist and not result.cancelled:
        if phase: phase('saving')
        if cancelled():
            return stopped()
        with closing(_rw(repository)) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            if cancelled(): raise InterruptedError('Inventory cancelled before database commit.')
            fresh_states,_=_known_state(descriptors) if descriptors else ([],())
            if _context(repository,fresh_states,conn)[3]!=context:
                raise ValueError('Library/record context changed during inventory.')
            if cancelled(): raise InterruptedError('Inventory cancelled before database commit.')
            conn.execute('INSERT INTO legacy_adoption_runs VALUES (?,?,?,?,?)',
                (run_id,library_id,context,canonical_json({'known_libraries':[asdict(k) for k in descriptors],
                    'root_observations':outcomes,'library_root':str(root)}),at))
            for track_id,reference in fresh_references:
                if cancelled(): raise InterruptedError('Inventory cancelled before database commit.')
                conn.execute('INSERT INTO source_audio_references VALUES (?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET '
                    'library_id=excluded.library_id,context_digest=excluded.context_digest,evidence_json=excluded.evidence_json,observed_at=excluded.observed_at',
                    (track_id,library_id,reference['source_context'],canonical_json(reference),at))
            for proposal in proposals:
                if cancelled(): raise InterruptedError('Inventory cancelled before database commit.')
                conn.execute('INSERT INTO legacy_adoption_proposals VALUES (?,?,?,?,?,?)',
                    (proposal.proposal_id,run_id,proposal.track_id,lexical_locator(proposal.locator) if proposal.locator else '',
                     proposal.status,canonical_json(asdict(proposal))))
            if cancelled(): raise InterruptedError('Inventory cancelled before database commit.')
    return result


def _snapshot_value(tags, relative):
    # An actual observed output snapshot, not the raw file SHA/source digest.
    return evidence_digest({'version':1,'tags':{k:tags.get(k,'') for k in
        ('artist','title','album','year','genre','bpm','comment','cover_sha256')},'relative_path':relative})


def _output_membership(root, cancelled):
    files,outcomes=_physical_inventory(root,cancelled)
    if cancelled(): raise InterruptedError('Adoption cancelled before database commit.')
    if any(status in ('ERROR','OFFLINE') for _,status in outcomes):
        raise ValueError('Output inventory became unavailable before adoption commit.')
    return tuple(outcomes), tuple((str(path),_guard_file(path,root)) for path in files)


def assert_legacy_export_allowed(inventory, tracks):
    """Barrier for the old copy exporter, not a new create/no-op implementation.

    Existing outputs require adoption or the later managed materializer. Never
    use the legacy suffix-copy path to work around an unresolved ownership case.
    """
    if inventory.cancelled or not inventory.known_libraries or any(
            status in ('OFFLINE','ERROR') for _,status in inventory.root_observations):
        raise ValueError('Historical output adoption inventory is incomplete; creation blocked.')
    selected={track.track_id for track in tracks}
    if any(p.locator and (p.track_id in selected or p.track_id is None) for p in inventory.proposals):
        raise ValueError('Historical outputs require adoption or managed materialization; creation blocked.')


def adopt_legacy_output(repository, proposal_id, *, confirmed, library_root,
                        known_libraries=None, cancelled=None) -> ManagedBinding:
    if confirmed is not True:
        raise ValueError('Explicit confirmation is required for adoption.')
    cancelled=cancelled or (lambda:False)
    if cancelled(): raise InterruptedError('Adoption cancelled before database commit.')
    root=_active_root(repository,library_root)
    with closing(_rw(repository)) as conn:
        row=conn.execute('SELECT p.proposal_json,p.status,r.context_digest,r.context_json FROM legacy_adoption_proposals p '
            'JOIN legacy_adoption_runs r ON r.run_id=p.run_id WHERE proposal_id=?',(proposal_id,)).fetchone()
        if row is None or row['status']!='CANDIDATE':
            raise ValueError('Proposal is unresolved, conflicting, stale or already bound.')
        proposal=AdoptionProposal(**json.loads(row['proposal_json']))
        saved_context=json.loads(row['context_json'])
        stored_known=tuple(KnownLibrary(**v) for v in saved_context['known_libraries'])
    if proposal.library_root!=str(root): raise ValueError('Wrong library root context.')
    supplied=stored_known if known_libraries is None else _descriptors(repository,root,known_libraries)
    if _descriptors(repository,root,supplied)!=stored_known:
        raise ValueError('Known library context changed since approval.')
    fresh=inventory_legacy_outputs(repository,library_root=root,known_libraries=supplied,
                                   cancelled=cancelled,persist=False)
    matches=[p for p in fresh.proposals if p.track_id==proposal.track_id and p.locator==proposal.locator]
    if fresh.cancelled: raise InterruptedError('Adoption cancelled before database commit.')
    if (fresh.context_digest!=row['context_digest'] or len(matches)!=1 or not matches[0].can_adopt
            or matches[0].full_sha256!=proposal.full_sha256
            or tuple(matches[0].stat_identity)!=tuple(proposal.stat_identity)
            or matches[0].record_revision!=proposal.record_revision
            or matches[0].source_context!=proposal.source_context):
        raise ValueError('Candidate, record or library changed; stale approval rejected.')
    current=matches[0]
    expected_membership=(fresh.root_observations,tuple(sorted({p.locator:tuple(p.stat_identity)
        for p in fresh.proposals if p.locator and p.stat_identity}.items())))
    with closing(_rw(repository)) as conn,conn:
        aliases={}
        main=str(repository.database_path.resolve(strict=True))
        for i,item in enumerate(stored_known):
            if item.database==main: aliases[item.database]='main'
            else:
                alias=f'known_{i}'
                conn.execute(f'ATTACH DATABASE ? AS {alias}',(Path(item.database).as_uri()+'?mode=rw',))
                aliases[item.database]=alias
        conn.execute('BEGIN IMMEDIATE')
        states,owners=_known_state(stored_known,conn=conn,aliases=aliases)
        library_id,sources,tracks,context=_context(repository,states,conn)
        if context!=fresh.context_digest or library_id!=current.library_id:
            raise ValueError('Library/ownership context changed before adoption commit.')
        track=next((t for t in tracks if t.track_id==current.track_id),None)
        if track is None: raise ValueError('Record changed or was removed.')
        if conn.execute('SELECT 1 FROM managed_bindings WHERE track_id=?',(track.track_id,)).fetchone():
            raise ValueError('Existing managed binding cannot be silently replaced.')
        source=next((s for s in sources if s.source_id==track.source_id and s.library_id==library_id),None)
        if source is None or _source_context(track,sources,library_id)!=current.source_context:
            raise ValueError('Source binding changed before adoption commit.')
        source_stamp=None
        try:
            Path(track.path).lstat()
        except FileNotFoundError:
            saved=conn.execute('SELECT context_digest,evidence_json FROM source_audio_references WHERE track_id=?',
                               (track.track_id,)).fetchone()
            reference=json.loads(saved['evidence_json']) if saved else {}
            if (not saved or saved['context_digest']!=current.source_context
                    or reference.get('kind')!='VERIFIED_SOURCE'
                    or reference.get('source_context')!=current.source_context
                    or reference.get('library_id')!=library_id or reference.get('track_id')!=track.track_id
                    or reference.get('source_id')!=track.source_id or reference.get('source_locator')!=str(track.path)
                    or reference.get('full_sha256')!=track.sha256
                    or reference.get('algorithm')!=current.audio_algorithm
                    or reference.get('audio_digest')!=current.audio_digest):
                raise ValueError('Source unavailable without a current trusted reference.')
        else:
            source_stamp=_guard_file(track.path,source.root_path)
            source_proof=inspect_audio(track.path,cancelled=cancelled)
            if cancelled(): raise InterruptedError('Adoption cancelled before database commit.')
            if (source_proof.status!='VALID' or source_proof.full_sha256!=track.sha256
                    or source_proof.audio_digest!=current.audio_digest
                    or source_proof.algorithm!=current.audio_algorithm
                    or source_proof.stat_identity!=source_stamp
                    or source_stamp[2:4]!=(track.size_bytes,track.mtime_ns)):
                raise ValueError('Source changed before adoption commit.')
        before=_guard_file(current.locator,root)
        proof=inspect_audio(Path(current.locator),cancelled=cancelled)
        if (proof.status!='VALID' or proof.full_sha256!=current.full_sha256
                or proof.audio_digest!=current.audio_digest or proof.stat_identity!=before
                or before!=tuple(current.stat_identity)):
            raise ValueError('Candidate changed before adoption commit.')
        key=lexical_locator(current.locator)
        for owner_library,owner_track,owner_path,device,inode in owners:
            if key==lexical_locator(owner_path) or before[:2]==(device,inode):
                raise ValueError('Target already has an owner; duplicate ownership rejected.')
        if cancelled(): raise InterruptedError('Adoption cancelled before database commit.')
        if _output_membership(root,cancelled)!=expected_membership:
            raise ValueError('Output inventory changed before database commit.')
        final_states,_=_known_state(stored_known,conn=conn,aliases=aliases)
        if final_states!=states:
            raise ValueError('Known library ownership/material changed before database commit.')
        relative=Path(current.locator).relative_to(root).as_posix(); safe_relative(relative)
        binding_id=str(uuid4()); at=time.time_ns()
        applied={'version':1,'tag_snapshot':proof.tag_snapshot,'relative_path':relative,
                 'value':_snapshot_value(proof.tag_snapshot,relative),'full_sha256':proof.full_sha256,
                 'audio_algorithm':proof.algorithm,'audio_digest':proof.audio_digest}
        source_binding={'locator':str(track.path),'source_id':track.source_id,'relative_path':track.source_relative_path,
                        'source_context':current.source_context}
        evidence={'confirmed':True,'proposal_id':proposal_id,'inventory_id':proposal.run_id,
                  'evidence_sources':current.evidence_sources,'record_revision':current.record_revision,
                  'known_context':context,'source_audio_digest':current.audio_digest}
        conn.execute('INSERT INTO managed_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (track.track_id,library_id,binding_id,relative,key,proof.full_sha256,proof.algorithm,proof.audio_digest,
             before[0],before[1],canonical_json(before),canonical_json(source_binding),canonical_json(applied),canonical_json(evidence),at))
        conn.execute("UPDATE legacy_adoption_proposals SET status='ALREADY_BOUND' WHERE proposal_id=?",(proposal_id,))
        # A final no-follow observation detects replacement after the decoder.
        if _guard_file(current.locator,root)!=before: raise ValueError('Candidate changed before database commit.')
        if cancelled(): raise InterruptedError('Adoption cancelled before database commit.')
        binding=next(b for b in read_managed_bindings(conn) if b.track_id==track.track_id)
        from audio_library_organizer.storage.file_state_cache import write_file_facts
        write_file_facts(conn,binding_facts(binding,track,root,at=at,current=True))
        if _guard_file(current.locator,root)!=before:
            raise ValueError('Candidate changed before database commit.')
        if source_stamp is not None and _guard_file(track.path,source.root_path)!=source_stamp:
            raise ValueError('Source changed before database commit.')
        if source_stamp is None:
            try:
                Path(track.path).lstat()
            except FileNotFoundError:
                pass
            else:
                raise ValueError('Source became available during adoption; approval must be revalidated.')
        if cancelled(): raise InterruptedError('Adoption cancelled before database commit.')
        if _output_membership(root,cancelled)!=expected_membership:
            raise ValueError('Output inventory changed before database commit.')
        return binding


def binding_facts(binding,track,root,*,at=None,current=False):
    from audio_library_organizer.domain.file_state import (
        FileFacts,FileObservation,FileAvailability,OutputSnapshot,Ownership)
    at=binding.adopted_at if at is None else at
    namespace='alo.legacy-adoption.tags-locator'
    return FileFacts(track.track_id,at,
        managed=FileObservation(track.track_id,binding.locator(root),FileAvailability.PRESENT,at,
                                reason='APPROVED_ADOPTION_RECHECK_REQUIRED',is_current=current),
        managed_expected=True,ownership=Ownership.CONFIRMED,owner_track_id=track.track_id,
        # Observed tags/cover are a credible applied snapshot. They do not prove
        # full desired routing/normalization policy, owned by the later output
        # specification stage. Keep that knowledge unknown instead of clean.
        desired=None,
        applied=OutputSnapshot(namespace,1,binding.applied_snapshot['value']),is_current=current)
