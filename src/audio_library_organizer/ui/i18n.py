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


def translate_static_text(text: str, language: str) -> str:
    if language != 'en':
        return text
    if text in TEXT_MAP_EN:
        return TEXT_MAP_EN[text]
    if '\n' in text:
        return '\n'.join(TEXT_MAP_EN.get(line, _dynamic_en(line)) for line in text.split('\n'))
    return _dynamic_en(text)


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
