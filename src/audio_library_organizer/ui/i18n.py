from __future__ import annotations

import re

CATALOG: dict[str, dict[str, str]] = {
    'nav.start': {'pl': 'Start', 'en': 'Start'},
    'nav.library': {'pl': 'Biblioteka', 'en': 'Library'},
    'nav.duplicates': {'pl': 'Duplikaty', 'en': 'Duplicates'},
    'nav.collections': {'pl': 'Moje foldery MP3', 'en': 'My MP3 folders'},
    'nav.help': {'pl': 'Pomoc', 'en': 'Help'},
    'nav.settings': {'pl': 'Ustawienia', 'en': 'Settings'},
    'action.scan': {'pl': 'Skanuj foldery', 'en': 'Scan folders'},
    'action.add_files': {'pl': 'Dodaj utwory do biblioteki', 'en': 'Add tracks to library'},
    'action.add_files_tooltip': {'pl': 'Dodaj pliki audio do biblioteki ALO Music', 'en': 'Add audio files to the ALO Music library'},
    'action.identify_online': {'pl': 'Rozpoznaj utwory online', 'en': 'Identify tracks online'},
    'action.cancel_online': {'pl': 'Anuluj rozpoznawanie', 'en': 'Cancel identification'},
    'action.resume_online': {'pl': 'Wznów rozpoznawanie', 'en': 'Resume identification'},
    'action.review': {'pl': 'Sprawdź w Bibliotece', 'en': 'Review in Library'},
    'action.export': {'pl': 'Utwórz pliki wynikowe', 'en': 'Create output files'},
    'settings.title': {'pl': 'Ustawienia i lokalizacje plików', 'en': 'Settings and file locations'},
    'settings.language': {'pl': 'Język', 'en': 'Language'},
    'settings.normalization': {'pl': 'Normalizacja nazw', 'en': 'Name normalization'},
    'settings.backup': {'pl': 'Kopia bezpieczeństwa ALO', 'en': 'ALO backup'},
    'library.active': {'pl': 'Aktywna biblioteka', 'en': 'Active library'},
    'library.manage': {'pl': 'Biblioteki', 'en': 'Libraries'},
}


def tr(key: str, language: str = 'pl') -> str:
    language = language if language in {'pl', 'en'} else 'pl'
    entry = CATALOG.get(key)
    if not entry:
        return key
    return entry.get(language) or entry.get('pl') or key


TEXT_MAP_EN: dict[str, str] = {
    'Wyjście audio': 'Audio output',
    'Brak wyjścia audio': 'No audio output',
    # navigation / main workflow
    'Start': 'Start', 'Biblioteka': 'Library', 'Biblioteki': 'Libraries', 'Duplikaty': 'Duplicates',
    'Moje foldery MP3': 'My MP3 folders', 'Pomoc': 'Help', 'Ustawienia': 'Settings',
    'Skanuj foldery': 'Scan folders', 'Dodaj utwory do biblioteki': 'Add tracks to library',
    'Dodaj pliki audio do biblioteki ALO Music': 'Add audio files to the ALO Music library',
    'Szybki dostęp': 'Quick access', 'Pliki wynikowe / GOTOWE': 'Output files / READY',
    'Niewybrane': 'Not selected', 'Raporty': 'Reports', 'Kopiuj ścieżkę': 'Copy path',
    'Otwórz folder w Eksploratorze': 'Open folder in File Explorer', 'Dostępna': 'Available', 'Niedostępna': 'Unavailable',
    'Rozpoznaj utwory online': 'Identify tracks online', 'Anuluj rozpoznawanie': 'Cancel identification',
    'Wznów rozpoznawanie': 'Resume identification', 'Sprawdź w Bibliotece': 'Review in Library',
    'Utwórz pliki': 'Create files', 'Utwórz pliki wynikowe': 'Create output files',
    'BIEŻĄCA OPERACJA': 'CURRENT OPERATION', 'GOTOWY': 'READY', 'Wybierz etap pracy powyżej.': 'Choose a workflow step above.',
    'Etapy pracy': 'Workflow', 'Stan biblioteki': 'Library status', 'CO TERAZ?': 'WHAT NEXT?',
    'Dostępne pliki': 'Available files', 'Brakujące': 'Missing', 'Liczba gatunków': 'Genres',
    'Najczęstszy gatunek': 'Top genre', 'Średnie BPM': 'Average BPM', 'Okładki': 'Covers',
    'Rozpoznane online': 'Identified online', 'Rozmiar biblioteki': 'Library size', 'Podejrzane dane': 'Suspicious data',
    'Odśwież / przeskanuj bibliotekę': 'Refresh / rescan library', 'Pracuj dalej': 'Continue',

    # settings
    'Ustawienia i lokalizacje plików': 'Settings and file locations',
    'Nazewnictwo plików': 'Filename naming', 'Rozpoznawanie online': 'Online identification',
    'Interfejs': 'Interface', 'Zaawansowane': 'Advanced',
    'Wybierz główną lokalizację biblioteki ALO.': 'Choose the main ALO library location.',
    'Ustal sposób tworzenia nazw plików wynikowych.': 'Choose how output filenames are created.',
    'Dostosuj sposób korzystania ze źródeł internetowych.': 'Configure how online sources are used.',
    'Połącz ALO ze źródłami używanymi podczas rozpoznawania utworów.': 'Connect ALO to the sources used for track identification.',
    'Dostosuj język i zachowanie programu.': 'Configure the app language and behavior.',
    'Opcje techniczne, diagnostyczne i serwisowe.': 'Technical, diagnostic and maintenance options.',
    'Biblioteka dostępna': 'Library available', 'Biblioteka niedostępna': 'Library unavailable',
    'Zmień lokalizację': 'Change location',
    'Wybierz nową lokalizację biblioteki': 'Choose a new library location',
    'Zmieniono lokalizację biblioteki głównej.': 'The Main Library location has been changed.',
    'Wybrana lokalizacja koliduje z inną biblioteką ALO.': 'The selected location conflicts with another ALO library.',
    'Wybrana lokalizacja koliduje ze źródłem skanowania ALO.': 'The selected location conflicts with an ALO scan source.',
    'Zmienić lokalizację biblioteki?': 'Change the library location?',
    'ALO przełączy Bibliotekę główną na wybrany folder:': 'ALO will switch the Main Library to the selected folder:',
    'Ta operacja nie przenosi ani nie usuwa plików z dotychczasowej lokalizacji. ': 'This operation does not move or delete files from the current location. ',
    'Jeśli chcesz zachować tamte dane w nowym miejscu, skopiuj je osobno przed przełączeniem.': 'To keep that data in the new location, copy it separately before switching.',
    'Nie można użyć lokalizacji biblioteki': 'Cannot use the library location',
    'Język interfejsu': 'Interface language', 'Język': 'Language', 'Polski': 'Polish', 'English': 'English',
    'Zapisz język': 'Save language', '✓ Zapisano': '✓ Saved',
    'Wybierz język interfejsu. Możesz go zmienić w dowolnym momencie.': 'Choose the interface language. You can change it at any time.',
    'Lokalizacje Biblioteki głównej': 'Main Library locations',
    'Tutaj widzisz wyłącznie stałą Bibliotekę główną. Dodatkowe biblioteki są zarządzane osobno.': 'Only the permanent Main Library is shown here. Additional libraries are managed separately.',
    'Lokalizacje biblioteki': 'Library locations', 'Muzyka do skanowania': 'Music to scan',
    'Folder biblioteki:': 'Library folder:', 'Lokalizacja bazowa:': 'Base location:', 'Pełna ścieżka:': 'Full path:',
    'Wolne miejsce: —': 'Free space: —', 'GOTOWE': 'READY', 'NIE WYBRANE': 'NOT SELECTED',
    'DO SPRAWDZENIA': 'REVIEW', 'MOJE FOLDERY MP3': 'MY MP3 FOLDERS', 'RAPORTY': 'REPORTS',
    'Biblioteki…': 'Libraries…', 'Otwórz': 'Open', 'Otwórz folder': 'Open folder',
    'Format nazwy pliku': 'Filename format', 'Wykonawca': 'Artist', 'Tytuł': 'Title', 'Wersja / Remix': 'Version / Remix',
    'Rok': 'Year', 'Gatunek': 'Genre', 'Album': 'Album', 'Przywróć domyślny format': 'Restore default format',
    'Pola wyboru tworzą standardowy układ; szablon można też poprawić ręcznie.': 'The checkboxes build the standard layout; you can also edit the template manually.',
    'Element wymagany — nie można wyłączyć': 'Required item — cannot be disabled',
    'Normalizacja nazw': 'Name normalization', 'Automatycznie poprawiaj nazwy przy zapisie': 'Automatically normalize names on save',
    'Włączona': 'Enabled', 'Znajdź': 'Find', 'Zamień na': 'Replace with', '＋ Dodaj regułę': '＋ Add rule',
    'Edytuj zaznaczoną': 'Edit selected', 'Usuń zaznaczoną': 'Remove selected', 'Przywróć domyślne': 'Restore defaults',
    'Kopia bezpieczeństwa ALO': 'ALO backup', 'Utwórz kopię': 'Create backup', 'Przywróć kopię': 'Restore backup',
    'Integracje i klucze API': 'Integrations and API keys', 'Jak zdobyć klucz?': 'How to get a key?',
    'Otwórz stronę': 'Open website', 'Skonfigurowano': 'Configured', 'Brak klucza': 'Missing key',
    'Nie wymaga klucza API': 'No API key required',
    'Otwórz stronę AcoustID': 'Open AcoustID website', 'Otwórz stronę Discogs': 'Open Discogs website',
    'Po skanie automatycznie uruchom rozpoznawanie online': 'Automatically identify online after scanning',
    'Zapisz klucze': 'Save API keys', '✓ Klucze zapisane': '✓ API keys saved', 'Zapisz ustawienia': 'Save settings',
    '✓ Ustawienia zapisane': '✓ Settings saved', 'Kontakt:': 'Contact:',
    'Zachowanie rozpoznawania': 'Identification behavior',
    'Ustaw, czy ALO ma automatycznie rozpocząć rozpoznawanie po zakończeniu skanowania.': 'Choose whether ALO should start identification automatically after scanning.',
    'Ustawienia domyślne': 'Default settings',
    'Przywróć ustawienia domyślne': 'Restore default settings',
    'Przywróć bezpieczne preferencje bez usuwania biblioteki, utworów ani kluczy API.': 'Restore safe preferences without deleting the library, tracks or API keys.',
    'Przywrócić bezpieczne ustawienia domyślne?': 'Restore safe default settings?',
    'ALO przywróci tylko nieszkodliwe preferencje programu:': 'ALO will restore only harmless application preferences:',
    'format i organizację nazw plików': 'filename format and organization',
    'automatyczne rozpoznawanie po skanie': 'automatic identification after scanning',
    'normalizację nazw i jej reguły': 'name normalization and its rules',
    'domyślne zachowanie interfejsu': 'default interface behavior',
    'Biblioteka, utwory, metadane, pliki, historia, język i klucze API pozostaną bez zmian.': 'The library, tracks, metadata, files, history, language and API keys will remain unchanged.',
    'Przywrócono ustawienia domyślne': 'Default settings restored',

    # library manager / wizard
    'Biblioteka główna': 'Main Library', 'Dodatkowe biblioteki': 'Additional libraries',
    'AKTYWNA': 'ACTIVE', '● AKTYWNA': '● ACTIVE', 'Kliknij, aby przełączyć': 'Click to switch',
    'Ustaw jako aktywną': 'Set active', '✓ Aktywna': '✓ Active', 'Kliknij, aby zaznaczyć': 'Click to select', 'Kliknij bibliotekę, aby ją zaznaczyć. Dopiero przycisk „Ustaw jako aktywną” przełącza bibliotekę. Zielony kolor oznacza bibliotekę aktualnie używaną przez ALO.': 'Click a library to select it. Only the “Set active” button switches libraries. Green always marks the library currently used by ALO.', 'Zmień nazwę': 'Rename', 'Nazwa biblioteki:': 'Library name:', 'Nie można zmienić nazwy': 'Cannot rename library', 'Zacznij od nowa': 'Start over', 'Najpierw zapisz lub odrzuć zmiany w otwartym edytorze metadanych.': 'Save or discard changes in the open metadata editor first.',
    'AKTYWNA BIBLIOTEKA': 'ACTIVE LIBRARY', 'Przełącz na główną': 'Switch to Main Library',
    'Kliknij bibliotekę, aby przełączyć. Aktywna pozycja jest wyraźnie oznaczona.': 'Click a library to switch. The active item is clearly highlighted.',
    'Kliknij, aby przełączyć': 'Click to switch', 'Kliknij, aby zarządzać bibliotekami': 'Click to manage libraries',
    '＋ Nowa biblioteka': '＋ New library', 'Usuń bibliotekę': 'Remove library',
    'Resetuj ALO do czystego stanu': 'Reset ALO to a clean state',
    'Usuwa bazy i ustawienia ALO, ale nie usuwa plików muzycznych z dysku.': 'Removes ALO databases and settings, but does not delete music files from disk.',
    'Otwórz folder źródłowy': 'Open source folder', 'Utwórz nową bibliotekę': 'Create a new library',
    'Nazwa biblioteki': 'Library name', 'Folder z muzyką': 'Music folder', 'Nie wybrano folderu': 'No folder selected',
    'Wybierz folder z muzyką': 'Choose music folder', 'Utwórz bibliotekę': 'Create library', 'Anuluj': 'Cancel',
    'Wybierz folder z muzyką dla nowej biblioteki': 'Choose a music folder for the new library',
    'Biblioteka główna pozostanie bez zmian.': 'The Main Library will remain unchanged.',
    'Pliki muzyczne nie zostaną skopiowane ani usunięte.': 'Music files will not be copied or deleted.',
    'Nie można dodać biblioteki': 'Cannot add library',

    # library page
    'Szczegóły utworu': 'Track details', 'Status': 'Status', 'Długość': 'Duration', 'Jakość': 'Quality',
    'Szukaj: wykonawca, tytuł, album…': 'Search: artist, title, album…', 'Gatunki, np. Trance, Vocal': 'Genres, e.g. Trance, Vocal',
    'BPM od': 'BPM from', 'BPM do': 'BPM to', '★ Wszystkie utwory': '★ All tracks',
    '🟢 Gotowe': '🟢 Ready', '🟣 Duplikaty': '🟣 Duplicates', '🟠 Do sprawdzenia': '🟠 Review',
    '⚪ Nie wybieram': '⚪ Not selected', 'Brak okładki': 'No cover',
    'Brak roku': 'No year', 'Ręcznie edytowane': 'Manually edited', 'Gatunek dla zaznaczonych': 'Genre for selected',
    'Zaznacz wszystko': 'Select all', 'Utwórz folder z zaznaczonych': 'Create folder from selected',
    'Utwórz playlistę': 'Create playlist', 'ⓘ Szczegóły utworu ▸': 'ⓘ Track details ▸', 'ⓘ Ukryj szczegóły ◂': 'ⓘ Hide details ◂',
    'Edytuj metadane': 'Edit metadata', 'Pokaż w Eksploratorze': 'Show in Explorer', '▶ Odtwórz': '▶ Play',
    'Wpisz kilka gatunków po przecinku. Utwór musi zawierać wszystkie podane gatunki.': 'Enter multiple genres separated by commas. A track must contain all listed genres.',

    # metadata editor
    'Edytuj metadane': 'Edit metadata', 'Edytuj metadane przed zatwierdzeniem': 'Edit metadata before approval',
    '🔒 Zablokuj dane przed ponownym rozpoznaniem online': '🔒 Lock data against online re-identification',
    'Zablokuj dane przed ponownym rozpoznaniem online': 'Lock data against online re-identification',
    '🔓 Zablokuj online': '🔓 Lock online', '🔒 Zablokowane': '🔒 Locked',
    'Zablokowany utwór jest pomijany przez AcoustID, MusicBrainz i Discogs. Ręczna edycja nadal działa.': 'A locked track is skipped by AcoustID, MusicBrainz and Discogs. Manual editing still works.',
    'Zablokowany przed ponownym rozpoznaniem online': 'Locked against online re-identification',
    '● Niezapisane zmiany': '● Unsaved changes', 'DANE SPRZED ROZPOZNANIA ONLINE': 'DATA BEFORE ONLINE IDENTIFICATION',
    '↶ Przywróć dane sprzed online': '↶ Restore pre-online data', 'POTWIERDZONE': 'CONFIRMED', 'BRAKI': 'MISSING', 'PEWNOŚĆ': 'CONFIDENCE',
    'Dane kompletne': 'Data complete', 'Wszystkie wymagane pola są uzupełnione': 'All required fields are filled in',
    'Brak wyniku rozpoznania': 'No identification result', 'Dopasowanie bardzo wysokie': 'Very high match',
    'Dopasowanie wymaga krótkiej kontroli': 'Match needs a quick review', 'Niska pewność — sprawdź dane': 'Low confidence — review the data',
    'Wybór okładki': 'Cover selection', 'OBECNA': 'CURRENT', 'POBRANA': 'DOWNLOADED', 'WŁASNA': 'CUSTOM', 'BRAK OKŁADKI': 'NO COVER',
    'AKTUALNY STATUS:': 'CURRENT STATUS:', 'Wymaga sprawdzenia': 'Needs review', 'Pilna kontrola': 'Urgent review',
    '↗ Otwórz link': '↗ Open link', '↗ Otwórz w Discogs': '↗ Open in Discogs', 'Odtwórz jako następny': 'Play next',
    'Źródło:': 'Source:', 'Następny:': 'Next:', 'TERAZ GRA': 'NOW PLAYING',
    'Plik lokalny': 'Local file', 'Edytor metadanych': 'Metadata editor',
    'WYBIERZ': 'SELECT', 'WYBIERZ PLIK…': 'CHOOSE FILE…', 'DANE GŁÓWNE': 'MAIN DATA', 'DANE DODATKOWE': 'ADDITIONAL DATA',
    'Tytuł / wersja': 'Title / version', 'Album / Release': 'Album / Release', 'Komentarz': 'Comment', 'Źródła:': 'Sources:',
    'PRZED ZMIANĄ': 'BEFORE CHANGE', 'PO ZMIANIE': 'AFTER CHANGE', 'Nazwa wynikowa': 'Output filename',
    'Przywróć nazwę automatyczną': 'Restore automatic name', '↶ Cofnij ostatnią zmianę': '↶ Undo last change',
    'Anuluj zmiany': 'Cancel changes', 'Zapisz zmiany': 'Save changes', 'Oznacz jako GOTOWE': 'Mark READY',
    'Odznacz jako GOTOWE': 'Unmark READY', 'Zamknij': 'Close', 'ODSŁUCH': 'PREVIEW',
    'np. 2009': 'e.g. 2009', 'Nieprawidłowy rok': 'Invalid year',
    'Rok musi składać się dokładnie z 4 cyfr, np. 2009.': 'Year must contain exactly 4 digits, e.g. 2009.',
    'Wybierz z podpowiedzi albo wpisz własny gatunek. Pierwszy gatunek jest główny.': 'Choose a suggestion or enter your own genre. The first genre is primary.',

    # collections / duplicates / player
    'Otwórz MOJE_FOLDERY_MP3': 'Open MY_MP3_FOLDERS', 'Dodaj z Biblioteki': 'Add from Library',
    'Utwórz playlistę M3U8': 'Create M3U8 playlist', 'Usuń zaznaczony plik z folderu': 'Remove selected file from folder',
    'Odśwież': 'Refresh', 'Moje foldery': 'My folders', 'Moje pliki': 'My files', 'Plik w folderze': 'File in folder', 'Rozmiar': 'Size',
    'Folder': 'Folder', 'Utwory': 'Tracks', 'Wybierz folder w zakładce „Moje foldery”.': 'Choose a folder in the “My folders” tab.',
    'Brak potencjalnych duplikatów': 'No potential duplicates', 'Wybierz grupę potencjalnych duplikatów': 'Choose a potential duplicate group',
    'Odrzuć': 'Reject',

    # generic
    'Otwórz folder': 'Open folder', 'Zamknij': 'Close', 'Usuń zaznaczony': 'Remove selected',
    'Brak plików': 'No files', 'Brak zaznaczenia': 'No selection', 'Błąd': 'Error', 'Ładowanie…': 'Loading…',
    'ŹRÓDŁA DANYCH': 'DATA SOURCES', 'ŹRÓDŁO': 'SOURCE', 'RĘCZNIE': 'MANUAL', 'Ręcznie': 'Manual',
    'Przywrócone': 'Restored', 'WŁASNA': 'CUSTOM', 'Niedostępna': 'Unavailable',
    'Kliknij okładkę, aby powiększyć': 'Click the cover to enlarge', 'Kliknij, aby powiększyć okładkę': 'Click to enlarge the cover',
    'Podgląd okładki': 'Cover preview', 'Powiększona okładka': 'Enlarged cover',
}


# Longer strings that are easier to keep grouped separately.
TEXT_MAP_EN.update({
    'Źródła i biblioteka są zapamiętywane między uruchomieniami. Oryginalne pliki nie są modyfikowane.': 'Sources and the library are remembered between runs. Original files are never modified.',
    'Wybierz dane umieszczane w nazwie. Domyślnie: Wykonawca - Tytuł (Wersja) (Rok) [BPMbpm].': 'Choose the data included in the filename. Default: Artist - Title (Version) (Year) [BPMbpm].',
    'Automatycznie ujednolica typowe określenia muzyczne przy zapisie, np. dj → DJ, club → Club, feat → Feat. Każdą regułę możesz wyłączyć lub edytować.': 'Automatically normalizes common music terms when saving, e.g. dj → DJ, club → Club, feat → Feat. Each rule can be disabled or edited.',
    'Kopia obejmuje bazę ALO i konfigurację programu. Pliki muzyczne nie są kopiowane.': 'The backup includes the ALO database and app configuration. Music files are not copied.',
    'Każda usługa ma krótką instrukcję. Kliknij „Jak zdobyć klucz?”, jeśli konfigurujesz ją pierwszy raz.': 'Each service has a short guide. Click “How to get a key?” if you are configuring it for the first time.',
    'Biblioteka główna jest stała. Możesz dodać osobne biblioteki dla innych folderów z muzyką. Każda biblioteka ma własną bazę ALO i nie miesza plików z pozostałymi.': 'The Main Library is permanent. You can add separate libraries for other music folders. Each library has its own ALO database and does not mix files with the others.',
    'Wybierz folder z muzyką. ALO utworzy dla niego osobną bazę i pokaże tylko pliki z tego folderu. Biblioteka główna pozostanie bez zmian.\n\nPliki muzyczne nie zostaną skopiowane ani usunięte.': 'Choose a music folder. ALO will create a separate database for it and show only files from that folder. The Main Library will remain unchanged.\n\nMusic files will not be copied or deleted.',
    'Fizyczne kopie wybranych utworów. Ten katalog jest wyłączony ze skanowania głównej biblioteki.': 'Physical copies of selected tracks. This folder is excluded from Main Library scanning.',
    'Zmiany są zapisywane w bibliotece ALO i dotyczą kopii wynikowej. Oryginalny plik pozostaje nietknięty.': 'Changes are saved in the ALO library and apply to the output copy. The original file remains untouched.',
    'Wybierz okładkę, która ma trafić do pliku wynikowego. Jeśli nic nie pasuje, wybierz „BRAK OKŁADKI”.': 'Choose the cover for the output file. If none fits, choose “NO COVER”.',
    'Możesz zmienić tę nazwę ręcznie — edytowana wersja zostanie zapisana.': 'You can edit this name manually — the edited version will be saved.',
    'Nie masz jeszcze własnych folderów MP3. W Bibliotece zaznacz utwory i wybierz „Utwórz folder z zaznaczonych”.': 'You do not have any MP3 folders yet. Select tracks in Library and choose “Create folder from selected”.',
})


# v0.4.2 coverage for settings, workflow, editor, player and common dialogs.
TEXT_MAP_EN.update({
    'Organizacja folderu GOTOWE': 'READY folder organization',
    'Opcjonalnie twórz jeden poziom podfolderów. Domyślnie wszystko trafia bezpośrednio do GOTOWE.': 'Optionally create one level of subfolders. By default everything goes directly to READY.',
    'Przy organizacji według gatunku używany jest pierwszy gatunek z listy, np. Trance, Progressive, Vocal → GOTOWE\\Trance.': 'When organizing by genre, the first genre in the list is used, e.g. Trance, Progressive, Vocal → READY\\Trance.',
    'Bez podfolderów': 'No subfolders', 'Według wykonawcy': 'By artist', 'Według gatunku': 'By genre',
    'PODGLĄD DOCELOWEJ ŚCIEŻKI': 'OUTPUT PATH PREVIEW',
    'np. adres e-mail lub nazwa użytkownika': 'e.g. email address or username',
    'Odczytaj tagi, długość, jakość, BPM i fingerprint': 'Read tags, duration, quality, BPM and fingerprint',
    'Uzupełnij dane z AcoustID, MusicBrainz i Discogs': 'Complete data using AcoustID, MusicBrainz and Discogs',
    'Sprawdź metadane, okładki i duplikaty przed utworzeniem plików': 'Review metadata, covers and duplicates before creating files',
    'Utwórz kopie w bibliotece docelowej i wykonaj techniczną kontrolę kopii': 'Create copies in the target library and verify them technically',
    'Dodaj nowy folder lub paczkę plików do aktualnej biblioteki': 'Add a new folder or batch of files to the current library',
    'Zapisz playlistę M3U8': 'Save M3U8 playlist', 'Playlista M3U8 (*.m3u8)': 'M3U8 playlist (*.m3u8)',
    'Utwórz kopię bezpieczeństwa ALO': 'Create ALO backup', 'Wybierz kopię bezpieczeństwa ALO': 'Choose ALO backup',
    'Kopia ALO (*.zip)': 'ALO backup (*.zip)', 'Przywróć bazę ALO': 'Restore ALO database',
    'Wybierz folder z nowymi plikami': 'Choose folder with new files',
    'BŁĄD OPERACJI': 'OPERATION ERROR', 'TWORZENIE PLIKÓW': 'CREATING FILES', 'TWORZENIE PLIKÓW ZAKOŃCZONE': 'FILE CREATION COMPLETE',
    'Skan anulowany': 'Scan cancelled', 'Skan zakończony': 'Scan complete', 'SKANOWANIE ZAKOŃCZONE': 'SCAN COMPLETE',
    'ROZPOZNAWANIE ZAKOŃCZONE': 'IDENTIFICATION COMPLETE',
    'Przejdź do Biblioteki': 'Go to Library', 'Otwórz folder biblioteki': 'Open library folder', 'Utwórz mimo to': 'Create anyway',
    'Brak kluczy API': 'Missing API keys', 'Nieprawidłowy folder': 'Invalid folder', 'Operacja w toku': 'Operation in progress',
    'Brak dostępnych plików': 'No available files', 'Nie można utworzyć folderu': 'Cannot create folder',
    'Folder utworzony': 'Folder created', 'Playlista gotowa': 'Playlist ready', 'Nie można zapisać playlisty': 'Cannot save playlist',
    'Błąd kopii bezpieczeństwa': 'Backup error', 'Kopia utworzona': 'Backup created', 'Nieprawidłowa kopia': 'Invalid backup',
    'Nie można przywrócić kopii': 'Cannot restore backup', 'Kopia przywrócona': 'Backup restored',
    'Brak reguły': 'Missing rule', 'Pole „Znajdź” nie może być puste.': 'The “Find” field cannot be empty.',
    'Edytuj regułę normalizacji': 'Edit normalization rule', 'Zapisz': 'Save', 'Odrzuć': 'Discard', 'Wróć': 'Back',
    'Nieprawidłowy rok': 'Invalid year', 'Rok musi składać się dokładnie z 4 cyfr, np. 2009.': 'Year must contain exactly 4 digits, e.g. 2009.',
    'Brak wymaganych danych': 'Missing required data', 'Wybierz okładkę': 'Choose cover', 'Obrazy (*.jpg *.jpeg *.png *.webp)': 'Images (*.jpg *.jpeg *.png *.webp)',
    'Brak alternatywnych danych': 'No alternative data', 'Duża różnica': 'Large difference',
    'Kliknij, aby porównać dostępne wartości z różnych źródeł.': 'Click to compare available values from different sources.',
    'Cofa ostatnią zmianę w całym edytorze, także przywrócenie danych sprzed online.': 'Undo the last change in the whole editor, including restoring pre-online data.',
    'Opcjonalnie: edytuj nazwę tego pliku. Jeśli ją zmienisz, właśnie ta nazwa zostanie zapisana.': 'Optional: edit this filename. If you change it, that exact name will be saved.',
    'Masz niezapisane zmiany. Zapisać je przed zamknięciem?': 'You have unsaved changes. Save them before closing?',
    'Okładka osadzona w pliku źródłowym.': 'Cover embedded in the source file.',
    'Brak potwierdzonej okładki — grafika zastępcza ALO Music.': 'No confirmed cover — ALO Music placeholder image.',
    'Okładka wybrana ręcznie.': 'Cover selected manually.', 'Okładka pobrana z dopasowanego wydania.': 'Cover downloaded from the matched release.',
    'Nie udało się pobrać okładki zewnętrznej.': 'Could not download the external cover.', 'Brak znalezionej okładki zewnętrznej.': 'No external cover found.',
    'Wybierz utwór w Bibliotece, aby rozpocząć odsłuch': 'Select a track in Library to start listening',
    'Najpierw wybierz utwór w Bibliotece lub Duplikatach.': 'First select a track in Library or Duplicates.',
    'Brak wybranego utworu': 'No track selected', 'Błąd odtwarzania': 'Playback error', '⚠ Błąd odtwarzania': '⚠ Playback error',
    'Brak ręcznych zmian.': 'No manual changes.', 'ZATWIERDŹ JAKO GOTOWE': 'MARK AS READY',
    'Okładka źródłowa / zapasowa.': 'Source / fallback cover.', 'Pobieranie podglądu zewnętrznej okładki…': 'Loading external cover preview…',
    '＋ Dodaj do Moje foldery MP3': '＋ Add to My MP3 folders', '♫ Utwórz playlistę z zaznaczonych': '♫ Create playlist from selected',
    'Zmień gatunek': 'Change genre', 'Zaznacz utwory, które mają trafić do playlisty.': 'Select tracks to include in the playlist.',
    'Najpierw zaznacz utwór w bibliotece.': 'First select a track in the library.',
    'Zaznacz utwory, które mają trafić do nowego folderu MP3.': 'Select tracks to include in the new MP3 folder.',
    'Zaznacz jeden lub wiele utworów w tabeli.': 'Select one or more tracks in the table.',
    'Pierwszy gatunek jest główny i decyduje o folderze.': 'The first genre is primary and decides the folder.',
    'Kliknij prawym przyciskiem, aby ustawić jako główny. Kliknij ×, aby usunąć.': 'Right-click to set as primary. Click × to remove.',
    'Usuń z folderu': 'Remove from folder', 'Wybierz folder zawierający utwory.': 'Choose a folder containing tracks.',
    'Wybierz plik we własnym folderze MP3.': 'Choose a file in your MP3 folder.',
    'Program pokazuje pliki, które mogą być tym samym nagraniem albo inną wersją. Wybierz plik, który chcesz zachować, odłóż niepotrzebny do NIE WYBIERAM albo edytuj jego dane. Program niczego nie usuwa automatycznie.': 'The app shows files that may be the same recording or another version. Choose the file to keep, mark an unwanted one as NOT SELECTED, or edit its data. The app never deletes anything automatically.',
    'Utwórz bezpieczną bibliotekę muzyczną': 'Create a safe music library', '1. Muzyka źródłowa': '1. Source music',
    '2. Gdzie utworzyć nową bibliotekę': '2. Where to create the new library', '＋ Dodaj folder…': '＋ Add folder…',
    'Wybierz lokalizację…': 'Choose location…', 'UTWÓRZ BIBLIOTEKĘ I DALEJ': 'CREATE LIBRARY AND CONTINUE',
    'Wybierz miejsce dla nowej biblioteki': 'Choose a location for the new library', 'Wybierz miejsce dla nowej biblioteki': 'Choose a location for the new library',
    'Wybierz lokalizację i nazwę folderu': 'Choose location and folder name', 'Dodaj przynajmniej jeden folder z muzyką.': 'Add at least one music folder.',
    'Wybierz lokalizację folderu docelowego.': 'Choose the target folder location.', 'Nie można utworzyć biblioteki': 'Cannot create library',
})


TEXT_MAP_EN.update({
    'Stan trwałej biblioteki, nowe pliki, elementy wymagające uwagi i najważniejsze statystyki.': 'Persistent library status, new files, items needing attention and key statistics.',
    'Uruchom skanowanie folderów źródłowych.': 'Scan the source folders.',
    'Przywrócenie zastąpi bazę Biblioteki głównej danymi z kopii. Pliki muzyczne nie zostaną zmienione. Kontynuować?': 'Restoring will replace the Main Library database with the backup data. Music files will not be changed. Continue?',
    'Przywrócono bazę Biblioteki głównej, dostępne bazy profili i ustawienia z kopii. Pliki muzyczne pozostały bez zmian.': 'Restored the Main Library database, available library databases and settings from the backup. Music files remained unchanged.',
    'Najpierw zakończ bieżącą operację.': 'Finish the current operation first.',
    'Nie ma plików do zapisania w playliście.': 'There are no files to save in the playlist.',
    'Żaden z zaznaczonych plików nie jest obecnie dostępny.': 'None of the selected files is currently available.',
    'Najpierw uruchom skanowanie folderów.': 'Scan the folders first.',
    'Najpierw przeskanuj bibliotekę.': 'Scan the library first.',
    'AcoustID i Discogs nie są skonfigurowane. Kontynuować tylko z MusicBrainz?': 'AcoustID and Discogs are not configured. Continue using MusicBrainz only?',
    'AcoustID, MusicBrainz i Discogs — operacja może potrwać z powodu limitów zapytań.': 'AcoustID, MusicBrainz and Discogs — this may take time because of request limits.',
    'Rozpoznawanie online — może potrwać, ponieważ bazy mają limity zapytań…': 'Online identification — this may take time because providers limit requests…',
    'Tworzenie plików i techniczna kontrola kopii…': 'Creating files and performing technical copy verification…',
    'Sprawdź utwory oznaczone jako DO SPRAWDZENIA.': 'Review tracks marked as REVIEW.',
    'Bieżące zapytanie zostanie dokończone; kolejne nie będą wysyłane.': 'The current request will finish; no further requests will be sent.',
    'Zatrzymanie nastąpi bezpiecznie po zakończeniu bieżącego pliku…': 'Stopping will happen safely after the current file finishes…',
    'Analiza tylko wskazanego folderu…': 'Analyzing only the selected folder…',
    'Odczyt tagów, BPM, jakości i fingerprintów…': 'Reading tags, BPM, quality and fingerprints…',
    'Skanowanie': 'Scanning', 'Rozpoznawanie online': 'Online identification',
    'Najpierw sprawdź Bibliotekę': 'Review Library first', 'Tworzenie plików i kontrola techniczna': 'Creating files and technical verification',
    'Błędy kopiowania:': 'Copy errors:', 'Błędy kontroli:': 'Verification errors:',
    'Tworzenie plików wymaga uwagi': 'File creation needs attention',
    'Kopia przed zmianą tagów przeszła kontrolę SHA-256, a plik końcowy istnieje w folderze docelowym.': 'The raw copy passed SHA-256 verification before tag changes, and the final file exists in the target folder.',
    'W tej sesji nie ma już plików oznaczonych DO SPRAWDZENIA.': 'There are no files marked REVIEW left in this run.',
    'Pliki utworzone i sprawdzone': 'Files created and verified',
    'Uruchom rozpoznawanie online lub sprawdź dane w Bibliotece.': 'Run online identification or review data in Library.',
    'Podaj nazwę folderu biblioteki.': 'Enter a library folder name.', 'Nazwa folderu zawiera niedozwolone znaki.': 'The folder name contains invalid characters.',
    'BŁĄD': 'ERROR', 'Niska pewność rozpoznania': 'Low identification confidence',
    'Rozpoznawanie online nie zostało jeszcze uruchomione dla tego pliku.': 'Online identification has not yet been run for this file.',
    'Brak dodatkowych szczegółów dopasowania.': 'No additional match details.', 'Dane lokalne / nierozpoznane online': 'Local data / not identified online',
    'Duplikat / podobne nagranie': 'Duplicate / similar recording', 'Brak:': 'Missing:', 'duża różnica': 'large difference',
    'Okładka odtwarzanego utworu': 'Cover of the playing track',
    '⚠ Duża różnica względem danych sprzed online — sprawdź wykonawcę i tytuł przed zatwierdzeniem.': '⚠ Large difference from pre-online data — check artist and title before approving.',
    'Niska pewność — sprawdź': 'Low confidence — review', 'Brak': 'Missing', '✓ WŁASNA WYBRANA': '✓ CUSTOM SELECTED',
    'TYTUŁ / WERSJA': 'TITLE / VERSION', 'DŁUGOŚĆ': 'DURATION', 'JAKOŚĆ': 'QUALITY', 'PLIK ŹRÓDŁOWY': 'SOURCE FILE',
    'Pełny SHA-256': 'Full SHA-256', 'kanały': 'channels',
    '✓ Dane główne kompletne — nie musisz niczego uzupełniać.': '✓ Main data complete — nothing needs to be filled in.',
    'Nie udało się pobrać okładki zewnętrznej — użyta zostanie źródłowa lub zastępcza.': 'Could not download the external cover — the source or fallback cover will be used.',
    'Ten plik został przez Ciebie wybrany w zakładce Duplikaty.': 'You selected this file in Duplicates.',
    'Oryginalne pliki pozostaną nietknięte. ALO Music analizuje źródła tylko do odczytu, a uporządkowane pliki tworzy w wybranej przez Ciebie bibliotece.': 'Original files remain untouched. ALO Music analyzes sources read-only and creates organized copies in the library you choose.',
    '✓ Źródła nie są modyfikowane ani usuwane': '✓ Sources are never changed or deleted',
    'Dodaj jeden lub kilka folderów, które program ma przeskanować. Pliki w tych folderach są tylko odczytywane.': 'Add one or more folders to scan. Files in these folders are read-only.',
    'Wybierz dysk lub folder nadrzędny, np. D:\\Muzyka.': 'Choose a drive or parent folder, e.g. D:\\Music.',
    'ALO Music utworzy w nim podfoldery GOTOWE, NIE_WYBRANE, DO_SPRAWDZENIA, MOJE_FOLDERY_MP3 i raporty oraz własną bazę .alo.': 'ALO Music will create READY, NOT_SELECTED, REVIEW, MY_MP3_FOLDERS, reports and its own .alo database inside it.',
    'Wybierz lokalizację powyżej': 'Choose a location above',
    'Podgląd przed utworzeniem plików': 'Preview before creating files',
    'Usunąć tylko tę kopię z MOJE_FOLDERY_MP3? Oryginalny plik i główna biblioteka pozostaną bez zmian.': 'Remove only this copy from MY_MP3_FOLDERS? The original file and Main Library will remain unchanged.',
    '★ ZACHOWAJ i × NIE WYBIERAM aktualizują Bibliotekę od razu. Fioletowy stan DUPLIKAT jest wykrywany przez program i pozostaje widoczny w Bibliotece.': '★ KEEP and × NOT SELECTED update Library immediately. The purple DUPLICATE state is detected by the app and remains visible in Library.',
    '▶ Odtwórz': '▶ Play', '✎ Edytuj metadane': '✎ Edit metadata', 'Pokaż w Eksploratorze': 'Show in Explorer',
    'Niezapisane zmiany': 'Unsaved changes',
    'Nie można oznaczyć jako GOTOWE — uzupełnij wymagane pola: ': 'Cannot mark READY — fill in the required fields: ',
})


def _dynamic_en(text: str) -> str:
    # Runtime labels are assembled from stable UI phrases and user data. Keep
    # the data intact while translating only the surrounding interface copy.
    if text.startswith('Sortowanie: '):
        result = text.replace('Sortowanie:', 'Sort:', 1).replace('Filtry:', 'Filters:', 1)
        result = result.replace('Filters: brak', 'Filters: none')
        return result.replace('Szukaj:', 'Search:').replace('Gatunek:', 'Genre:')
    if text.startswith('Brak: '):
        return 'Missing: ' + translate_static_text(text[6:], 'en')
    if text.startswith('Zapisano metadane i ustawiono ZACHOWAJ: '):
        return 'Metadata saved and marked KEEP: ' + text.split(': ', 1)[1]
    if text.startswith('Cofnięto: '):
        return 'Undone: ' + translate_static_text(text[len('Cofnięto: '):], 'en')
    if text.startswith('Decyzja w Duplikatach: '):
        return 'Decision in Duplicates: ' + translate_static_text(text[len('Decyzja w Duplikatach: '):], 'en')
    if text.startswith('Błąd rozpoznawania online — '):
        return 'Online identification error — ' + translate_static_text(text[len('Błąd rozpoznawania online — '):], 'en')
    if text.startswith('Zmieniono ') and ' dla ' in text:
        match = re.fullmatch(r'Zmieniono (.+) dla (\d+) utworów\. Ręczna wartość jest chroniona przed automatycznym nadpisaniem\.', text)
        if match:
            return f'Updated {translate_static_text(match.group(1), "en")} for {match.group(2)} tracks. The manual value is protected from automatic changes.'
    for source, target in (
        ('Źródło: ', 'Source: '),
        ('Następny: ', 'Next: '),
        ('Zastosuj dostępne dane ze źródła: ', 'Apply available data from source: '),
        ('Okładka online — ', 'Online cover art — '),
        ('Błąd odtwarzania: ', 'Playback error: '),
        ('Metadane zapisane • Status: ', 'Metadata saved • Status: '),
    ):
        if text.startswith(source):
            return target + translate_static_text(text[len(source):], 'en')
    for source, target in (
        ('Brak ważnych danych: ', 'Missing essential data: '),
        ('Pola wymagające uwagi: ', 'Fields needing attention: '),
    ):
        if text.startswith(source):
            return target + ', '.join(translate_static_text(field, 'en') for field in text[len(source):].split(', '))
    if re.match(r'^\d+% — ', text):
        for source, target in (('bardzo pewne', 'very confident'), ('sprawdź wersję', 'check version'), ('wymaga sprawdzenia', 'needs review')):
            text = text.replace(source, target)
        return text
    status_suffix = re.fullmatch(r'(.+): (GOTOWE|DO SPRAWDZENIA)', text)
    if status_suffix:
        return f'{status_suffix.group(1)}: {TEXT_MAP_EN[status_suffix.group(2)]}'
    decision_message = re.fullmatch(r'(.+): wybrano (ZACHOWAJ|DUPLIKAT|NIE WYBIERAM|DO SPRAWDZENIA) → Biblioteka: (.+)\.', text)
    if decision_message:
        filename, decision, status = decision_message.groups()
        return f'{filename}: selected {translate_static_text(decision, "en")} → Library: {translate_static_text(status, "en")}.'
    for pattern, replacement in (
        (r'^(\d+) plików • (\d+) grup$', r'\1 files • \2 groups'),
        (r'^Biblioteka wymaga uwagi: (\d+) do sprawdzenia, (\d+) duplikatów\.$', r'Library needs attention: \1 need review, \2 duplicates.'),
        (r'^(\d+) utworów jest gotowych\. Możesz filtrować Bibliotekę albo tworzyć własne foldery MP3\.$', r'\1 tracks are ready. You can filter Library or create your own MP3 folders.'),
        (r'^Biblioteka wymaga odświeżenia — (\d+) plików nie jest już dostępnych\.$', r'Library needs a refresh — \1 files are no longer available.'),
        (r'^(Skan zakończony|Skan anulowany): (\d+) przeanalizowano, (\d+) bez zmian, błędy: (\d+)\.$', r'\1: \2 analyzed, \3 unchanged, errors: \4.'),
        (r'^Pewne (\d+), prawdopodobne (\d+), niepewne (\d+), błędy (\d+)\.( Pominięto zablokowane: (\d+)\.)?$', r'Certain \1, probable \2, uncertain \3, errors \4. Locked skipped: \6.'),
        (r'^Skanowanie (\d+)/(\d+): (.+)$', r'Scanning \1/\2: \3'),
        (r'^Rozpoznawanie online (\d+)/(\d+): (.+)$', r'Identifying online \1/\2: \3'),
        (r'^Tworzenie plików i kontrola techniczna (\d+)/(\d+): (.+)$', r'Creating and verifying files \1/\2: \3'),
        (r'^Utworzono playlistę: (.+)$', r'Playlist created: \1'),
        (r'^Zapisano (\d+) utworów:\n(.+)$', r'Saved \1 tracks:\n\2'),
        (r'^Zapisano kopię ALO bez plików muzycznych:\n(.+)$', r'ALO backup saved without music files:\n\1'),
        (r'^Skopiowano (\d+) plików do MOJE_FOLDERY_MP3\.$', r'Copied \1 files to MOJE_FOLDERY_MP3.'),
        (r'^Utworzono folder z (\d+) plikami w MOJE_FOLDERY_MP3\.$', r'Created a folder with \1 files in MOJE_FOLDERY_MP3.'),
        (r'^Kopiowanie (\d+) zaznaczonych utworów…$', r'Copying \1 selected tracks…'),
        (r'^Ręcznie zatwierdzono jako GOTOWE: (.+)$', r'Manually marked as READY: \1'),
        (r'^Rozpoznawanie (.+): błąd providerów — sprawdź komunikat w danych utworu\.$', r'Identification of \1: provider error — see track details.'),
        (r'^(.+): wysokie dopasowanie\.$', r'\1: high-confidence match.'),
        (r'^(.+): dopasowanie wymaga kontroli\.$', r'\1: match needs review.'),
        (r'^(.+): brak pewnego dopasowania\.$', r'\1: no confident match.'),
        (r'^Biblioteka „(.+)” została wyzerowana\. Możesz dodać nowe pliki do skanowania\.$', r'Library “\1” has been reset. You can add new files to scan.'),
        (r'^Nazwa nowego folderu \((\d+) utworów\):$', r'New folder name (\1 tracks):'),
        (r'^Propozycje \((\d+)\)$', r'Suggestions (\1)'),
        (r'^(\d+) do sprawdzenia$', r'\1 need review'),
        (r'^(.+): błąd providerów — sprawdź komunikat w danych utworu\.$', r'\1: provider error — see track details.'),
        (r'^(\d+) grup duplikatów$', r'\1 duplicate groups'),
        (r'^(\d+) bez okładki$', r'\1 without cover art'),
        (r'^(\d+) brakujących plików$', r'\1 missing files'),
        (r'^(\d+) kanały$', r'\1 channels'),
        (r'^(\d+) pliki • decyzje (\d+)/(\d+)$', r'\1 files • decisions \2/\3'),
        (r'^Nowy gatunek dla (\d+) utworów:$', r'New genre for \1 tracks:'),
        (r'^Utworzono i sprawdzono technicznie (\d+) plików\. Raport kontroli zapisano w folderze raportów\.$', r'Created and verified \1 files. The verification report was saved in the reports folder.'),
    ):
        if re.fullmatch(pattern, text, flags=re.DOTALL):
            result = re.sub(pattern, replacement, text, flags=re.DOTALL)
            if pattern.startswith('^(Skan zakończony|Skan anulowany)'):
                result = result.replace('Skan zakończony', 'Scan complete').replace('Skan anulowany', 'Scan cancelled')
            if pattern.startswith('^Pewne') and not re.search(r'Pominięto zablokowane:', text):
                result = result.replace(' Locked skipped: .', '')
            return result
    if text.startswith('Podgląd: '):
        return 'Preview: ' + text[len('Podgląd: '):]
    if text.startswith('Przykład: '):
        return 'Example: ' + text[len('Przykład: '):]
    if text.startswith('Aktywna biblioteka: '):
        return 'Active library: ' + text[len('Aktywna biblioteka: '):]
    if text.endswith(' • AKTYWNA'):
        return text[:-len('AKTYWNA')] + 'ACTIVE'
    if text.startswith('Lokalizacja bazowa: '):
        return 'Base location: ' + text[len('Lokalizacja bazowa: '):]
    if text.startswith('Pełna ścieżka: '):
        return 'Full path: ' + text[len('Pełna ścieżka: '):]
    if text.startswith('Wolne miejsce: '):
        return 'Free space: ' + text[len('Wolne miejsce: '):]
    if text.startswith('Skanowane źródła ('):
        return re.sub(r'^Skanowane źródła \((\d+)\)$', r'Scanned sources (\1)', text)
    if text.startswith('Ostatni skan: '):
        return text.replace('Ostatni skan:', 'Last scan:', 1).replace('Pliki:', 'Files:')
    if text.startswith('Rodzina wersji: '):
        return re.sub(r'^Rodzina wersji: (\d+) utwory$', r'Version family: \1 tracks', text)
    if 'Otwórz w Eksploratorze' in text:
        return text.replace('Otwórz w Eksploratorze', 'Open in Explorer')
    # Compact count/status summaries.
    result = text
    replacements = (
        (r'^Zapisano (\d+) utworów:', r'Saved \1 tracks:'),
        (r'^Utworzono folder z (\d+) plikami', r'Created a folder with \1 files'),
        (r'^Nazwa nowego folderu \((\d+) utworów\):', r'New folder name (\1 tracks):'),
        (r'^Nowy gatunek dla (\d+) utworów:', r'New genre for \1 tracks:'),
        (r'\b(\d+) dostępnych plików\b', r'\1 available files'),
        (r'\b(\d+) plików\b', r'\1 files'),
        (r'\b(\d+) pliki\b', r'\1 files'),
        (r'\b(\d+) grup\b', r'\1 groups'),
        (r'\bdecyzje\b', r'decisions'),
        (r'\b(\d+) utworów\b', r'\1 tracks'),
        (r'\b(\d+) gotowe\b', r'\1 ready'),
        (r'\b(\d+) do sprawdzenia\b', r'\1 to review'),
        (r'\b(\d+) nie wybieram\b', r'\1 not selected'),
        (r'\b(\d+)% uporządkowana\b', r'\1% organized'),
    )
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result)
    return result


def _english_count_agreement(text: str) -> str:
    text = re.sub(r'\b1 (available files|missing files|duplicate groups|files|tracks|groups|channels)\b',
                  lambda match: '1 ' + match.group(1).replace('files', 'file').replace('tracks', 'track').replace('groups', 'group').replace('channels', 'channel'), text)
    return re.sub(r'\b1 need review\b', '1 needs review', text)


def translate_static_text(text: str, language: str) -> str:
    if language != 'en':
        return text
    if text in TEXT_MAP_EN:
        return TEXT_MAP_EN[text]
    dynamic = _dynamic_en(text)
    if dynamic != text:
        return _english_count_agreement(dynamic)
    if ' · ' in text:
        parts = [translate_static_text(part, language) for part in text.split(' · ')]
        if parts != text.split(' · '):
            return ' · '.join(parts)
    if '\n' in text:
        return '\n'.join(TEXT_MAP_EN.get(line, _dynamic_en(line)) for line in text.split('\n'))
    return _english_count_agreement(_dynamic_en(text))


def _remembered_text(obj, prop: str, current: str, language: str) -> str:
    original = obj.property(prop)
    if original is None:
        original = current
        obj.setProperty(prop, original)
        return str(original)
    original = str(original)
    translated = translate_static_text(original, 'en')
    # If a widget changed dynamically after the previous translation, treat the
    # new value as the new Polish source string rather than restoring stale text.
    if current not in {original, translated} and current:
        original = current
        obj.setProperty(prop, original)
    return original


def language_for(root) -> str:
    """Return the active UI language stored on a widget or one of its parents."""
    current = root
    while current is not None:
        try:
            language = current.property('_alo_language')
            if language in {'pl', 'en'}:
                return str(language)
            current = current.parent()
        except Exception:
            break
    return 'pl'


def ui_text(root, text: str) -> str:
    """Translate a runtime dialog/status string using the owning UI language."""
    return translate_static_text(text, language_for(root))


def localized_no_cover_name(root) -> str:
    """Select artwork copy for the UI; exported audio still uses its original art."""
    return 'no_cover_en.png' if language_for(root) == 'en' else 'no_cover.png'


def apply_static_language(root, language: str) -> None:
    """Apply PL/EN to visible static UI, including secondary widget metadata.

    The UI is authored in Polish. Original texts are remembered per widget so
    language switching is reversible and dynamic text can be refreshed safely.
    """
    language = language if language in {'pl', 'en'} else 'pl'
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import (
            QLabel, QAbstractButton, QGroupBox, QComboBox, QLineEdit, QTextEdit,
            QTableWidget, QTableView, QTabWidget, QListWidget, QWidget,
        )
    except ImportError:
        return

    root.setProperty('_alo_language', language)
    objects = [root, *root.findChildren(object)]
    for widget in objects:
        if isinstance(widget, QWidget):
            try:
                if widget.windowTitle():
                    original = _remembered_text(widget, '_alo_pl_window_title', widget.windowTitle(), language)
                    widget.setWindowTitle(translate_static_text(original, language))
            except Exception:
                pass
            try:
                if widget.toolTip():
                    original = _remembered_text(widget, '_alo_pl_tooltip', widget.toolTip(), language)
                    widget.setToolTip(translate_static_text(original, language))
            except Exception:
                pass

        if isinstance(widget, (QLabel, QAbstractButton, QGroupBox)):
            try:
                current = widget.text()
                original = _remembered_text(widget, '_alo_pl_text', current, language)
                widget.setText(translate_static_text(original, language))
            except Exception:
                pass
        elif isinstance(widget, QAction):
            try:
                current = widget.text()
                original = _remembered_text(widget, '_alo_pl_text', current, language)
                widget.setText(translate_static_text(original, language))
            except Exception:
                pass

        if isinstance(widget, (QLineEdit, QTextEdit)):
            try:
                current = widget.placeholderText()
                if current:
                    original = _remembered_text(widget, '_alo_pl_placeholder', current, language)
                    widget.setPlaceholderText(translate_static_text(original, language))
            except Exception:
                pass

        if isinstance(widget, QComboBox):
            try:
                for index in range(widget.count()):
                    data_key = f'_alo_pl_item_{index}'
                    original = widget.property(data_key)
                    current = widget.itemText(index)
                    if original is None or current not in {str(original), translate_static_text(str(original), 'en')}:
                        original = current
                        widget.setProperty(data_key, original)
                    widget.setItemText(index, translate_static_text(str(original), language))
            except Exception:
                pass

        if isinstance(widget, QListWidget):
            try:
                for index in range(widget.count()):
                    item = widget.item(index)
                    if item is None:
                        continue
                    key = Qt.ItemDataRole.UserRole + 120
                    original = item.data(key)
                    current = item.text()
                    if original is None or current not in {str(original), translate_static_text(str(original), 'en')}:
                        original = current
                        item.setData(key, original)
                    item.setText(translate_static_text(str(original), language))
            except Exception:
                pass

        if isinstance(widget, QTableWidget):
            try:
                key = '_alo_pl_headers'
                originals = widget.property(key)
                current_headers = [widget.horizontalHeaderItem(i).text() if widget.horizontalHeaderItem(i) else '' for i in range(widget.columnCount())]
                if originals is None:
                    originals = current_headers
                    widget.setProperty(key, originals)
                for i, original in enumerate(list(originals)):
                    item = widget.horizontalHeaderItem(i)
                    if item is not None:
                        item.setText(translate_static_text(str(original), language))
            except Exception:
                pass

        if isinstance(widget, QTableView) and not isinstance(widget, QTableWidget):
            try:
                model = widget.model()
                if model is not None:
                    key = '_alo_pl_model_headers'
                    originals = widget.property(key)
                    if originals is None:
                        originals = [str(model.headerData(i, Qt.Orientation.Horizontal) or '') for i in range(model.columnCount())]
                        widget.setProperty(key, originals)
                    for i, original in enumerate(list(originals)):
                        model.setHeaderData(i, Qt.Orientation.Horizontal, translate_static_text(str(original), language))
            except Exception:
                pass

        if isinstance(widget, QTabWidget):
            try:
                key = '_alo_pl_tabs'
                originals = widget.property(key)
                if originals is None:
                    originals = [widget.tabText(i) for i in range(widget.count())]
                    widget.setProperty(key, originals)
                for i, original in enumerate(list(originals)):
                    widget.setTabText(i, translate_static_text(str(original), language))
            except Exception:
                pass


# v0.4.5 destination libraries, duplicate comparison and version-family UI.
TEXT_MAP_EN.update({
    'Folder biblioteki / zapisu': 'Library / output folder',
    'Wybierz folder zapisu': 'Choose output folder',
    'Wybierz folder biblioteki / zapisu': 'Choose library / output folder',
    'Otwórz w Eksploratorze': 'Open in Explorer',
    'Skanowane źródła': 'Scanned sources',
    'Brak zapisanej historii skanowania.': 'No scan history saved.',
    'Historia folderów otwieranych i skanowanych w tej bibliotece. To informacja — sama historia nie uruchamia ponownego skanowania.': 'History of folders opened and scanned in this library. This is informational — the history itself never starts another scan.',
    'Biblioteka to folder docelowy ALO — tutaj znajdują się lub będą zapisywane utwory wynikowe. Foldery źródłowe są dodawane osobno podczas skanowania.': 'A library is the ALO output folder — processed tracks are stored or will be stored here. Source folders are added separately when scanning.',
    'Wybierz folder, w którym ALO będzie zapisywać gotowe i przetworzone utwory. Foldery źródłowe dodasz osobno podczas skanowania.\n\nPliki muzyczne nie zostaną skopiowane ani usunięte. ALO nie przenosi ani nie usuwa plików źródłowych.': 'Choose the folder where ALO will save ready and processed tracks. Add source folders separately when scanning.\n\nMusic files will not be copied or deleted. ALO never moves or deletes source files.',
    'Kliknij bibliotekę, aby ją aktywować. Zielony kolor zawsze oznacza bibliotekę aktualnie używaną przez ALO.': 'Click a library to activate it. Green always marks the library currently used by ALO.',
    'Wariant': 'Variant',
    'Nazwa pliku': 'Filename',
    'Długość': 'Duration',
    'Format': 'Format',
    'Bitrate': 'Bitrate',
    'Hz': 'Hz',
    'Rozmiar': 'Size',
    'Status': 'Status',
    'Decyzja': 'Decision',
    'Rodzina wersji': 'Version family',
    'Porównaj dane techniczne i sam wybierz plik, który chcesz zachować. Różna długość może oznaczać Radio Edit, Extended Mix albo inną wersję — ALO niczego nie wybiera i niczego nie usuwa automatycznie.': 'Compare the technical data and choose the file yourself. A different duration may mean a Radio Edit, Extended Mix or another version — ALO never chooses a winner and never deletes anything automatically.',
    'Dwuklik w wiersz uruchamia odsłuch. ZACHOWAJ = zielony wiersz, NIE WYBIERAM = szary. Status DUPLIKAT jest osobnym oznaczeniem technicznym.': 'Double-click a row to play it. KEEP = green row, NOT SELECTED = gray. DUPLICATE is shown separately as a technical status.',
    '★ ZACHOWAJ': '★ KEEP',
    '× NIE WYBIERAM': '× NOT SELECTED',
    '✎ EDYTUJ': '✎ EDIT',
    'DUPLIKAT': 'DUPLICATE',
})

# v0.4.6 simplified Start/settings/library management.
TEXT_MAP_EN.update({
    'Biblioteka ALO Music': 'ALO Music library',
    'Biblioteka główna — folder docelowy': 'Main Library — output folder',
    'Tutaj widzisz wyłącznie folder, w którym ALO zapisuje pliki wynikowe. Skanowane źródła są dostępne jako historia w oknie Biblioteki.': 'This shows only the folder where ALO saves output files. Scanned sources are available as history in the Libraries window.',
    'Biblioteka docelowa jest zapamiętywana między uruchomieniami. Historia skanów jest dostępna w oknie Biblioteki. Oryginalne pliki nie są modyfikowane.': 'The output library is remembered between launches. Scan history is available in the Libraries window. Original files are not modified.',
    'Zarządzaj bibliotekami ALO': 'Manage ALO libraries',
    'Zarządzaj bibliotekami': 'Manage libraries',
    'Wyczyść historię skanów': 'Clear scan history',
})

# v0.4.24: English copy for labels generated outside the initial widget tree.
TEXT_MAP_EN.update({
    'DO SPRAWDZENIA': 'NEEDS REVIEW', 'NIE WYBIERAM': 'NOT SELECTED',
    # These are real directory names. Translate the surrounding UI, not paths.
    'Pliki wynikowe / GOTOWE': 'Output files / GOTOWE',
    'Otwórz MOJE_FOLDERY_MP3': 'Open MOJE_FOLDERY_MP3',
    'Organizacja folderu GOTOWE': 'GOTOWE folder organization',
    'Opcjonalnie twórz jeden poziom podfolderów. Domyślnie wszystko trafia bezpośrednio do GOTOWE.': 'Optionally create one level of subfolders. By default, files go directly into GOTOWE.',
    'Przy organizacji według gatunku używany jest pierwszy gatunek z listy, np. Trance, Progressive, Vocal → GOTOWE\\Trance.': 'When organizing by genre, the first genre in the list is used, e.g. Trance, Progressive, Vocal → GOTOWE\\Trance.',
    'ALO Music utworzy w nim podfoldery GOTOWE, NIE_WYBRANE, DO_SPRAWDZENIA, MOJE_FOLDERY_MP3 i raporty oraz własną bazę .alo.': 'ALO Music will create the actual folders GOTOWE, NIE_WYBRANE, DO_SPRAWDZENIA, MOJE_FOLDERY_MP3 and raporty, plus its own .alo database.',
    'Usunąć tylko tę kopię z MOJE_FOLDERY_MP3? Oryginalny plik i główna biblioteka pozostaną bez zmian.': 'Remove only this copy from MOJE_FOLDERY_MP3? The original file and Main Library will remain unchanged.',
    '🟠 Do sprawdzenia': '🟠 Needs review', '⚪ Nie wybieram': '⚪ Not selected',
    'Wymaga sprawdzenia': 'Needs review', 'Oznacz jako GOTOWE': 'Mark as ready',
    'Odznacz jako GOTOWE': 'Unmark as ready', 'ZACHOWAJ': 'KEEP',
    'Utwórz playlistę (.m3u8)': 'Create playlist (.m3u8)',
    'Cofnij ostatnią zmianę': 'Undo last change', 'Odtwórz': 'Play',
    'Ukryj szczegóły': 'Hide details', 'Utwórz playlistę z zaznaczonych': 'Create playlist from selected',
    'Dane główne kompletne — nie musisz niczego uzupełniać.': 'Main metadata complete — nothing to add.',
    'ŚREDNIA': 'MEDIUM', 'WYSOKA': 'HIGH', 'NISKA': 'LOW',
    'Dodaj regułę': 'Add rule', 'Brakujące pliki': 'Missing files',
    'OKŁADKI': 'COVER ART', 'BRAKUJĄCE PLIKI': 'MISSING FILES',
    'Kliknij, aby otworzyć ten widok w Bibliotece': 'Click to open this view in Library',
    'Oryginalne pliki NIE zostaną zmienione ani usunięte.': 'Original files will NOT be changed or deleted.',
    'Pierwszy gatunek jest główny i decyduje o folderze. Kliknij, aby usunąć.': 'The first genre is primary and determines the folder. Click to remove.',
    'Kliknij prawym przyciskiem, aby ustawić jako główny. Kliknij, aby usunąć.': 'Right-click to make primary. Click to remove.',
    'Utwór należy do grupy wymagającej porównania.': 'Track belongs to a group that needs comparison.',
    'Dane wymagają ręcznej kontroli.': 'Metadata needs manual review.',
    'Poważny problem lub podejrzane dane wymagające szczególnej uwagi.': 'A serious issue or suspicious data needs special attention.',
    'Utwór pominięty decyzją użytkownika.': 'Track skipped by your choice.',
    'Legenda statusów': 'Status legend', 'Pokaż znaczenie kolorów statusów': 'Show what the status colors mean',
    'GOTOWE — Utwór gotowy do użycia / eksportu.': 'READY — Track ready to use or export.',
    'DUPLIKAT — Utwór należy do grupy wymagającej porównania.': 'DUPLICATE — Track belongs to a group that needs comparison.',
    'DO SPRAWDZENIA — Dane wymagają ręcznej kontroli.': 'NEEDS REVIEW — Metadata needs manual review.',
    'DO SPRAWDZENIA — ważne — Poważny problem lub podejrzane dane wymagające szczególnej uwagi.': 'NEEDS REVIEW — important — A serious issue or suspicious data needs special attention.',
    'NIE WYBIERAM — Utwór pominięty decyzją użytkownika.': 'NOT SELECTED — Track skipped by your choice.',
    'Źródła nie są modyfikowane ani usuwane': 'Sources are not changed or deleted',
    'Dwuklik w wiersz uruchamia odsłuch. Przy przełączaniu wariantów A/B odsłuch zachowuje ten sam moment utworu. ZACHOWAJ = zielona komórka decyzji, NIE WYBIERAM = szara. Brak decyzji pozostawia zwykłe ciemne tło.': 'Double-click a row to play it. Switching between A/B variants keeps the same playback position. KEEP has a green decision cell, NOT SELECTED a gray one. Undecided files keep the normal dark background.',
    'Sprawdź przed zamknięciem': 'Review before closing', 'Przed zamknięciem sprawdź ten utwór': 'Review this track before closing',
    'ALO wykryło elementy, które mogą wymagać Twojej decyzji:': 'ALO found items that may need your decision:',
    'Wróć do edycji': 'Return to editing', 'Odrzuć zmiany': 'Discard changes',
    'Zamknij mimo ostrzeżeń': 'Close despite warnings', 'Przejdź do poprzedniego pliku': 'Go to previous file',
    'Następny plik': 'Next file', 'Przejdź do następnego pliku': 'Go to next file',
    'Przywróć dane sprzed online': 'Restore data from before online identification',
    'Duża różnica względem danych sprzed online — sprawdź wykonawcę i tytuł przed zatwierdzeniem.': 'Large difference from the previous data — check artist and title before approval.',
    'Otwórz adres w domyślnej przeglądarce': 'Open link in your default browser',
    'Pewność': 'Confidence', 'Okładka (wybierana z listy)': 'Cover art (choose from list)',
    'Wybierz własny plik okładki': 'Choose your own cover image',
    'Szukaj okładki online': 'Search for cover art online',
    'Odśwież propozycje okładek przez ponowne rozpoznanie online': 'Refresh cover suggestions by identifying online again',
    'Pokaż więcej': 'Show more', 'Przywróć nazwę z metadanych': 'Restore filename from metadata',
    'Porównanie źródeł  (pomocniczo)': 'Source comparison  (reference)',
    'Legenda źródeł — kliknij': 'Source legend — click', 'Legenda źródeł': 'Source legend',
    'identyfikacja nagrania i wydań': 'recording and release identification',
    'wartość wpisana ręcznie': 'manually entered value',
    'wartość wykryta z audio': 'value detected from audio',
    'wartość odczytana z nazwy pliku': 'value read from the filename',
    'Źródło': 'Source', 'Główne źródło': 'Primary source', 'Użyj danych': 'Use data',
    'Podgląd wybranej okładki': 'Preview selected cover art',
    'Kliknij, aby zmienić na DO SPRAWDZENIA': 'Click to change to NEEDS REVIEW',
    'Kliknij, aby oznaczyć jako GOTOWE': 'Click to mark as READY',
    'Nie udało się pobrać okładki': 'Could not download cover art',
    'Odtwórz / pauza': 'Play / pause', 'Przewiń 10 sekund': 'Skip 10 seconds',
    'Powtarzaj aktualny utwór': 'Repeat current track',
    'Ten utwór jest zablokowany przed rozpoznawaniem online. Odblokuj go, aby wykonać skan.': 'This track is locked against online identification. Unlock it to identify it.',
    'Brak ręcznych zmian do cofnięcia w tej sesji.': 'No manual changes to undo in this session.',
    'UTWÓR ROZPOZNANY ONLINE': 'TRACK IDENTIFIED ONLINE',
    'UTWÓR SPRAWDZONY ONLINE': 'TRACK CHECKED ONLINE',
    'Każde źródło działa niezależnie. Klucze są przechowywane lokalnie i pozostają maskowane w interfejsie.': 'Each source works independently. Keys are stored locally and masked in the interface.',
    'Rozpoznawanie utworów na podstawie fingerprintu audio.': 'Identify tracks using audio fingerprints.',
    'Utwór, wykonawca, album i identyfikatory nagrania.': 'Track, artist, album and recording IDs.',
    'Katalog, album, rok, gatunek i propozycje okładek.': 'Catalog, album, year, genre and cover art suggestions.',
    'MusicBrainz i Apple/iTunes działają bez klucza. AcoustID i Discogs są używane, jeśli je skonfigurowano.': 'MusicBrainz and Apple/iTunes work without keys. AcoustID and Discogs are used when configured.',
    'Wybierz folder biblioteki / zapisu': 'Choose library / output folder',
    'Gotowe': 'Ready', 'Do sprawdzenia': 'Needs review', 'Nie wybieram': 'Not selected',
    'Wszystkie utwory': 'All tracks', 'Wszystkie': 'All',
    'decyzje': 'decisions', 'pliki': 'files', 'kanały': 'channels', 'Teraz: ': 'Now: ',
    'Resetuj widok': 'Reset view', 'DANE TECHNICZNE': 'TECHNICAL DETAILS',
    'UKRYJ DANE TECHNICZNE': 'HIDE TECHNICAL DETAILS',
    'HISTORIA ZMIAN W SESJI': 'CHANGES IN THIS SESSION',
    'ROZMIAR PLIKU': 'FILE SIZE', 'Wpisz lub wybierz gatunek…': 'Type or choose a genre…',
    'Szukaj w pomocy…': 'Search Help…',
    'BIBLIOTEKA ZOSTANIE UTWORZONA TUTAJ': 'THE LIBRARY WILL BE CREATED HERE',
    'NAZWA FOLDERU BIBLIOTEKI': 'LIBRARY FOLDER NAME',
    'Dodaj folder…': 'Add folder…',
    'GOTOWE   •   NIE WYBRANE   •   DO SPRAWDZENIA   •   MOJE FOLDERY MP3   •   raporty': 'GOTOWE   •   NIE_WYBRANE   •   DO_SPRAWDZENIA   •   MOJE_FOLDERY_MP3   •   raporty',
    'ALO Music — konfiguracja biblioteki': 'ALO Music — library setup',
    'Utwórz bezpieczną bibliotekę muzyczną': 'Create a safe music library',
    'Wybierz lokalizację i nazwę folderu': 'Choose a location and folder name',
    'Dodaj przynajmniej jeden folder z muzyką.': 'Add at least one music folder.',
    'Wybierz lokalizację folderu docelowego.': 'Choose the output folder location.',
    'Podaj nazwę folderu biblioteki.': 'Enter a library folder name.',
    'Nazwa folderu zawiera niedozwolone znaki.': 'The folder name contains invalid characters.',
    'Nie można utworzyć biblioteki': 'Cannot create library',
    'Nowa biblioteka': 'New library', 'np. House 2000': 'e.g. House 2000',
    'Utwór gotowy do użycia / eksportu.': 'Track ready to use or export.',
    'Wybierz…': 'Choose…', 'Okładka': 'Cover art', 'Propozycje (0)': 'Suggestions (0)',
    'Rozpoznaj online': 'Identify online', 'Rozpoznawanie…': 'Identifying…',
    'Poprzedni plik': 'Previous file', 'Plik ': 'File ',
    'Metadane utworu': 'Track metadata', 'Status pliku': 'File status',
    'Informacje o rozpoznaniu': 'Identification details',
    'Rozpoznane pola': 'Identified fields', 'Dodaj komentarz…': 'Add a comment…',
    'Analiza audio': 'Audio analysis', 'ANALIZA AUDIO': 'AUDIO ANALYSIS',
    'Blokada rozpoznawania online': 'Online identification lock',
    'Dane chronione przed ponownym rozpoznaniem online': 'Data protected from online identification',
    'Rozpoznawanie online odblokowane': 'Online identification unlocked',
    'Status: DO SPRAWDZENIA': 'Status: NEEDS REVIEW',
    'Uruchom rozpoznawanie online tylko dla tego utworu.': 'Identify this track online only.',
    'Zapisz i zamknij': 'Save and close', 'ŹRÓDŁO': 'SOURCE',
    'Rozmiar obrazu: ': 'Image size: ', 'Cofnij 10 sekund': 'Back 10 seconds',
    'Nieznany wykonawca': 'Unknown artist', 'Odtwarzacz jest gotowy': 'Player ready',
    'Status DO SPRAWDZENIA': 'Status NEEDS REVIEW',
    'Podejrzane BPM': 'Suspicious BPM', 'Sprzeczne dane online': 'Conflicting online data',
    'Nieprawidłowa długość audio': 'Invalid audio duration',
    'Plik niedostępny': 'File unavailable', 'Pusty plik': 'Empty file',
    'Błąd odtwarzania: ': 'Playback error: ',
    'ROZPOZNAWANIE WYMAGA UWAGI': 'IDENTIFICATION NEEDS ATTENTION',
    'ROZPOZNAWANIE JEDNEGO UTWORU': 'IDENTIFYING ONE TRACK',
    'ROZPOZNAWANIE ANULOWANE': 'IDENTIFICATION CANCELLED',
    'ANULOWANIE ROZPOZNAWANIA': 'CANCELLING IDENTIFICATION',
    'ANULOWANIE SKANOWANIA': 'CANCELLING SCAN',
    'FOLDER MP3 GOTOWY': 'MP3 FOLDER READY',
    'NOWE PLIKI': 'NEW FILES', 'SKANOWANIE ANULOWANE': 'SCAN CANCELLED',
    'Anulowanie rozpoznawania…': 'Cancelling identification…',
    'Anulowanie skanowania…': 'Cancelling scan…',
    'Rozpoznawanie online tylko: ': 'Online identification only: ',
    'Rozpoznawanie zablokowane': 'Identification locked',
    'Najpierw zapisz albo anuluj zmiany w tym utworze, a potem uruchom rozpoznawanie online.': 'Save or discard this track’s changes before identifying it online.',
    'Kopiowanie, zapis metadanych i techniczna kontrola kopii…': 'Copying files, writing metadata and verifying copies…',
    'Tworzenie plików i techniczna kontrola kopii…': 'Creating and verifying files…',
    'Odczyt tagów, BPM, jakości i fingerprintów…': 'Reading tags, BPM, quality and fingerprints…',
    'Rozpoznawanie online — może potrwać, ponieważ bazy mają limity zapytań…': 'Identifying online — this may take time due to provider rate limits…',
    'Dodaj do Moje foldery MP3': 'Add to My MP3 folders',
    'MOJE FOLDERY MP3': 'MY MP3 FOLDERS',
    'Utwórz pliki wynikowe': 'Create output files',
    'ROZPOZNANE ONLINE': 'IDENTIFIED ONLINE', 'PODEJRZANE DANE': 'SUSPICIOUS DATA',
    'ROZMIAR BIBLIOTEKI': 'LIBRARY SIZE', 'WOLNE MIEJSCE': 'FREE SPACE',
    'Wymaga uwagi': 'Needs attention', 'Statystyki biblioteki': 'Library statistics',
    'Ostatnie skanowanie: brak danych': 'Last scan: no data',
    'Ostatnie skanowanie:': 'Last scan:', 'Ładowanie biblioteki…': 'Loading library…',
    'Skanowanie: odczyt tagów, BPM, jakości i fingerprintów…': 'Scanning: reading tags, BPM, quality and fingerprints…',
    'DO SPRAWDZENIA — ważne': 'NEEDS REVIEW — important',
    'Moje pliki MP3': 'My MP3 files',
    'Długość zgodna': 'Matching duration', 'długość zgodna': 'matching duration',
    'Rozpoznawanie online nadal trwa. Poczekaj na zakończenie operacji.': 'Online identification is still running. Wait for it to finish.',
    'ROZPOZNAWANIE ONLINE': 'ONLINE IDENTIFICATION',
    'ANALIZA DŹWIĘKU': 'AUDIO ANALYSIS',
    'Zapisano metadane': 'Metadata saved',
    'Sprawdź utwory oznaczone jako DO SPRAWDZENIA.': 'Review tracks marked NEEDS REVIEW.',
    'W tej sesji nie ma już plików oznaczonych DO SPRAWDZENIA.': 'No tracks need review in this session.',
    'Nie można oznaczyć jako GOTOWE — uzupełnij wymagane pola: ': 'Cannot mark as READY — complete the required fields: ',
    'WERYFIKACJA W BIBLIOTECE': 'REVIEW IN LIBRARY',
    'BŁĄD': 'ERROR', 'Brak': 'Missing',
    'Odtwarzanie': 'Playing', 'Pauza': 'Paused', 'Gotowy': 'Ready',
    'BRAK': 'NONE',
    'Zablokowany przed ponownym rozpoznaniem online': 'Locked against online identification',
    'Powiększona okładka': 'Enlarged cover art',
    'Kliknij okładkę, aby powiększyć': 'Click cover art to enlarge',
    'Otwórz w Discogs': 'Open in Discogs', 'Otwórz link': 'Open link',
    'Pola wymagające uwagi: ': 'Fields needing attention: ',
    'Brak ważnych danych: ': 'Missing essential data: ',
    'tytuł / wersja': 'title / version', 'wykonawca': 'artist', 'rok': 'year', 'gatunek': 'genre',
    '✓ Dane główne kompletne — nie musisz niczego uzupełniać.': '✓ Main metadata complete — nothing to add.',
    'Gotowe: ': 'Ready: ',
    'Niska pewność rozpoznania': 'Low identification confidence',
    'Zmiana pola title': 'Title changed', 'Zmiana pola artist': 'Artist changed',
    'Zmiana pola year': 'Year changed', 'Zmiana pola genre': 'Genre changed',
    'Edycja metadanych': 'Metadata edited', 'Edycja metadanych w Duplikatach': 'Metadata edited in Duplicates',
    'Oznaczenie jako GOTOWE': 'Marked as READY', 'Odznaczenie jako GOTOWE': 'Unmarked as READY',
    'Zatwierdzenie jako GOTOWE': 'Approved as READY',
    'Zapisano metadane i ustawiono ZACHOWAJ: ': 'Metadata saved and marked KEEP: ',
    'Analiza tylko wskazanego folderu…': 'Analyzing the selected folder only…',
    'Odczyt tagów, BPM, jakości i fingerprintów…': 'Reading tags, BPM, quality and fingerprints…',
    'SKANOWANIE ZAKOŃCZONE': 'SCAN COMPLETE',
    'TWORZENIE MOJEGO FOLDERU MP3': 'CREATING MY MP3 FOLDER',
    'TWORZENIE PLIKÓW': 'CREATING FILES',
    'BŁĄD OPERACJI': 'OPERATION ERROR',
    'ROZPOZNAWANIE ZAKOŃCZONE': 'IDENTIFICATION COMPLETE',
    'Bieżące zapytanie zostanie dokończone; kolejne nie będą wysyłane.': 'The current request will finish; no more requests will be sent.',
    'Zatrzymanie nastąpi bezpiecznie po zakończeniu bieżącego pliku…': 'The scan will stop after the current file finishes…',
    'Brak pozycji DO SPRAWDZENIA.': 'No tracks need review.',
    'Błąd rozpoznawania online': 'Online identification error',
    'spróbuj ponownie lub sprawdź połączenie/klucze': 'try again or check your connection and API keys',
    'Folder źródłowy i biblioteka nie mogą zawierać się wzajemnie.': 'A source folder and the library cannot be inside one another.',
    'Podaj nazwę folderu.': 'Enter a folder name.',
    'Nieobsługiwany format kopii ALO.': 'Unsupported ALO backup format.',
    'Kopia nie zawiera bazy biblioteki.': 'The backup does not contain a library database.',
    'Kopia nie przeszła weryfikacji SHA-256/rozmiaru przed zapisaniem tagów.': 'The copy failed SHA-256 or size verification before writing tags.',
    'fpcalc nie zwrócił fingerprintu Chromaprint.': 'fpcalc returned no Chromaprint fingerprint.',
    'fpcalc zwrócił nieprawidłową długość nagrania.': 'fpcalc returned an invalid recording duration.',
    'FFmpeg nie wygenerował fingerprintu Chromaprint.': 'FFmpeg could not generate a Chromaprint fingerprint.',
    'Wybrany plik nie należy do tej grupy duplikatów.': 'The selected file does not belong to this duplicate group.',
    'np. D:\\Muzyka': 'e.g. D:\\Music',
    'LOKALIZACJA': 'LOCATION', 'DOPASOWANIE': 'MATCH',
    'WYKONAWCA': 'ARTIST', 'ROK': 'YEAR', 'GATUNEK': 'GENRE',
    'KOMENTARZ': 'COMMENT', 'EDYTUJ': 'EDIT',
    'Zapisano': 'Saved', 'Klucze zapisane': 'API keys saved',
    'Ustawienia zapisane': 'Settings saved',
    'Wersja, remix, rok, gatunek i informacje o wydaniu.': 'Version, remix, year, genre and release details.',
    'Rok': 'Year', 'Tytuł': 'Title', 'Wykonawca': 'Artist', 'Gatunek': 'Genre',
    'wykonawca zgodny': 'artist matches', 'wykonawca podobny': 'artist is similar',
    'dokładny tytuł/wersja': 'exact title/version', 'tytuł/wersja podobna': 'similar title/version',
    'długość zbliżona': 'similar duration', 'długość różna': 'different duration',
    'album zgodny': 'album matches', 'album podobny': 'similar album', 'rok zgodny': 'year matches',
    'wersja potwierdzona MusicBrainz': 'version confirmed by MusicBrainz',
    'wersja zbliżona do MusicBrainz': 'similar version in MusicBrainz',
    'Nie znaleziono pewnego dopasowania online': 'No confident online match found',
    '⚠ Duża różnica względem danych sprzed online — sprawdź tożsamość utworu': '⚠ Large difference from previous data — verify the track identity',
    'Nagranie wygląda na fragment audycji / plik z prefiksem czasu': 'Recording appears to be an excerpt or a file with a time prefix',
    'Długość pliku istotnie różni się od znalezionego wydania': 'File duration differs significantly from the matched release',
    'Ręcznie zatwierdzone przez użytkownika': 'Manually approved by the user',
    'Zachowane ręcznie jako osobna wersja z grupy duplikatów': 'Manually kept as a separate version from a duplicate group',
    'Przywrócono dane sprzed rozpoznania online — sprawdź i zatwierdź': 'Data from before online identification restored — review and approve',
    'Możliwa inna wersja / potencjalny duplikat — sprawdź w zakładce Duplikaty': 'Possible different version or duplicate — check Duplicates',
    'Brak informacji o kodeku': 'Missing codec information',
    'Niekompletne podstawowe tagi': 'Incomplete essential tags',
    'dane zapisane w pliku': 'data stored in the file',
    'wydanie, wersja/remix, rok i gatunek': 'release, version/remix, year and genre',
    'katalog Apple / iTunes bez klucza API': 'Apple/iTunes catalog without an API key',
    'NAZWA': 'FILENAME', 'ANALIZA': 'ANALYSIS', '≋ ANALIZA': '≋ ANALYSIS',
    'Nazwa pliku': 'Filename', 'Przywrócone': 'Restored',
    'Zastosuj dostępne dane ze źródła: ': 'Apply available data from source: ',
    'Błąd odtwarzania:': 'Playback error:',
    'Uzupełnij dane z MusicBrainz i Apple/iTunes oraz opcjonalnie AcoustID i Discogs': 'Complete metadata with MusicBrainz and Apple/iTunes, and optionally AcoustID and Discogs',
    'Ostatni skan:': 'Last scan:', 'Pliki:': 'Files:',
    'Znajdź:': 'Find:', 'Zamień na:': 'Replace with:',
    'Tytuł / wersja:': 'Title / version:',
})
