# ALO Music — Audio Library Organizer

**ALO Music** to desktopowa aplikacja dla Windows do bezpiecznego porządkowania dużych bibliotek muzycznych. Skanuje lokalne foldery, analizuje pliki audio i metadane, pomaga rozpoznawać utwory online, porównuje potencjalne duplikaty i tworzy uporządkowane pliki wynikowe — bez ingerowania w oryginały.

**Aktualna wersja: 0.4.11** · Windows · interfejs PL / EN · projekt aktywnie rozwijany

> **Najważniejsza zasada ALO:** pliki źródłowe pozostają nietknięte. Program pracuje na indeksie biblioteki i tworzy osobne kopie wynikowe.

## Pobieranie

Gotowe wydania dla Windows są publikowane w sekcji **Releases** tego repozytorium.

Każde wydanie zawiera:

- instalator `Setup.exe`,
- wersję Portable w archiwum ZIP,
- plik `SHA256SUMS.txt` do weryfikacji integralności pobranych plików.

Kod źródłowy ALO Music pozostaje prywatny i nie jest częścią tego repozytorium ani paczek publicznych.

## Co potrafi ALO Music

- skanowanie dużych folderów z muzyką i budowanie lokalnej biblioteki,
- rozpoznawanie nagrań i uzupełnianie danych z **AcoustID, MusicBrainz i Discogs**,
- analiza BPM oraz kontrola podstawowych danych technicznych pliku,
- edycja wykonawcy, tytułu / wersji, roku, gatunku, BPM, albumu, komentarza i okładki,
- czytelne statusy: **GOTOWE**, **DUPLIKAT**, **DO SPRAWDZENIA** i **NIE WYBIERAM**,
- ręczne porównywanie duplikatów bez automatycznego wybierania „lepszego” pliku,
- rozróżnianie wersji takich jak Radio Edit, Extended Mix, Original Mix, Club Mix i remix,
- blokowanie wybranego utworu przed ponownym rozpoznawaniem online,
- wyszukiwanie, filtrowanie i sortowanie biblioteki,
- wbudowany odsłuch oraz kolejkę „odtwórz jako następny”,
- obsługę wielu bibliotek i własnych folderów MP3,
- bezpieczne tworzenie uporządkowanych plików wynikowych bez automatycznego kasowania muzyki.

## Prosty przepływ pracy

**1. Skanuj foldery → 2. Rozpoznaj utwory online → 3. Sprawdź w Bibliotece → 4. Utwórz pliki wynikowe**

ALO prowadzi użytkownika przez cały proces jednym paskiem etapów. Po skanowaniu od razu widać, ile utworów jest gotowych, ile wymaga sprawdzenia i czy wykryto potencjalne duplikaty.

## Zrzuty ekranu

### Start — stan biblioteki i postęp pracy

![ALO Music — Start](docs/screenshots/alo-start.jpg)

Ekran Start pokazuje postęp bieżącej operacji, liczbę plików, statusy biblioteki, poziom uporządkowania oraz najważniejsze statystyki.

### Biblioteka — wyszukiwanie, statusy i szczegóły utworu

![ALO Music — Biblioteka](docs/screenshots/alo-library.jpg)

Biblioteka łączy dużą tabelę utworów z wyszukiwaniem, filtrami, danymi technicznymi i panelem szczegółów. Kolory statusów pozwalają szybko znaleźć pozycje wymagające uwagi.

### Duplikaty — decyzję podejmuje użytkownik

![ALO Music — Duplikaty](docs/screenshots/alo-duplicates.jpg)

ALO zestawia potencjalnie podobne pliki w jednej tabeli i pokazuje m.in. długość, BPM, format, bitrate, częstotliwość próbkowania oraz rozmiar. Program **nie wybiera automatycznie zwycięzcy** — użytkownik sam oznacza `ZACHOWAJ` albo `NIE WYBIERAM`.

### Edytor metadanych — wszystko w jednym miejscu

![ALO Music — Edytor metadanych](docs/screenshots/alo-metadata-editor.jpg)

Edytor pozwala sprawdzić dane przed i po rozpoznaniu online, wybrać okładkę, poprawić metadane, sterować źródłami danych, odsłuchać utwór, zablokować ponowne rozpoznawanie i kontrolować nazwę pliku wynikowego.

## Bezpieczeństwo danych

ALO Music został zaprojektowany tak, aby porządkowanie kolekcji nie oznaczało ryzyka utraty oryginałów. Źródłowe pliki muzyczne nie są modyfikowane ani automatycznie usuwane. Pliki wynikowe powstają jako osobne kopie, a istniejące cele nie są bezmyślnie nadpisywane. Decyzje dotyczące duplikatów i utworów odrzuconych zawsze należą do użytkownika.

## Rozpoznawanie online

ALO może korzystać z **AcoustID / Chromaprint**, **MusicBrainz** i **Discogs**. Połączenie z Internetem jest potrzebne do rozpoznawania i pobierania danych online; samo przeglądanie i porządkowanie lokalnej biblioteki pozostaje funkcją desktopową.

Wybrane utwory można zablokować przed kolejnym rozpoznaniem online, dzięki czemu ręcznie poprawione dane nie zostaną później przypadkowo zastąpione.

## Stan projektu

ALO Music jest aktywnie rozwijany. Obecna linia **v0.4.11** skupia się na dopracowaniu interfejsu, czytelności statusów, ręcznej obsłudze duplikatów i bezpiecznej pracy na dużych bibliotekach muzycznych.

---

**ALO Music — porządkuj bibliotekę, zachowując kontrolę nad każdym plikiem.**
