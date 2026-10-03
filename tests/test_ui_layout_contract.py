from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'src/audio_library_organizer/ui/main_window.py').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'src/audio_library_organizer/ui/library_page.py').read_text(encoding='utf-8')
PLAYER = (ROOT / 'src/audio_library_organizer/ui/player.py').read_text(encoding='utf-8')
DUPLICATES = (ROOT / 'src/audio_library_organizer/ui/duplicates_page.py').read_text(encoding='utf-8')
EDITOR = (ROOT / 'src/audio_library_organizer/ui/metadata_editor.py').read_text(encoding='utf-8')
THEME = (ROOT / 'src/audio_library_organizer/ui/theme.py').read_text(encoding='utf-8')


def test_start_keeps_central_stat_cards_without_duplicate_workflow_strip():
    assert 'from audio_library_organizer.ui.widgets import StatCard' in MAIN
    for label in ('Wszystkie', 'Gotowe', 'Duplikaty', 'Do sprawdzenia'):
        assert f"StatCard('{label}'" in MAIN
    assert "workflow.setObjectName('CompactWorkflow')" not in MAIN


def test_operation_state_is_kept_in_the_workflow_strip():
    assert "self.operation_frame = QFrame(); self.operation_frame.setObjectName('OperationFrame')" in MAIN
    assert 'self.operation_frame.setParent(self.action_frame)' in MAIN
    assert 'action.addWidget(self.operation_frame, 1)' in MAIN
    assert 'outer.addWidget(self.operation_frame)' not in MAIN
    assert "self.operation_icon = QLabel()" in MAIN
    assert "self.operation_icon.setPixmap(start_icon('status_ring'" in MAIN
    assert "self.operation_state_icon.setPixmap(start_icon(icon_name" in MAIN
    assert 'def _set_operation_state(' in MAIN
    assert "self.operation_frame.setProperty('operationKind', kind)" in MAIN
    assert 'QFrame#ToolbarFrame QFrame#OperationFrame' in THEME
    assert 'QPushButton#CancelScanAction' in THEME
    assert 'QPushButton#ExportAction { background:#123f46;' in THEME


def test_player_is_global_footer_without_duplicate_branding_and_has_richer_card():
    assert 'FooterSeparator' in PLAYER
    assert 'QFrame#VariantDPlayerSurface' in THEME
    assert 'self.surface = VariantDPlayerSurface' in PLAYER
    assert 'ALO Music v{__version__}' not in PLAYER
    assert 'Powered by Damian' not in PLAYER
    assert 'GitHub Issues' not in PLAYER
    assert 'outer.addWidget(self.player)' in MAIN


def test_player_is_compact_elegant_and_keeps_seek_volume_controls():
    # Cover/timeline geometry is exercised by test_player_reference_followup.
    assert 'self.play.setFixedSize(50, 50)' in PLAYER
    assert 'row.addWidget(self.seek, 3)' in PLAYER
    assert 'self.volume.setFixedWidth(88)' in PLAYER
    assert 'QPushButton#VariantDPlayButton' in THEME
    assert 'QSlider#VariantDVolume::groove:horizontal' in THEME


def test_library_detail_actions_are_pinned_outside_scroll_area():
    assert "actions_bar.setObjectName('PinnedDetailActions')" in LIBRARY
    assert 'detail_outer.addWidget(self.detail_scroll, 1)' in LIBRARY
    assert 'detail_outer.addWidget(actions_bar)' in LIBRARY
    assert LIBRARY.index('detail_outer.addWidget(self.detail_scroll, 1)') < LIBRARY.index('detail_outer.addWidget(actions_bar)')
    assert 'QFrame#PinnedDetailActions' in THEME


def test_library_details_keep_dense_cover_and_data_sections():
    assert 'self.detail.setMinimumWidth(640)' in LIBRARY
    assert 'summary_row = QHBoxLayout()' in LIBRARY
    assert 'summary_row.addWidget(self.completeness_card, 1)' in LIBRARY
    assert "track_card.setObjectName('LibraryTrackDataCard')" in LIBRARY
    assert "self.technical_panel.setObjectName('LibraryTechnicalCard')" in LIBRARY
    assert "('duration', 'Czas trwania'" in LIBRARY
    assert 'self.split.setSizes([960, 640])' in LIBRARY


def test_library_table_navigation_and_selection_stays_stable():
    assert 'for item in items:' in LIBRARY
    assert 'self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)' in LIBRARY
    assert 'resizeColumnToContents' not in LIBRARY
    assert 'self.table.clicked.connect(self._stabilize_clicked_row)' not in LIBRARY
    assert 'class StableTableView' in LIBRARY
    assert 'horizontalScrollBar().setValue(0)' in LIBRARY
    assert 'setTextElideMode(Qt.TextElideMode.ElideRight)' in LIBRARY


def test_library_details_button_is_above_panel_and_right_aligned():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    from audio_library_organizer.ui.library_page import LibraryPage

    app = QApplication.instance() or QApplication([])
    page = LibraryPage()
    page.resize(1600, 900); page.show(); app.processEvents()
    try:
        button = page.details_btn.geometry().translated(page.details_btn.parentWidget().mapTo(page, QPoint()))
        panel = page.detail.geometry().translated(page.detail.parentWidget().mapTo(page, QPoint()))
        assert page.details_btn.objectName() == 'DetailsToggle'
        assert button.bottom() < panel.top()
        assert abs(button.right() - panel.right()) <= 1
        assert button.center().y() == page.collection_btn.geometry().center().y()
    finally:
        page.close()


def test_library_rounds_bpm_and_never_shows_raw_seconds_in_details():
    assert 'display_bpm(track.bpm)' in LIBRARY
    assert "({t.duration_seconds:.2f} s)" not in LIBRARY


def test_library_has_status_first_filters_without_decision_navigation():
    for text in ('Gotowe', 'Duplikaty', 'Do sprawdzenia', 'Nie wybieram', 'Brak okładki', 'Brak roku'):
        assert text in LIBRARY
    assert 'Ręcznie edytowane' not in LIBRARY
    assert 'Do decyzji' not in LIBRARY
    assert "QPushButton('← Poprzedni')" not in LIBRARY
    assert "QPushButton('Następny →')" not in LIBRARY
    assert 'decision_queue(self._tracks)' not in LIBRARY


def test_duplicate_page_exposes_explicit_decision_for_each_file_and_individual_editor():
    assert 'decision_requested = Signal(object, str)' in DUPLICATES
    assert 'edit_track_requested = Signal(object)' in DUPLICATES
    assert 'separate_version_requested = Signal(object, object)' not in DUPLICATES
    for label in ('ZACHOWAJ', 'NIE WYBIERAM', 'EDYTUJ'):
        assert label in DUPLICATES
    for icon in ("alo_icon('status'", "alo_icon('cancel'", "alo_icon('edit'"):
        assert icon in DUPLICATES
    assert "QPushButton('◈ DUPLIKAT')" not in DUPLICATES
    assert "QPushButton('☆ OSOBNA WERSJA')" not in DUPLICATES
    assert 'edit_group_requested' not in DUPLICATES
    assert 'Edytuj dane grupy' not in DUPLICATES
    assert 'SUGESTIA PROGRAMU ★' not in DUPLICATES
    assert 'QTableWidget' in DUPLICATES
    assert 'ALO niczego nie wybiera' in DUPLICATES
    assert 'self.duplicates.decision_requested.connect(self._duplicate_decision)' in MAIN
    assert 'self.duplicates.edit_track_requested.connect(self._edit_duplicate_track)' in MAIN


def test_duplicate_tab_displays_live_count_inside_navigation_button():
    assert 'duplicate_group_count(tracks)' in MAIN
    assert 'setText(f"{duplicate_label} ({duplicate_groups})")' in MAIN
    assert 'duplicate_nav_badge' not in MAIN


def test_filename_settings_offer_field_selection_and_live_preview():
    assert 'Format nazwy pliku' in MAIN
    assert 'self.filename_checks' in MAIN
    for field, label in (
        ('Artist', 'Wykonawca'), ('Title', 'Tytuł'), ('Version', 'Wersja / Remix'),
        ('Year', 'Rok'), ('BPM', 'BPM'), ('Genre', 'Gatunek'), ('Album', 'Album'),
    ):
        assert f"('{field}', '{label}'" in MAIN
    assert 'self.filename_preview' in MAIN
    assert 'template_from_filename_fields' in MAIN
    assert 'self.filename_override = QLineEdit' in EDITOR
    assert "QLabel('Nazwa wynikowa')" in EDITOR
    assert 'Przywróć nazwę z metadanych' in EDITOR


def test_settings_are_visually_separated_and_have_folder_organization_and_target_highlight():
    assert "setObjectName('LocationCard')" in MAIN
    assert "setObjectName('NamingCard')" in MAIN
    assert "setObjectName('IntegrationCard')" in MAIN
    assert 'Organizacja folderu GOTOWE' in MAIN
    assert "self.folder_org_buttons['none'] = QRadioButton('Bez podfolderów')" in MAIN
    assert "self.folder_org_buttons['artist'] = QRadioButton('Według wykonawcy')" in MAIN
    assert "self.folder_org_buttons['genre'] = QRadioButton('Według gatunku')" in MAIN
    assert 'LibraryAvailabilityStatus' in MAIN
    assert 'ChangeLibraryLocationAction' in MAIN
    assert 'Otwórz GOTOWE' not in MAIN
    for selector in ('QFrame#SettingsSection', 'QFrame#NamingCard', 'QFrame#ProviderCard', 'QFrame#ContactFooter', 'QLabel#LibraryAvailabilityStatus'):
        assert selector in THEME


def test_settings_have_api_help_and_compact_contact_footer_only_in_settings():
    assert 'help_requested = Signal(str)' in MAIN
    assert 'Jak zdobyć klucz?' in MAIN
    assert 'Powered by Damian' in MAIN
    assert 'https://github.com/DamianPPD/ALO-Music-Public/issues' in MAIN
    assert 'mailto:' not in MAIN
    assert 'O programie' not in MAIN
    assert "setObjectName('ContactFooter')" in MAIN
    assert 'self.settings_page.help_requested.connect(self._open_help_topic)' in MAIN


def test_metadata_editor_has_large_cover_proposals_and_keeps_explicit_placeholder_choice():
    assert 'Okładka (wybierana z listy)' in EDITOR
    assert 'self.cover_main_preview.setFixedSize(288, 288)' in EDITOR
    assert "self.choose_cover_button = QPushButton('Dodaj')" in EDITOR
    assert "self.search_cover_button = QPushButton('Szukaj okładki online')" in EDITOR
    assert 'Więcej okładek online…' not in EDITOR
    assert "entries.append(('placeholder', 'BRAK OKŁADKI'))" in EDITOR
    assert "track.field_source_values.get('__cover__'" in EDITOR
    assert 'cover_choice' in EDITOR
    assert (ROOT / 'src/audio_library_organizer/assets/no_cover.png').exists()
    assert (ROOT / 'BRAK_OKLADKI.png').exists()


def test_sha256_is_not_in_library_quick_details():
    assert "self.detail_labels['hash']" not in LIBRARY
    assert "('hash', 'SHA-256')" not in LIBRARY


def test_persistent_paths_and_scan_cancel_are_clear():
    assert 'Biblioteka docelowa jest zapamiętywana między uruchomieniami' in MAIN
    assert 'Anuluj skanowanie' in MAIN
    assert 'QPushButton#CancelScanAction' in THEME


def test_metadata_editor_keeps_individual_fields_recognition_comparison_and_inline_player():
    for label in ('Wykonawca', 'Tytuł / wersja', 'Rok', 'Gatunek', 'BPM', 'Album / Release', 'Discogs URL', 'Komentarz'):
        assert label in EDITOR
    assert "metadata.setObjectName('PrimaryMetadataCard')" in EDITOR
    assert "status_card.setObjectName('MetadataStatusCompact')" not in EDITOR
    assert "recognition.setObjectName('RecognitionDetailsPopup')" in EDITOR
    assert "comparison.setObjectName('SourceComparisonCard')" in EDITOR
    assert "self.source_legend_button.setText('')" in EDITOR
    assert "self.source_table = SourceComparisonTable(0, 7)" in EDITOR
    assert "use_button = QPushButton(ui_text(self, 'Użyj danych'))" in EDITOR
    assert 'self.source_table.resize_to_rows()' in EDITOR
    assert "self.compact_player = CompactPlayerBar" in EDITOR
    assert 'AKTUALNY STATUS:' not in EDITOR


def test_metadata_editor_inline_player_keeps_seek_and_volume():
    compact = PLAYER.split('class CompactPlayerBar', 1)[1]
    assert 'ClickableCoverLabel' not in compact
    # The reference layout now includes track identity and a flexible seek bar.
    assert 'self.surface = VariantDPlayerSurface' in compact
    assert 'self.volume = self.surface.volume' in compact
    assert 'self.seek = self.surface.seek' in compact


def test_navigation_buttons_use_icons_and_workflow_colors_follow_approved_reference():
    assert 'self.nav_icon_ids = (' in MAIN
    assert "self.nav_icon_ids = ('nav_start', 'nav_library', 'nav_duplicates', 'nav_folders', 'nav_help', 'nav_settings')" in MAIN
    assert 'alo_icon(' in MAIN
    assert 'QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#Primary {' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#ExportAction {' in THEME
    assert 'QFrame#ToolbarFrame QPushButton#AddFilesAction {' in THEME


def test_provider_settings_include_keyless_apple_and_musicbrainz_cards():
    assert "apple_name = QLabel('Apple / iTunes')" in MAIN
    assert "self.apple_status = QLabel('Nie wymaga klucza API')" in MAIN
    assert "self.musicbrainz_status = QLabel('Nie wymaga klucza API')" in MAIN
    assert 'Każde źródło działa niezależnie.' in MAIN
