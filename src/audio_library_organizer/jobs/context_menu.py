"""Immutable menu work. Presence is a hint; read_material remains the authority.

No QObject, widget, repository mutation or GUI callback crosses this boundary.
The optional snapshot reader must capture plain repository/root inputs only.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from threading import Event

from audio_library_organizer.jobs.managed_files import read_material


def frozen_value(value):
    if is_dataclass(value):
        return tuple((f.name, frozen_value(getattr(value, f.name))) for f in fields(value))
    if isinstance(value, dict):
        return tuple(sorted((k, frozen_value(v)) for k, v in value.items()))
    if isinstance(value, (set, frozenset)):
        return frozenset(frozen_value(v) for v in value)
    if isinstance(value, (list, tuple)):
        return tuple(frozen_value(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class MenuContext:
    read_context: object
    epoch: int
    records: tuple
    target_id: str
    evaluations: tuple
    view: tuple
    menu_id: int


@dataclass(frozen=True, slots=True)
class MenuWork:
    context: MenuContext
    operation: str
    plans: tuple = ()
    snapshot_reader: object = None
    data: tuple = ()


def snapshot_matches(context, snapshot):
    current, tracks = snapshot[:2]
    if current != context.read_context:
        return False
    if len(snapshot) > 2 and frozen_value(snapshot[2]) != context.evaluations:
        return False
    for track_id, before in context.records:
        matches = [t for t in tracks if t.track_id == track_id]
        if len(matches) != 1 or frozen_value(matches[0]) != before:
            return False
    return True


def material_exists(plan, cancelled):
    """Worker-only, conservative presence check. Never grants read authority."""
    if cancelled() or plan is None:
        return False
    try:
        return bool(plan.locator and Path(plan.locator).is_file()) or material_exists(plan.fallback, cancelled)
    except (OSError, RuntimeError, ValueError):
        return False


def execute_menu_work(work, cancel):
    """Always return a value/error through the task's terminal notification."""
    if cancel.is_set():
        raise InterruptedError('Menu work cancelled')
    if work.operation == 'probe':
        # Plans are shared by several actions. Probe each unique plan once.
        observed = {}
        result = []
        for key, plans in work.plans:
            values = []
            for plan in plans:
                if plan not in observed:
                    observed[plan] = material_exists(plan, cancel.is_set)
                values.append(observed[plan])
            result.append((key, bool(values) and all(values)))
        return tuple(result)

    def fresh():
        if cancel.is_set():
            raise InterruptedError('Menu work cancelled')
        if work.snapshot_reader is None:
            return None
        snapshot = work.snapshot_reader()
        if cancel.is_set():
            raise InterruptedError('Menu work cancelled')
        if not snapshot_matches(work.context, snapshot):
            raise ValueError('Menu repository context changed')
        return snapshot

    snapshot = fresh()
    paths, identities = [], []
    for plan in work.plans:
        if cancel.is_set() or plan is None or plan.locator is None:
            raise ValueError('No authorized menu read plan')
        result = read_material(plan, str, cancelled=cancel.is_set)
        allowed = {p.guard_key for p in (plan, plan.fallback) if p is not None}
        if (not result.resolution.is_verified or result.resolution.guard_key not in allowed
                or result.value != result.resolution.locator):
            raise ValueError('Menu material could not be revalidated')
        paths.append(Path(result.value))
        identities.append(result.resolution.material_identity)
    snapshot = fresh()
    if cancel.is_set():
        raise InterruptedError('Menu work cancelled')
    if work.operation == 'playlist':
        from audio_library_organizer.jobs.playlists import write_m3u8
        def before_write():
            for plan, expected, identity in zip(work.plans, paths, identities):
                checked = read_material(plan, str, cancelled=cancel.is_set)
                if (not checked.resolution.is_verified or checked.value != str(expected)
                        or checked.resolution.material_identity != identity):
                    raise ValueError('Playlist material changed during preparation')
            fresh()
        return write_m3u8(Path(work.data[0]), paths, relative=True, guard=fresh, before_write=before_write), len(paths)
    if work.operation == 'collection':
        from audio_library_organizer.jobs.collections import build_collection_plan
        if snapshot is None:
            raise ValueError('Collection requires a fresh repository snapshot')
        ids = {track_id for track_id, _ in work.context.records}
        tracks = [t for t in snapshot[1] if t.track_id in ids]
        return build_collection_plan(work.data[0], work.data[1], tracks)
    if work.operation != 'action':
        raise ValueError('Unknown menu operation')
    return tuple(paths)


class LatestMenuWork:
    """One running item and one latest pending item; no unbounded pool queue."""
    def __init__(self):
        self.serial = 0
        self.active = None
        self.pending = None
        self.closed = False

    def submit(self, work, callback):
        if self.closed:
            raise RuntimeError('Menu work is closed')
        self.serial += 1
        entry = (self.serial, work, Event(), callback)
        if self.active is None:
            self.active = entry
            return entry
        self.active[2].set()
        self.pending = entry
        return None

    def complete(self, serial):
        if self.active is None or self.active[0] != serial:
            return None, None
        finished = self.active
        self.active, self.pending = self.pending, None
        return finished, self.active

    def cancel(self, *, closing=False):
        if self.active is not None:
            self.active[2].set()
        self.pending = None
        self.closed = self.closed or closing
