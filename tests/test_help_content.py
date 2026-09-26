from audio_library_organizer.help_content import HELP_TOPICS


def test_help_contains_required_professional_topics():
    required = {'Pierwsze uruchomienie','Bezpieczeństwo plików','Duplikaty','Rozpoznawanie utworów','BPM','Okładki','Statusy i zatwierdzanie','Odtwarzacz'}
    assert required.issubset(HELP_TOPICS)
    assert all(len(HELP_TOPICS[name].strip()) > 80 for name in required)


def test_help_includes_api_setup_and_decision_explanation():
    assert 'Konfiguracja AcoustID i Discogs' in HELP_TOPICS
    assert 'Jak program podejmuje decyzje' in HELP_TOPICS
    assert 'Rozwiązywanie problemów' in HELP_TOPICS
    assert 'acoustid.org/new-application' in HELP_TOPICS['Konfiguracja AcoustID i Discogs']
    assert 'discogs.com/settings/developers' in HELP_TOPICS['Konfiguracja AcoustID i Discogs']


def test_help_includes_manual_genre_locking_and_rescan_guidance():
    assert 'Ręczne poprawki i blokady' in HELP_TOPICS
    assert 'Ponowne skanowanie' in HELP_TOPICS
    assert 'gatunek' in HELP_TOPICS['Ręczne poprawki i blokady'].casefold()
    assert 'niezmienione' in HELP_TOPICS['Ponowne skanowanie'].casefold()


def test_api_key_help_is_step_by_step_and_explains_where_to_paste_keys():
    body = HELP_TOPICS['Konfiguracja AcoustID i Discogs'].casefold()
    assert '1.' in body and '2.' in body and '3.' in body
    assert 'ustawienia' in body
    assert 'acoustid client key' in body
    assert 'discogs token' in body
    assert 'nie wysyłaj' in body or 'nie udostępniaj' in body


def test_help_explains_multiple_valid_duplicate_versions_and_filename_templates():
    duplicate_help = HELP_TOPICS['Duplikaty'].casefold()
    assert '✎ edytuj' in duplicate_help or 'edytuj' in duplicate_help
    assert 'tabela' in duplicate_help
    assert 'nie rekomenduje zwycięzcy' in duplicate_help
    assert 'rodzinę wersji' in duplicate_help
    assert 'osobnymi wersjami' in duplicate_help
    assert 'Format nazwy pliku' in HELP_TOPICS
    naming_help = HELP_TOPICS['Format nazwy pliku']
    assert '{Artist}' in naming_help and '{Version}' in naming_help and '{BPM}' in naming_help


def test_api_help_uses_visually_separated_cards_and_clear_key_names():
    body = HELP_TOPICS['Konfiguracja AcoustID i Discogs']
    assert body.count('class="help-card"') >= 3
    assert 'Application API Key' in body
    assert 'Personal Access Token' in body
    assert 'MusicBrainz' in body and 'nie wymaga' in body
    assert 'class="important"' in body


def test_help_matches_v045_duplicate_and_editor_workflow():
    duplicate_help = HELP_TOPICS['Duplikaty']
    editor_help = HELP_TOPICS['DO SPRAWDZENIA i cofanie zmian']
    assert 'program proponuje' not in duplicate_help.casefold()
    assert 'A/B/C' not in duplicate_help
    assert 'PRZED / PO ZMIANIE' not in editor_help
    assert 'tabela' in duplicate_help.casefold()
    assert 'rodzin' in duplicate_help.casefold()


def test_help_about_and_rescan_do_not_claim_old_source_autorestore_behavior():
    about = HELP_TOPICS['O programie']
    rescan = HELP_TOPICS['Ponowne skanowanie']
    assert '0.4.24' in about
    assert 'źródła, lokalizacja biblioteki i wyniki skanowania są przywracane' not in about.casefold()
    assert 'zapamiętuje foldery źródłowe' not in rescan.casefold()
    assert 'histori' in rescan.casefold()
