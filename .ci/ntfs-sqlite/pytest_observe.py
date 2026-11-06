"""Run the original pytest modules; record a successful export before teardown."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest


def database_checks(path):
    with sqlite3.connect(path) as conn:
        integrity = conn.execute('PRAGMA integrity_check').fetchall()
        foreign_keys = conn.execute('PRAGMA foreign_key_check').fetchall()
    assert integrity == [('ok',)] and foreign_keys == []
    return {'integrity': integrity, 'foreign_keys': foreign_keys}


def record_flow(item):
    from mutagen.id3 import ID3

    window, tracks, summaries = item.funcargs['export_window']
    result = window._export_result
    scenario = 'cancel' if item.funcargs['stop_after'] == 3 else 'full'
    paths = window.app_settings.library
    repo = window.repository
    tracks_by_id = {track.track_id: track for track in tracks}
    tracks_by_source = {track.path: track for track in tracks}
    summary = summaries[0][0]
    outputs = {}
    for binding in repo.list_managed_bindings():
        track = tracks_by_id[binding.track_id]
        path = Path(binding.locator(paths.root))
        assert path.is_relative_to(paths.ready)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == binding.expected_sha256
        tags = ID3(path)
        assert (str(tags['TPE1']), str(tags['TIT2'])) == ('Artist', f'{track.title} [128bpm]')
        assert (str(tags['TDRC']), str(tags['TCON']), str(tags['TBPM'])) == ('2000', 'House', '128')
        assert tags.version[:2] == (2, 3)
        outputs[track.track_id] = dict(binding_id=binding.binding_id, path=str(path), sha256=digest,
                                      artist=str(tags['TPE1']), title=str(tags['TIT2']),
                                      apic=[dict(mime=tag.mime, sha256=hashlib.sha256(tag.data).hexdigest())
                                            for tag in tags.getall('APIC')])
    assert set(outputs) == {tracks_by_source[row.source].track_id for row in result.outcomes
                            if row.status == 'verified'}
    assert len({row['path'] for row in outputs.values()}) == len(outputs)
    assert not list(paths.review.rglob('*.mp3')) and not list(paths.not_selected.rglob('*.mp3'))
    assert summary.created_text == str(result.created)
    evidence = dict(pid=os.getpid(), library=str(paths.root), prefs=window.qt_settings.fileName(),
                    planned=result.planned, processed=result.processed, created=result.created,
                    skipped=result.skipped, failed=result.failed, remaining=result.remaining,
                    cancelled=result.cancelled, summary=summary.outcome, summary_count=summary.created_text,
                    summary_notice=summary.notice_text, track_ids=sorted(tracks_by_id),
                    missing_cover_uuid=tracks[7].track_id, outputs=outputs,
                    sqlite=database_checks(repo.database_path))
    dest = Path(os.environ['ALO_EVIDENCE']) / f'before-close-{scenario}.json'
    dest.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{scenario}: planned={result.planned}, created={result.created}, '
          f'skipped={result.skipped}, remaining={result.remaining}, integrity=ok, FK=0')


class Observer:
    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_call(self, item):
        result = yield
        if item.originalname == 'test_empty_output_library_isolates_missing_cover_and_persists_bindings':
            record_flow(item)
        return result


if __name__ == '__main__':
    sys.exit(pytest.main(sys.argv[1:], plugins=[Observer()]))
