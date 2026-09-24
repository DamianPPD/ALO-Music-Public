# ALO Music v0.4.13 — Windows

## Co nowego w v0.4.13

- Naprawiono przeskakiwanie aktualnie odtwarzanego utworu na początek Biblioteki podczas sortowania po kolumnie statusu.
- Odtwarzanie nie zmienia już tekstu używanego do sortowania tabeli.
- Aktualnie grający utwór jest wyróżniony podświetleniem całego wiersza w Bibliotece.

## Co nowego w v0.4.12

- Poprawiono wielokrotne przełączanie odsłuchu **A/B** w Duplikatach — kolejne A → B → A zachowują bieżący moment utworu.
- Naprawiono zamykanie aplikacji po zakończeniu **Rozpoznaj online** dla pojedynczego utworu.
- Dodano rozpoznawanie online pojedynczego utworu bezpośrednio z edytora metadanych.
- Dopracowano blokadę utworu przed ponownym rozpoznaniem online.
- Dodano praktyczne statystyki biblioteki na Dashboardzie oraz ekran ładowania z logo ALO.
- Przyspieszono grupowanie potencjalnych duplikatów i ograniczono zbędne zapisy dostępności plików.
- Usunięto natywny obrys aktywnej komórki w Bibliotece — pozostaje czytelne zaznaczenie całego wiersza.
- Przycisk tworzenia playlisty pokazuje teraz format: `Utwórz playlistę (.m3u8)`.
- Poprawiono stabilność odtwarzacza oraz przekazywanie wyników pracy z wątku roboczego do interfejsu.

## Co nowego w v0.4.11

- Dopracowano czytelność Biblioteki i legendę statusów.
- Zachowano ręczne decyzje dla duplikatów oraz ich widoczność po rozstrzygnięciu.
- Poprawiono fokus komórek tabeli i spójność statusu `NIE WYBIERAM`.
- Przygotowano publiczny proces wydania Windows: `ALO-Music.exe`, Portable ZIP, instalator per-user i SHA-256.

## Co nowego w v0.4.10

- Biblioteka zachowuje sortowanie, filtry, zaznaczenie, pozycję przewijania i szerokości kolumn podczas odświeżeń.
- Duplikaty mają uproszczoną kolumnę decyzji oraz pełne kolorowanie wierszy dla `ZACHOWAJ` / `NIE WYBIERAM`.
- Player ma szerszy, bardziej centralny panel sterowania.

## Co nowego w v0.4.9

- Uporządkowano prezentację decyzji w Duplikatach i rozdzielono techniczny status od wyboru użytkownika.

## Co nowego w v0.4.8

- Pierwszy wybór języka ma większy dialog i prawdziwe ikony flag PL/GB, więc tekst nie powinien być ucinany przy skalowaniu Windows.
- Blokada ponownego rozpoznania jest przyciskiem w dolnym pasku edytora: `🔓 Zablokuj online` / `🔒 Zablokowane`, w niebieskim stylu ochrony.
- `Ręcznie edytowane` usunięto z listy filtrów Biblioteki. Pola wyszukiwania/gatunku mają ograniczoną szerokość, więc BPM i lista statusów nie uciekają na prawą stronę szerokiego monitora.
- Biblioteka nie przełącza się już po kliknięciu wpisu. Kliknięcie tylko zaznacza, a dopiero `Ustaw jako aktywną` wykonuje przełączenie.
- Menu `⋯` dodatkowej biblioteki zawiera zmianę nazwy, otwarcie folderu, `Zacznij od nowa` i bezpieczne usunięcie wpisu. Żadna z tych akcji nie kasuje plików muzycznych.
- Nowa biblioteka po utworzeniu jest zaznaczona, ale nie aktywowana automatycznie.

## Co nowego w v0.4.7

W edytorze metadanych możesz włączyć jedną blokadę całego utworu: `🔒 Zablokuj dane przed ponownym rozpoznaniem online`. Zablokowane pliki są pomijane przez AcoustID, MusicBrainz i Discogs, ale nadal można je normalnie edytować ręcznie. Biblioteka pokazuje przy nich ikonę kłódki, a podsumowanie rozpoznawania podaje liczbę pominiętych zablokowanych utworów.

## Co nowego w v0.4.6

Start został uproszczony: tytułem jest nazwa aktywnej biblioteki, usunięto powtórzony pasek etapów pracy i średnie BPM. Górny pasek ma teraz prostą akcję `Biblioteki`, a `Dodaj nowe pliki` jest wyraźniej oddzielone od kroków workflow.

Ustawienia nie pokazują już rosnącej listy źródeł skanowania. Historia skanów jest dostępna w panelu Biblioteki, ma stałą wysokość, przewijanie oraz `Wyczyść historię skanów`; operacja nie usuwa muzyki. Pliki wynikowe mają czyszczone numery ścieżki i płyty (`Track Number` / `Disc Number`).

## Co nowego w v0.4.5

Duplikaty mają teraz tabelę danych zamiast układu z rekomendacją programu. ALO pokazuje różnice techniczne i podświetla wartości, które się różnią, ale nie wybiera automatycznie „lepszego” pliku. `ZACHOWAJ` jest zielone, `NIE WYBIERAM` szare, a nierozstrzygnięte techniczne duplikaty fioletowe. Licznik `Duplikaty (N)` oznacza liczbę grup czekających na decyzję.

`Rodzina wersji` łączy informacyjnie Original Mix / Radio Edit / Extended Mix / Club Mix / nazwane remiksy jednego utworu. Wyraźnie różne wersje nie są traktowane jak zwykłe duplikaty tylko dlatego, że mają wspólny materiał audio.

W edytorze metadanych usunięto panel `Przed zmianą / Po zmianie`; dane sprzed rozpoznania online są większe i czytelniejsze. Z paska statusu usunięto powtórzenie `Wymaga sprawdzenia`.

W `Biblioteki` ścieżka oznacza teraz folder **docelowy**, w którym ALO zapisuje lub będzie zapisywać pliki wynikowe. Aktywna biblioteka jest wyróżniona zielono i ma link otwierający folder w Eksploratorze. Osobny przewijany panel pokazuje historię skanowanych źródeł z datą i liczbą plików.

Przed utworzeniem plików podgląd pokazuje konflikty nazw i istniejące cele; ALO nadal nie nadpisuje plików.

Ta wersja jest pełną paczką projektu — bez osobnego hotfixa.

## Co nowego w v0.4.4

Biblioteka ma teraz jeden czytelny stan wymagający uwagi: `DO SPRAWDZENIA`. Stare `Do decyzji` zostało usunięte. Zwykła kontrola jest oznaczana bursztynowo, a naprawdę poważny problem czerwono — tekst statusu pozostaje ten sam.

W edytorze metadanych u góry widać `AKTUALNY STATUS: ...`, a przy Discogs URL jest przycisk otwierający poprawny link bezpośrednio w domyślnej przeglądarce. Ręczne zatwierdzenie kompletnego utworu jako `GOTOWE` ma pierwszeństwo nad starymi ostrzeżeniami z rozpoznawania online.

Odtwarzanie w Bibliotece jest niezależne od samego zaznaczenia: pojedynczy klik tylko wybiera wiersz, dwuklik rozpoczyna odsłuch. Aktualny utwór pozostaje odtwarzany podczas przeglądania tabeli i jest oznaczony jako `TERAZ GRA`. Menu kontekstowe pozwala ustawić `Odtwórz jako następny`; player pokazuje źródło i zaplanowaną kolejną pozycję. Przyciski `Poprzedni` / `Następny` zostały usunięte z Biblioteki.

Ta wersja jest pełną paczką projektu — bez osobnego hotfixa.

## Co nowego w v0.4.3

Przy pierwszym uruchomieniu ALO pokazuje mały ekran `Polski / English`. Wybrany język jest zapamiętywany; po użyciu pełnego resetu ekran pojawi się ponownie.

W panelu `Biblioteki` znajduje się `Resetuj ALO do czystego stanu`. Ta funkcja usuwa rejestr bibliotek, aktywną bibliotekę, lokalne bazy/indexy i zapisane ustawienia ALO. **Nie usuwa plików MP3 ani folderów z muzyką.** Po resecie program należy uruchomić ponownie i skonfigurować jak za pierwszym razem.

Synchronizacja/pełne skanowanie usuwa z indeksu rekordy plików, które zostały skasowane z dysku. Dzięki temu stary utwór nie powinien nadal wisieć w Bibliotece po usunięciu źródłowego MP3.

Biblioteka główna oraz dodatkowe biblioteki nadal są od siebie oddzielone. Usunięcie dodatkowej biblioteki usuwa jej wpis z ALO, nie muzykę.

Ta wersja jest pełną paczką projektu — bez osobnego hotfixa.

## Najprostsze uruchomienie

1. Zainstaluj Python 3.11+ (docelowo projekt jest rozwijany na Pythonie 3.12).
2. Rozpakuj cały projekt w jednym katalogu, np. `C:\ALO_Music`.
3. Uruchom `run_audio_library_organizer.bat`.
4. Przy pierwszym uruchomieniu skrypt utworzy `.venv`, zainstaluje zależności i przygotuje `fpcalc`/Chromaprint.
5. Wybierz `Polski` albo `English`.
6. W kreatorze wybierz foldery źródłowe oraz miejsce i nazwę biblioteki docelowej.

Nie usuwaj `.venv` podczas instalowania kolejnej pełnej aktualizacji.

## Bezpieczeństwo

ALO Music nie modyfikuje plików źródłowych. Eksport działa na kopiach. Przed zmianą tagów program porównuje surową kopię ze źródłem przez SHA-256/rozmiar, a po zapisaniu tagów sprawdza istnienie i rozmiar pliku końcowego.

## Foldery wynikowe

Domyślnie:

- `GOTOWE`
- `NIE_WYBRANE`
- `DO_SPRAWDZENIA`
- `MOJE_FOLDERY_MP3` — własne zestawy z fizycznymi kopiami wybranych utworów
- `.alo` — trwała baza ALO Music
- `raporty`

`DUPLIKAT` i `NIE WYBIERAM` są archiwizowane w `NIE_WYBRANE`. Nic nie jest automatycznie kasowane.

W Ustawieniach można opcjonalnie organizować `GOTOWE` według wykonawcy **albo** gatunku. Domyślnie: `Bez podfolderów`.

## Rozpoznawanie online

### AcoustID

1. Otwórz `https://acoustid.org/new-application`.
2. Zaloguj się i utwórz aplikację, np. `Audio Library Organizer`.
3. Skopiuj **Application API Key / client key**.
4. Wklej go w `Ustawienia → Integracje i klucze API → AcoustID`.

### Discogs

1. Zaloguj się do Discogs.
2. Otwórz `https://www.discogs.com/settings/developers`.
3. Wygeneruj **Personal Access Token**.
4. Wklej go w `Ustawienia → Integracje i klucze API → Discogs`.

MusicBrainz nie wymaga osobnego klucza do zwykłego odczytu. Nie udostępniaj tokenów innym osobom.

## Przebieg pracy

1. `Skanuj foldery` — tagi, długość, jakość, BPM/fingerprint.
2. `Rozpoznaj utwory online` — AcoustID/MusicBrainz/Discogs; podczas pracy ten sam przycisk pozwala bezpiecznie anulować lub wznowić operację.
3. `Sprawdź w Bibliotece` — metadane, okładki, duplikaty i pozycje `DO SPRAWDZENIA`.
4. `Utwórz pliki wynikowe` — kopie, tagi, okładki i techniczna kontrola.

Podczas skanowania przycisk zmienia się w czerwone `Anuluj skanowanie`; zatrzymanie następuje bezpiecznie po bieżącym pliku.

## Biblioteki

- `Biblioteka główna` — podstawowa, stała baza ALO.
- `Nowa biblioteka` — zapisana, oddzielna baza z własnym folderem docelowym; foldery źródłowe do skanowania dodajesz osobno.
- Kliknij całą pozycję biblioteki, aby ją aktywować.
- `Usuń bibliotekę` usuwa tylko wpis i bazę ALO; muzyka na dysku pozostaje bez zmian.

Kliknij wyraźny wskaźnik aktywnej biblioteki u góry programu, aby otworzyć panel zarządzania.

## Playlisty i Moje foldery MP3

Z Biblioteki oraz `Moje foldery / Moje pliki` można utworzyć playlistę `M3U8`. Pliki z `Moje pliki` korzystają z tego samego wspólnego odtwarzacza ALO. Folder `MOJE_FOLDERY_MP3` nadal jest wyłączony ze skanowania źródeł, aby własne kopie nie wracały jako duplikaty.

## Duplikaty

ALO Music wykrywa **potencjalne** duplikaty. Dla każdego pliku masz trzy proste akcje:

- `★ ZACHOWAJ`
- `× NIE WYBIERAM`
- `✎ EDYTUJ`

Jeżeli plik jest inną poprawną wersją, edytuj jego tytuł/wersję i zachowaj go. `DUPLIKAT` jest automatycznym stanem technicznym programu, nie osobnym przyciskiem. Zmiana od razu jest widoczna w Bibliotece. `DUPLIKAT` i `NIE WYBIERAM` trafią przy eksporcie do `NIE_WYBRANE`.

## Metadane i okładki

Dane główne: wykonawca, tytuł/wersja, rok, gatunek i BPM. Ich brak blokuje zielone `GOTOWE`.

Dane dodatkowe: Album/Release, Discogs URL, komentarz. Ich brak nie blokuje GOTOWE.

W edytorze można porównać okładkę obecną, pobraną, własną i placeholder `BRAK OKŁADKI`. Plik wynikowy zawsze otrzymuje grafikę.

## Kontakt

W dolnej części Ustawień znajduje się:

`Powered by Damian`

`Kontakt: GitHub Issues — https://github.com/DamianPPD/ALO-Music-Public/issues`

Adres jest klikalny; player nie powiela tych informacji.

## Build developerski EXE

W PowerShell w katalogu projektu:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Wynik: `dist\ALO-Music\ALO-Music.exe`.

## Pełne wydanie Windows

Wymagania: Python 3.11+ oraz Inno Setup 6 z `ISCC.exe`.

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\build_release_windows.ps1
```

Skrypt buduje i smoke-testuje aplikację, tworzy Portable ZIP, instalator per-user oraz `SHA256SUMS.txt` w `release\v<wersja>\`.
