from audio_library_organizer.ui.i18n import translate_static_text


def test_library_manager_new_destination_and_history_copy_translates_to_english():
    assert translate_static_text('Folder biblioteki / zapisu', 'en') == 'Library / output folder'
    assert translate_static_text('Wybierz folder zapisu', 'en') == 'Choose output folder'
    assert translate_static_text('Skanowane źródła (7)', 'en') == 'Scanned sources (7)'
    assert translate_static_text('Ostatni skan: 13.09.2026 04:10   •   Pliki: 1240', 'en') == 'Last scan: 13.09.2026 04:10   •   Files: 1240'
    html = '<a href="open">📂 C:\\ALO  ↗  Otwórz w Eksploratorze</a>'
    assert 'Open in Explorer' in translate_static_text(html, 'en')


def test_duplicate_table_and_version_family_new_copy_translates_to_english():
    expected = {
        'Wariant': 'Variant',
        'Nazwa pliku': 'Filename',
        'Długość': 'Duration',
        'Format': 'Format',
        'Bitrate': 'Bitrate',
        'Rozmiar': 'Size',
        'Decyzja': 'Decision',
        'Rodzina wersji': 'Version family',
    }
    for pl, en in expected.items():
        assert translate_static_text(pl, 'en') == en
    assert translate_static_text('Rodzina wersji: 4 utwory', 'en') == 'Version family: 4 tracks'
