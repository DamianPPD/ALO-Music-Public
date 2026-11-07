"""Standalone §8 publication smoke tests against the selected candidate's real UI.

Run with the candidate's src and tests directories on PYTHONPATH. The only
producer instrumentation is an event barrier to make the Stop click deterministic.
"""
import csv
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
from threading import Event
from time import monotonic
from uuid import UUID

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from mutagen.id3 import ID3
from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
import pytest

from audio_adoption_fixtures import mp3_samples  # noqa: F401, required by mp3_bytes
from audio_library_organizer.audio.identity import inspect_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.jobs import exporter
from audio_library_organizer.ui.export_dialogs import ExportPreviewDialog, ExportSummaryDialog
from conftest import current_start_window, release_test_windows  # noqa: F401, fixture imports
from test_apev2_identity_v0427 import (
    ALGORITHM, ID3V1, _ape_descriptor, _ape_item, _ape_tag, _ape_with_false_id3v1,
    _restart_and_check, mp3_bytes,
)
from test_export_window_v0427 import no_unhandled_qt_errors  # noqa: F401, autouse fixture
from test_manual_cover_export_v0427 import wait_for_export


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _snapshot(path):
    return path.read_bytes(), path.stat().st_mtime_ns


def _click(button):
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


@pytest.fixture
def ui(current_start_window, monkeypatch):
    window = current_start_window
    preview_exec = ExportPreviewDialog.exec
    summary_exec = ExportSummaryDialog.exec
    previews, summaries, unexpected = [], [], []

    def preview(dialog):
        previews.append(dialog.total_label.text())
        QTimer.singleShot(0, lambda: _click(dialog.create_button))
        return preview_exec(dialog)

    def summary(dialog):
        summaries.append((dialog.outcome, dialog.created_label.text(), dialog.report))
        QTimer.singleShot(0, lambda: _click(dialog.close_button))
        return summary_exec(dialog)

    def unexpected_box(dialog):
        unexpected.append((dialog.windowTitle(), dialog.text()))
        return QMessageBox.StandardButton.Cancel

    def unexpected_message(_parent, title, message, *args, **kwargs):
        unexpected.append((title, message))
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(ExportPreviewDialog, 'exec', preview)
    monkeypatch.setattr(ExportSummaryDialog, 'exec', summary)
    monkeypatch.setattr(QMessageBox, 'exec', unexpected_box)
    for name in ('warning', 'critical', 'information'):
        monkeypatch.setattr(QMessageBox, name, unexpected_message)
    yield window, previews, summaries
    assert not unexpected, unexpected


def _prepare(window, tmp_path, variants):
    source = tmp_path / 'source'
    source.mkdir()
    window.repository.register_source(source)
    tracks = {}
    for name, content in variants.items():
        path = source / f'{name}.mp3'
        path.write_bytes(content)
        info = path.stat()
        track = TrackRecord(path=path, artist='Fixture Artist', title=name, year='2000',
                            genre='House', bpm=128, status='ready',
                            locked_fields={'__status__'}, sha256=_sha(content),
                            size_bytes=info.st_size, mtime_ns=info.st_mtime_ns)
        window.repository.upsert_track(track)
        tracks[name] = track
    window.refresh_data()
    assert not list(window.app_settings.library.root.rglob('*.mp3'))
    return tracks, {track.path: _snapshot(track.path) for track in tracks.values()}


def _start(window):
    assert window.export_btn.isVisible() and window.export_btn.isEnabled()
    _click(window.export_btn)
    assert window._thread is not None and window._export_dialog is not None


def _settle(window):
    try:
        wait_for_export(window)
    finally:
        if window._thread is not None and window._export_dialog is not None:
            window._export_dialog.stop_button.click()
            wait_for_export(window)
    result = window._export_result
    assert result is not None and not result.fatal_error, result
    return result


def _audit(ui, expected_outcome, created, planned):
    _, previews, summaries = ui
    assert previews == [str(planned)]
    assert len(summaries) == 1
    outcome, created_text, report = summaries[0]
    assert (outcome, created_text) == (expected_outcome, str(created))
    assert report is not None and report.is_file()
    with report.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == planned
    return {Path(row['source_path']): row for row in rows}


def _published(window, tracks, result, audit, frames, ape_tails):
    paths = window.app_settings.library
    expected_digest = _sha(frames)
    outcomes = {outcome.source: outcome for outcome in result.outcomes}
    bindings = {binding.track_id: binding for binding in window.repository.list_managed_bindings()}
    assert bindings.keys() == {track.track_id for track in tracks.values()}
    assert set(paths.root.rglob('*.mp3')) == set(result.copied)
    assert not list(paths.root.rglob('.alo-copy-*'))
    outputs = {}
    for name, track in tracks.items():
        outcome, binding = outcomes[track.path], bindings[track.track_id]
        assert UUID(binding.track_id) and UUID(binding.binding_id) and UUID(binding.library_id)
        assert binding.library_id == window.repository.library_id
        assert outcome.status == 'verified' and outcome.raw_verified, outcome
        output = outcome.destination
        assert output == Path(binding.locator(paths.root))
        content, mtime = _snapshot(output)
        full_sha = _sha(content)
        proof = inspect_audio(output)
        assert proof.status == 'VALID', proof.reason
        assert proof.stat_identity == binding.stat_identity
        assert proof.algorithm == binding.audio_algorithm == ALGORITHM
        assert proof.audio_digest == binding.audio_digest == expected_digest
        assert proof.full_sha256 == binding.expected_sha256 == outcome.final_sha256 == full_sha
        assert audit[track.path]['final_sha256'] == full_sha
        assert binding.evidence['source_sha256'] == track.sha256 != full_sha
        assert binding.evidence['source_audio_digest'] == expected_digest
        tags = ID3(output, load_v1=False)
        assert str(tags['TPE1']) == track.artist
        assert str(tags['TIT2']) == f'{track.title} [128bpm]'
        assert str(tags['TBPM']) == '128'
        assert str(tags['TCON']) == 'House' and str(tags['TDRC']) == '2000'
        ape, before_v1 = ape_tails.get(name, (b'', False))
        if ape:
            end = len(content) - 128 if before_v1 else len(content)
            assert content[end - len(ape):end] == ape, f'APE bytes changed for {name}'
            if before_v1:
                assert content[end:end + 3] == b'TAG', 'Terminal ID3v1 disappeared'
        else:
            assert not proof.ape_at_eof
        outputs[output] = (content, mtime)
        print(f'{name}: verified; SHA-256={full_sha}; audio={expected_digest}; APE bytes={len(ape)}')
    with closing(sqlite3.connect(paths.database)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        rows = conn.execute('SELECT track_id, binding_id, expected_sha256, audio_digest FROM managed_bindings')
        assert set(rows) == {(b.track_id, b.binding_id, b.expected_sha256, expected_digest)
                             for b in bindings.values()}
    return bindings, outputs


def _restart(window, tmp_path, tracks, bindings, files):
    result = _restart_and_check(window, tmp_path)
    assert not result['errors'], result
    assert result['ids'] == {track_id: binding.binding_id for track_id, binding in bindings.items()}
    assert set(result['cells']) == {track.track_id for track in tracks.values()}
    assert {tid for tid, label in result['cells'].items() if label.startswith('W bibliotece')} == bindings.keys(), result
    assert all(_snapshot(path) == expected for path, expected in files.items())
    print(f"Fresh process: {len(bindings)} W bibliotece; SQLite bindings, source and output files unchanged")


def test_create_five_mp3_variants_and_restart(ui, tmp_path, mp3_bytes):
    window = ui[0]
    prefix, frames = mp3_bytes
    audio = prefix + frames
    ape_eof = _ape_with_false_id3v1()
    ape_before_id3v1 = _ape_tag(_ape_item(value=b'Keep APE metadata through ID3v1'), header=True)
    tracks, sources = _prepare(window, tmp_path, {
        '01 normal MP3': audio,
        '02 MP3 with APEv2': audio + ape_eof,
        '03 MP3 with APEv2 and ID3v1': audio + ape_before_id3v1 + ID3V1,
        '04 MP3 with damaged APEv2': audio + _ape_item() + _ape_descriptor(31, 1),
        '05 MP3 with truncated MPEG': audio[:-1],
    })
    _start(window)
    result = _settle(window)
    assert not result.cancelled
    assert (result.planned, result.processed, result.created, result.failed, result.remaining) == (5, 5, 3, 2, 0), result
    audit = _audit(ui, 'problems', 3, 5)
    outcomes = {outcome.source: outcome for outcome in result.outcomes}
    refusal_reasons = set()
    for name in ('04 MP3 with damaged APEv2', '05 MP3 with truncated MPEG'):
        source = tracks[name].path
        proof = inspect_audio(source)
        outcome = outcomes[source]
        assert proof.status == 'ERROR' and proof.audio_digest is None and proof.reason
        assert outcome.status != 'verified' and outcome.destination is None and not outcome.raw_verified
        assert not audit[source]['destination_path'] and audit[source]['final_file_exists'] == 'False'
        assert proof.reason in audit[source]['error']
        refusal_reasons.add(proof.reason)
        print(f'{name}: refused; {proof.reason}')
    assert len(refusal_reasons) == 2
    bindings, outputs = _published(window, dict(list(tracks.items())[:3]), result, audit, frames, {
        '02 MP3 with APEv2': (ape_eof, False),
        '03 MP3 with APEv2 and ID3v1': (ape_before_id3v1, True),
    })
    assert all(_snapshot(path) == expected for path, expected in sources.items())
    _restart(window, tmp_path, tracks, bindings, sources | outputs)


def test_stop_via_ui_after_two_completed_and_restart(ui, tmp_path, mp3_bytes, monkeypatch):
    window = ui[0]
    prefix, frames = mp3_bytes
    ape = _ape_tag(_ape_item(value=b'APE preserved on stopped batch'))
    tracks, sources = _prepare(window, tmp_path, {
        f'{i:02} stopped batch': prefix + frames + ape for i in range(6)
    })
    reached, release = Event(), Event()
    original = exporter.execute_copy_plan
    started = []

    def execute(plan, **kwargs):
        send = kwargs['event']

        def observe(event):
            if event.phase == 'item_started':
                started.append(event.source)
            send(event)
            if event.phase == 'item_finished' and event.created == 2:
                reached.set()
                assert release.wait(20), 'Timed out while waiting for the UI to click Stop'

        return original(plan, **{**kwargs, 'event': observe})

    monkeypatch.setattr(exporter, 'execute_copy_plan', execute)
    _start(window)
    try:
        deadline = monotonic() + 35
        while monotonic() < deadline and window._export_dialog is not None:
            QCoreApplication.processEvents()
            progress = window._export_dialog
            if reached.is_set() and progress is not None and progress.count_labels['created'].text() == '2':
                break
            reached.wait(0.005)
        progress = window._export_dialog
        assert reached.is_set() and progress is not None
        assert progress.count_labels['created'].text() == '2' and len(started) == 2
        assert progress.stop_button.isVisible() and progress.stop_button.isEnabled()
        _click(progress.stop_button)
        assert progress.stopping and not progress.stop_button.isEnabled()
        assert window._export_stop_requested
    finally:
        release.set()
        result = _settle(window)
    assert result.cancelled
    assert (result.planned, result.processed, result.created, result.failed, result.remaining) == (6, 2, 2, 0, 4), result
    assert len(started) == 2, started
    audit = _audit(ui, 'cancelled', 2, 6)
    completed = {name: track for name, track in tracks.items() if track.path in started}
    bindings, outputs = _published(window, completed, result, audit, frames,
                                    {name: (ape, False) for name in completed})
    assert all(_snapshot(path) == expected for path, expected in sources.items())
    print('Stop clicked after 2 completed: 4 left; no further file started')
    _restart(window, tmp_path, tracks, bindings, sources | outputs)
