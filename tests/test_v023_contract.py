from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_metadata_editor_has_clickable_source_badges_and_consistent_source_styles():
    assert 'QToolButton' in EDITOR
    assert 'QMenu' in EDITOR
    assert "setObjectName('MetadataSourceBadge')" in EDITOR
    assert 'field_source_values' in EDITOR
    for source in ('Tag', 'Discogs', 'MusicBrainz', 'Ręcznie', 'Analiza audio', 'Nazwa pliku'):
        assert source in EDITOR or source in THEME
    for kind in ('tag', 'discogs', 'musicbrainz', 'manual', 'analysis', 'filename'):
        assert f'sourceKind="{kind}"' in THEME
    assert '≋ ANALIZA' in EDITOR


def test_metadata_editor_only_flags_required_main_fields_red_and_low_confidence_frame():
    assert "setProperty('missingRequired'" in EDITOR
    for field in ('artist', 'title', 'year', 'genre', 'bpm'):
        assert field in EDITOR
    assert 'missingRequired="true"' in THEME
    assert "element.setProperty('confidenceKind', kind)" in EDITOR
    assert 'RecognitionConfidenceBar[confidenceKind="low"]' in THEME
    assert "recognition.setObjectName('RecognitionInfoCompact')" in EDITOR
    assert "self.recognition_bar.setObjectName('RecognitionConfidenceBar')" in EDITOR
    assert "self.recognition_confidence.setObjectName('RecognitionConfidencePercent')" in EDITOR


def test_metadata_editor_has_single_editable_result_filename_and_nonclosing_actions():
    assert "QLabel('Nazwa wynikowa')" in EDITOR
    assert 'self.filename_override = QLineEdit' in EDITOR
    assert 'Przywróć nazwę z metadanych' in EDITOR
    assert "QPushButton('Anuluj zmiany')" not in EDITOR
    assert "self.save_button = QPushButton('Zapisz zmiany')" in EDITOR
    assert "self.status_button.setText(ui_text(self, 'GOTOWE')" in EDITOR
    assert 'Kliknij, aby oznaczyć jako GOTOWE' in EDITOR
    assert 'Kliknij, aby zmienić na DO SPRAWDZENIA' in EDITOR
    assert "QPushButton('Zamknij')" not in EDITOR
    assert 'self.footer_buttons = [self.undo_button, self.status_button, self.save_button]' in EDITOR
    assert 'save_requested = Signal(object)' in EDITOR
    assert 'self.accept()' not in EDITOR[EDITOR.index('def _request_save'):EDITOR.index('def values')]
    assert 'Niezapisane zmiany' in EDITOR
    assert "self.saved_notice = QLabel('Zapisano')" in EDITOR


def test_restore_pre_online_uses_editor_snapshot_undo_and_tag_color():
    assert 'def _capture_editor_state' in EDITOR
    assert 'def _apply_editor_state' in EDITOR
    assert 'self._undo_stack' in EDITOR
    assert 'def _restore_pre_online_fields' in EDITOR
    assert 'RestoreOnlineButton' in THEME
    assert '#5ca3ff' in THEME


def test_duplicate_decisions_are_green_gray_and_saved_edits_keep_track():
    assert "return 'ZACHOWAJ'" in DUPLICATES
    assert "QColor('#173c2d')" in DUPLICATES
    assert "QColor('#2a3038')" in DUPLICATES
    assert "'Status', 'Decyzja'" not in DUPLICATES
    assert 'DuplicateStatusBadge' not in THEME
    assert "apply_duplicate_decision(selected, 'keep')" in MAIN


def test_settings_and_operation_bar_v023_layout_contract():
    assert "self.library_status_label.setObjectName('LibraryAvailabilityStatus')" in MAIN
    assert 'QLabel#LibraryAvailabilityStatus' in THEME
    assert 'QRadioButton::indicator:checked' in THEME
    assert "footer.setObjectName('ContactFooter')" in MAIN
    assert 'AlignHCenter' in MAIN
    assert 'self.statusBar().showMessage' not in MAIN
    assert 'self.statusBar().hide()' in MAIN


def test_library_keeps_status_visible_and_titles_have_tooltip():
    assert 'class StableTableView' in LIBRARY
    assert 'horizontalScrollBar().setValue(0)' in LIBRARY
    assert "items[2].setToolTip(track.title or '')" in LIBRARY
    assert 'setTextElideMode(Qt.TextElideMode.ElideRight)' in LIBRARY
    assert "match_box.setProperty('lowConfidence'" in LIBRARY
