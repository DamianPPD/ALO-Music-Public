"""Approved Library refinements; real Qt widgets, synthetic data only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata import normalization
from audio_library_organizer.ui.library_page import LibraryPage, LIBRARY_SORT_ROLE
from test_library_file_ui_v0427 import library_page, menu_for, menu_actions, settle_context_read


@pytest.mark.parametrize('raw,expected', [
    ('2003', '2003'), ('2021-08-06', '2021'), ('2022-03-25', '2022'),
    ('2009-01-01', '2009'), ('2000-02', '2000'),
    ('2020-02-29T12:30:00Z', '2020'), (None, None), ('', None),
    ('2021-02-29', None), ('2022-13', None), ('2003junk', None),
    ('20a4', None), ('0000', None), ('2000-00-00', None), ('２０２１', None),
    ('2020-01-01T12:30+01:60', None), ('2020-01-01T12:30-00:99', None),
    ('2020-01-01T12:30+24:00', None), ('2020-01-01T12:30+02:30', '2020'),
])
def test_year_accepts_only_documented_calendar_dates(raw, expected):
    assert normalization.normalize_year(raw) == expected


def test_existing_full_dates_display_and_sort_without_mutating_records(tmp_path):
    QApplication.instance() or QApplication([])
    tracks = [TrackRecord(tmp_path / f'{i}.mp3', year=y, title=str(i))
              for i, y in enumerate(('2021-08-06', '2003', '2009-01-01', None, 'invalid'))]
    before = deepcopy(tracks)
    page = LibraryPage()
    page.set_tracks(tracks)
    for order, expected in ((Qt.SortOrder.AscendingOrder, [None, None, 2003, 2009, 2021]),
                            (Qt.SortOrder.DescendingOrder, [2021, 2009, 2003, None, None])):
        page.table.sortByColumn(4, order)
        shown = [page.model.item(row, 4).text() for row in range(5)]
        assert [None if y == '—' else int(y) for y in shown] == expected
        for row in range(5):
            item = page.model.item(row, 4)
            if item.text() != '—':
                assert item.data(LIBRARY_SORT_ROLE) == int(item.text())
    page.table.selectRow(0)
    # selectionChanged invokes the real detail workflow; do not request the
    # same artwork load a second time just to read the already-updated label.
    assert page.detail_labels['year'].text() == '2021'
    assert tracks == before


def test_editor_normalizes_visible_year_but_retains_raw_source(tmp_path):
    from audio_library_organizer.ui.metadata_editor import MetadataEditorDialog
    QApplication.instance() or QApplication([])
    track = TrackRecord(tmp_path / 'synthetic.mp3', year='2021-08-06')
    before = deepcopy(track)
    editor = MetadataEditorDialog(track)
    try:
        assert editor.year.text() == '2021'
        assert not editor.has_unsaved_changes()
        assert not editor.year.property('changed')
        editor._set_widget_value('year', '2009-01-01')
        assert editor.year.text() == '2009'
        assert editor._display_source_value('year', 'bad date') == '—'
        assert editor._track_value_map(track)['year'] == '2021-08-06'
        assert track == before
    finally:
        editor.done(QDialog.DialogCode.Rejected)


def test_manual_year_validator_matches_normalized_calendar_year_contract():
    assert normalization.is_valid_year_text('2003')
    assert normalization.is_valid_year_text('')
    assert not normalization.is_valid_year_text('0000')
    assert not normalization.is_valid_year_text('２０２１')
    assert not normalization.is_valid_year_text('2021-08-06')


def test_new_tags_normalize_year_and_preserve_raw_tag_bytes(tmp_path):
    from mutagen.id3 import ID3, TDRC, TIT2
    from audio_library_organizer.metadata.tags import read_tags
    path = tmp_path / 'synthetic.mp3'
    tag = ID3()
    tag.add(TIT2(encoding=3, text='Synthetic'))
    tag.add(TDRC(encoding=3, text='2021-08-06'))
    tag.save(path)
    before = path.read_bytes()
    result = read_tags(path)
    assert result.year == '2021'
    assert result.raw['TDRC'] == '2021-08-06'
    assert path.read_bytes() == before


def test_year_only_id3_and_generic_dates_keep_source_information(tmp_path, monkeypatch):
    from mutagen.id3 import ID3, TDRC
    from types import SimpleNamespace
    from audio_library_organizer.metadata import tags
    path = tmp_path / 'year-only.mp3'
    tag = ID3()
    tag.add(TDRC(encoding=3, text='2009-01-01'))
    tag.save(path)
    assert tags.read_tags(path).year == '2009'
    raw = {'date': ['2021-08-06']}
    monkeypatch.setattr(tags, 'MutagenFile', lambda *a, **kw: SimpleNamespace(tags=raw))
    result = tags.read_tags(tmp_path / 'synthetic.flac')
    assert result.year == '2021'
    assert result.raw == raw


def test_new_provider_dates_are_validated_without_changing_recognition():
    from audio_library_organizer.providers.itunes import parse_itunes_result
    from audio_library_organizer.providers.musicbrainz import parse_recording
    from audio_library_organizer.providers.discogs import parse_release_candidate
    from audio_library_organizer.providers.acoustid import parse_acoustid_results
    assert parse_itunes_result({'releaseDate': '2022-03-25T00:00:00Z'}).year == '2022'
    assert parse_itunes_result({'releaseDate': '2022junk'}).year is None
    assert parse_recording({'releases': [{'date': '2021-02-29'}, {'date': '2003-01'}]}).years == ('2003',)
    assert parse_release_candidate({'year': 0}).year is None
    result = parse_acoustid_results({'results': [{'score': .8, 'recordings': [
        {'id': 'synthetic', 'releases': [{'date': '2021-02-29'}]}]}]})
    assert result[0].year is None


def test_menu_exposes_only_approved_actions_and_keeps_toolbar(tmp_path):
    page, tracks, _ = library_page(tmp_path)
    menu = menu_for(page, tracks[0])
    actions = menu_actions(menu)
    assert set(actions) == {'edit', 'ready', 'review', 'reveal'}
    assert [a.text() for a in menu.actions()] == [
        'Edytuj metadane', 'Zmień stan metadanych', '', 'Pokaż plik w Eksploratorze']
    assert not actions['reveal'].isEnabled()
    assert actions['ready'].property('accent') == '#35d893'
    assert actions['review'].property('accent') == '#d8a23a'
    emitted = []
    page.edit_requested.connect(emitted.append)
    actions['edit'].trigger()
    actions['edit'].trigger()
    settle_context_read(page)
    assert emitted == [tracks[0]]
    assert page.details_btn is not None


def test_menu_status_actions_really_update_only_isolated_sqlite(current_start_window, tmp_path):
    import hashlib
    from audio_library_organizer.storage.database import connect
    window = current_start_window
    source = tmp_path / 'synthetic-source'
    source.mkdir()
    path = source / 'one.mp3'
    path.write_bytes(b'Synthetic read-only music for status test')
    window.repository.replace_sources([source])
    track = TrackRecord(path, artist='Fixture', title='Synthetic', year='2003', genre='House', bpm=128)
    window.repository.upsert_track(track)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    window.refresh_data()
    for action, expected in [('ready', 'ready'), ('review', 'review')]:
        current = window.repository.get_track(track.track_id)
        menu_actions(menu_for(window.library, current))[action].trigger()
        settle_context_read(window.library)
        assert window.repository.get_track(track.track_id).status == expected
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with connect(window.repository.database_path) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_legend_names_and_icons_use_existing_accents(language):
    from audio_library_organizer.ui.library_status_legend import install_library_status_legend
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    page.setProperty('_alo_language', language)
    menu = install_library_status_legend(page).menu()
    assert [a.property('accent') for a in menu.actions()] == [
        '#35d893', '#b987ff', '#d8a23a', '#f34d64', '#a8b1bd']
    for action in menu.actions():
        assert not action.icon().isNull()
        assert ' — ' in action.text()
    if language == 'en':
        assert menu.actions()[0].text().startswith('READY — ')


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_filter_labels_roles_and_supported_formats(language, tmp_path):
    from audio_library_organizer.jobs.scanner import SUPPORTED_EXTENSIONS
    from audio_library_organizer.domain.file_state import FileState
    from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    page.setProperty('_alo_language', language)
    page.set_tracks([TrackRecord(tmp_path / 'one.mp3')])
    assert {page.format_filter.itemData(i) for i in range(1, page.format_filter.count())} == {
        suffix[1:].upper() for suffix in SUPPORTED_EXTENSIONS}
    assert page.file_filter.count() == 7
    assert {page.file_filter.itemData(i) for i in range(1, 7)} == {s.value for s in FileState}
    assert all(':' not in page.file_filter.itemText(i) for i in range(7))
    assert all(':' not in page.format_filter.itemText(i) for i in range(page.format_filter.count()))
    assert page.file_filter.itemText(0) == ('Wszystkie stany' if language == 'pl' else 'All states')
    for state, color in FILE_STATE_COLORS.items():
        i = page.file_filter.findData(state.value)
        assert page.file_filter.itemData(i, Qt.ItemDataRole.ForegroundRole).color().name() == color.accent
    page.format_filter.setCurrentIndex(page.format_filter.findData('MP3'))
    assert len(page.visible_tracks()) == 1
    page.refresh()
    assert page.format_filter.currentData() == 'MP3'


@pytest.mark.parametrize('language', ['pl', 'en'])
def test_filter_keyboard_and_label_width_survive_language_and_font_changes(tmp_path, language):
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QFont, QFontMetrics
    from audio_library_organizer.ui.i18n import apply_static_language
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    page.set_tracks([TrackRecord(tmp_path / 'one.mp3')])
    apply_static_language(page, language)
    font = QFont(page.file_filter.font())
    font.setPointSize(15)
    page.file_filter.setFont(font)
    QTest.keyClick(page.file_filter, Qt.Key.Key_Down)
    assert page.file_filter.currentData() == 'IN_LIBRARY'
    bold = QFont(page.file_filter.font())
    bold.setBold(True)
    needed = max(QFontMetrics(bold).horizontalAdvance(page.file_filter.itemText(i)) for i in range(7))
    assert page.file_filter.width() >= needed + page.file_filter.fontMetrics().horizontalAdvance(
        ('Plik' if language == 'pl' else 'File') + ': ') + 42


def _pixel_count(image, color):
    return sum(image.pixelColor(x, y).name() == color for y in range(image.height()) for x in range(image.width()))


def test_real_qt_paint_keeps_accent_text_and_neutral_description():
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QStyleOptionViewItem, QStyle
    from audio_library_organizer.ui.library_status_legend import install_library_status_legend
    from audio_library_organizer.ui.theme import DARK_STYLE
    app = QApplication.instance() or QApplication([])
    previous = app.styleSheet()
    app.setStyleSheet(DARK_STYLE)
    try:
        page = LibraryPage()
        menu = install_library_status_legend(page).menu()
        menu.ensurePolished()
        menu.resize(menu.sizeHint())
        image = menu.grab().toImage()
        # Scan text to the right of the icon, so a colored icon alone cannot pass.
        rect = menu.actionGeometry(menu.actions()[0])
        text = image.copy(rect.adjusted(45, 0, -2, 0))
        assert _pixel_count(text, '#35d893') > 0
        # Thin neutral text is subpixel-antialiased: no fully covered pixel is
        # guaranteed. Require pixels close to the actual light-gray paint pen.
        assert any(max(abs(channel - target) for channel, target in zip(
            image.pixelColor(x, y).getRgb()[:3], (238, 243, 247))) <= 15
            for y in range(rect.top(), rect.bottom()+1) for x in range(160, image.width()-10))
        page.file_filter.setCurrentIndex(page.file_filter.findData('SOURCE_ONLY'))
        page.file_filter.resize(page.file_filter.sizeHint())
        closed = page.file_filter.grab().toImage()
        assert _pixel_count(closed, '#84939e') > 0
        assert _pixel_count(closed, '#66aaf0') > 0
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, page.file_filter.width(), 32)
        option.palette = page.file_filter.palette()
        option.state = QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected
        option.widget = page.file_filter.view()
        popup = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
        popup.fill(Qt.GlobalColor.transparent)
        painter = QPainter(popup)
        try:
            page.file_filter.itemDelegate().paint(painter, option, page.file_filter.model().index(2, 0))
        finally:
            painter.end()
        assert _pixel_count(popup.copy(QRect(20, 0, popup.width()-20, 32)), '#66aaf0') > 0
    finally:
        app.setStyleSheet(previous)


@pytest.mark.parametrize('location', ['present', 'moved', 'offline'])
@pytest.mark.parametrize('known_source_only', [False, True])
def test_missing_count_and_file_filter_use_different_evidence_without_reclassifying(tmp_path, location, known_source_only):
    from audio_library_organizer.jobs.file_reconciliation import check_library
    from test_library_reconciliation_v0427 import library, record
    from audio_library_organizer.domain.file_state import FileState
    from audio_library_organizer.domain.file_state import FileFacts
    from audio_library_organizer.jobs.reporting import build_library_health
    repo, source = library(tmp_path)
    track = record(repo, source / 'one.mp3')
    initial = check_library(repo, checked_at=10,
        prepared_facts=(FileFacts(track.track_id, 10, managed_expected=False),) if known_source_only else (),
        prepared_library_id=repo.library_id)
    assert initial.summary.present == 1
    if location == 'moved':
        track.path.rename(tmp_path / 'outside-source.mp3')
    elif location == 'offline':
        source.rename(source.with_name('offline-source'))
    availability = repo.sync_availability(purge_missing=False)
    QApplication.instance() or QApplication([])
    page = LibraryPage()
    def refresh():
        snapshot = repo.file_check_snapshot()
        page.set_read_context(snapshot.read_context(tmp_path))
        page.set_file_state_evaluations(snapshot.library_id, {tid:c.evaluation for tid,c in snapshot.cached})
        page.set_tracks(list(snapshot.tracks))
    refresh()
    assert availability.missing == (0 if location == 'present' else 1)
    historical = FileState.SOURCE_ONLY if known_source_only else None
    assert page._file_presentation(page._tracks[0]).state == historical
    assert build_library_health(repo.list_tracks())['missing'] == availability.missing
    from threading import Event
    cancel = Event()
    cancelled = check_library(repo, checked_at=20, cancelled=cancel.is_set, progress=lambda *a: cancel.set())
    assert cancelled.cancelled and cancelled.cache_saved == 0
    refresh()
    assert page._file_presentation(page._tracks[0]).state == historical
    completed = check_library(repo, checked_at=30)
    # The view is a snapshot: the new result alone does not refresh the page.
    assert page._file_presentation(page._tracks[0]).state == historical
    refresh()
    state = page._file_presentation(page._tracks[0])
    if location == 'moved':
        assert completed.summary.missing == 1
        assert state.state == historical and not state.confirmed
    elif location == 'offline':
        assert completed.summary.offline == 1
        assert state.state == historical and not state.confirmed
    else:
        assert state.state == historical
    # With explicit, current evidence of no MANAGED assignment the backend can
    # distinguish confirmed missing from offline. This is not inferred from
    # is_file(False), nor injected into production by this diagnostic test.
    attested = check_library(repo, checked_at=40, prepared_library_id=repo.library_id,
                            prepared_facts=(FileFacts(track.track_id, 40, managed_expected=False),))
    refresh()
    state = page._file_presentation(page._tracks[0])
    if location == 'moved':
        assert attested.files[0].evaluation.state == FileState.SOURCE_UNAVAILABLE
        assert attested.files[0].evaluation.is_confirmed
        assert state.state == FileState.SOURCE_UNAVAILABLE and not state.confirmed
    elif location == 'present':
        assert attested.files[0].evaluation.state == FileState.SOURCE_ONLY
        assert attested.files[0].evaluation.is_confirmed
        assert state.state == FileState.SOURCE_ONLY and not state.confirmed
    else:
        assert state.state == historical and not state.confirmed
    assert len(repo.list_tracks()) == 1
