# ALO Music — Audio Library Organizer

**ALO Music** to desktopowa aplikacja dla Windows do bezpiecznego porządkowania dużych bibliotek muzycznych. Skanuje lokalne foldery, analizuje pliki audio i metadane, pomaga rozpoznawać utwory online, porównuje potencjalne duplikaty i tworzy uporządkowane pliki wynikowe — bez ingerowania w oryginały.

**Wersja wyświetlana: 0.4.24** · Windows · interfejs PL / EN · kod źródłowy dostępny publicznie · projekt aktywnie rozwijany

> **Najważniejsza zasada ALO:** pliki źródłowe pozostają nietknięte. Program pracuje na indeksie biblioteki i tworzy osobne kopie wynikowe.

## Co potrafi ALO Music

- skanowanie dużych folderów z muzyką i budowanie lokalnej biblioteki,
- rozpoznawanie nagrań i uzupełnianie danych z **MusicBrainz, Apple/iTunes oraz opcjonalnie AcoustID i Discogs**,
- rozpoznawanie online całej biblioteki albo pojedynczego utworu bezpośrednio z edytora metadanych,
- analiza BPM oraz kontrola podstawowych danych technicznych pliku,
- edycja wykonawcy, tytułu / wersji, roku, gatunku, BPM, albumu, komentarza i okładki,
- czytelne statusy: **GOTOWE**, **DUPLIKAT**, **DO SPRAWDZENIA** i **NIE WYBIERAM**,
- ręczne porównywanie duplikatów bez automatycznego wybierania „lepszego” pliku,
- odsłuch A/B potencjalnych duplikatów z zachowaniem tej samej pozycji utworu przy kolejnych przełączeniach,
- rozróżnianie wersji takich jak Radio Edit, Extended Mix, Original Mix, Club Mix i remix,
- blokowanie wybranego utworu przed ponownym rozpoznawaniem online,
- wyszukiwanie, filtrowanie i ręczne sortowanie biblioteki,
- zachowywanie pozycji listy przy zmianie statusu w edytorze metadanych,
- wbudowany odsłuch oraz kolejkę „odtwórz jako następny”,
- tworzenie playlist **M3U8** z zaznaczonych utworów,
- obsługę wielu bibliotek i własnych folderów MP3,
- bezpieczne tworzenie uporządkowanych plików wynikowych bez automatycznego kasowania muzyki.

## Prosty przepływ pracy

**1. Skanuj foldery → 2. Rozpoznaj utwory online → 3. Sprawdź w Bibliotece → 4. Utwórz pliki wynikowe**

ALO prowadzi użytkownika przez cały proces jednym paskiem etapów. Po skanowaniu od razu widać, ile utworów jest gotowych, ile wymaga sprawdzenia i czy wykryto potencjalne duplikaty.

## Ostatnie zmiany

Pełna historia zmian znajduje się w pliku **[CHANGELOG.md](CHANGELOG.md)**.

### v0.4.23 — kod źródłowy do publikacji

- uporządkowano Ustawienia i przeniesiono szybki dostęp do folderów na ekran Start,
- poprawiono zaznaczanie i wielokrotne kopiowanie fragmentów nazwy utworu w edytorze metadanych.

### v0.4.15 — 14.09.2026

- uproszczono ekran **Start** i usunięto z niego zduplikowane przyciski **Skanuj bibliotekę**, **Rozpoznaj online** i **Duplikaty** — główne akcje pozostają w górnym pasku programu,
- usunięto dodatkowy napis z numerem wersji z prawego dolnego rogu Startu,
- dodano kompaktową sekcję **Statystyki biblioteki** z informacjami o okładkach, rozpoznaniu online, brakujących plikach, podejrzanych danych, rozmiarze biblioteki i wolnym miejscu na dysku,
- ekran uruchamiania pokazuje teraz numer wersji programu obok logo i statusu ładowania,
- pogrubiono pasek postępu odtwarzacza i powiększono jego uchwyt, żeby był wyraźniejszy i wygodniejszy w obsłudze.

### v0.4.14 — 14.09.2026

- przebudowano ekran **Start** na bardziej kompaktowy dashboard,
- dodano pasek ścieżki aktywnej biblioteki z przyciskiem **Otwórz folder**,
- dodano klikalne liczniki **Utwory**, **Do sprawdzenia**, **Duplikaty** i **Brak okładki** prowadzące do odpowiednich widoków,
- dodano zapamiętywaną informację o czasie ostatniego skanowania,
- dodano komunikat **Wymaga uwagi**, widoczny tylko wtedy, gdy biblioteka faktycznie ma pozycje wymagające kontroli,
- loader startowy po wczytaniu biblioteki pokazuje liczbę gotowych do wyświetlenia utworów.

### v0.4.13 — 14.09.2026

- zmiana statusu **GOTOWE / DO SPRAWDZENIA** z edytora metadanych nie powoduje już przeskakiwania ani ponownego centrowania wiersza w Bibliotece,
- po zmianie statusu zachowywana jest bieżąca pozycja listy, przewinięcie i kolejność utworów; sortowanie zmienia się dopiero po świadomej akcji użytkownika,
- naprawiono przeskakiwanie aktualnie odtwarzanego utworu podczas sortowania po statusie,
- stan odtwarzania nie wpływa już na tekst używany do sortowania tabeli,
- aktualnie grający utwór jest wyróżniony podświetleniem całego wiersza,
- poprawiono czyszczenie tytułów zawierających dopiski stron internetowych,
- poprawiono dopasowywanie wykonawców zapisanych w różny sposób, np. `Get Far & Sagi Rei` oraz `Get Far feat. Sagi Rei`,
- rozdzielono brak dopasowania od rzeczywistego błędu usług MusicBrainz / Discogs.

### v0.4.12 — 14.09.2026

- poprawiono wielokrotne przełączanie odsłuchu **A/B** w Duplikatach — A → B → A zachowuje bieżący moment utworu,
- naprawiono zamykanie aplikacji po zakończeniu **Rozpoznaj online** dla pojedynczego utworu,
- dodano rozpoznawanie online pojedynczego utworu bezpośrednio z edytora metadanych,
- dopracowano blokadę utworu przed ponownym rozpoznaniem online,
- dodano praktyczne statystyki biblioteki na Dashboardzie,
- dodano ekran ładowania z logo ALO,
- przyspieszono grupowanie potencjalnych duplikatów i ograniczono zbędne zapisy dostępności plików,
- poprawiono stabilność odtwarzacza i obsługę wyników z wątków roboczych.

## Widoki programu

### Start — stan biblioteki i szybkie statystyki

Ekran Start pokazuje aktywną bibliotekę, klikalne liczniki najważniejszych grup oraz praktyczne statystyki: liczbę i procent utworów z okładką, liczbę i procent utworów sprawdzonych online, brakujące pliki, podejrzane dane, rozmiar biblioteki i wolne miejsce na dysku. Informacja **Wymaga uwagi** pojawia się tylko wtedy, gdy jest coś do sprawdzenia.

### Biblioteka — wyszukiwanie, statusy i szczegóły utworu

Biblioteka łączy dużą tabelę utworów z wyszukiwaniem, filtrami, danymi technicznymi i panelem szczegółów. Kolory statusów pozwalają szybko znaleźć pozycje wymagające uwagi. Aktualnie grający utwór ma wyróżniony cały wiersz bez zmiany kolejności sortowania.

Zmiana statusu **GOTOWE / DO SPRAWDZENIA** w edytorze metadanych nie przenosi już utworu w inne miejsce ani nie centruje automatycznie jego wiersza. Lista pozostaje dokładnie tam, gdzie była, a sortowanie zmienia się dopiero po ręcznej akcji użytkownika.

### Duplikaty — decyzję podejmuje użytkownik

ALO zestawia potencjalnie podobne pliki i pokazuje m.in. długość, BPM, format, bitrate, częstotliwość próbkowania oraz rozmiar. Program **nie wybiera automatycznie zwycięzcy** — użytkownik sam oznacza `ZACHOWAJ` albo `NIE WYBIERAM`.

Do szybkiego porównania można używać odsłuchu **A/B**. Przy przełączaniu między plikami ALO zachowuje bieżący moment odtwarzania, dzięki czemu łatwiej wychwycić różnice jakości, masteringu albo wersji nagrania.

### Edytor metadanych — wszystko w jednym miejscu

Edytor pozwala sprawdzić dane przed i po rozpoznaniu online, wybrać okładkę, poprawić metadane, sterować źródłami danych, odsłuchać utwór i kontrolować nazwę pliku wynikowego.

Dla pojedynczego utworu można uruchomić **Rozpoznaj online** bez skanowania całej biblioteki. Dostępna jest też blokada przed ponownym rozpoznaniem, która chroni ręcznie poprawione dane przed późniejszym zastąpieniem.

## Wydajność i uruchamianie

ALO pokazuje ekran ładowania podczas startu aplikacji wraz z numerem aktualnej wersji. Po wczytaniu biblioteki loader krótko pokazuje liczbę dostępnych utworów, zanim otworzy się główne okno programu.

Mechanizm grupowania potencjalnych duplikatów wykorzystuje wstępne grupowanie kandydatów zamiast porównywania każdej pozycji z każdą, co ogranicza zbędną pracę przy większych bibliotekach.

Aktualizacja informacji o dostępności plików zapisuje do bazy tylko rzeczywiste zmiany, zamiast wykonywać niepotrzebne operacje dla całej biblioteki.

## Bezpieczeństwo danych

ALO Music został zaprojektowany tak, aby porządkowanie kolekcji nie oznaczało ryzyka utraty oryginałów. Źródłowe pliki muzyczne nie są modyfikowane ani automatycznie usuwane. Pliki wynikowe powstają jako osobne kopie, a istniejące cele nie są bezmyślnie nadpisywane. Decyzje dotyczące duplikatów i utworów odrzuconych zawsze należą do użytkownika.

## Rozpoznawanie online

ALO może korzystać z **MusicBrainz**, **Apple/iTunes**, **AcoustID / Chromaprint** i **Discogs**. Połączenie z Internetem jest potrzebne do rozpoznawania i pobierania danych online; samo przeglądanie i porządkowanie lokalnej biblioteki pozostaje funkcją desktopową.

Rozpoznawanie można uruchomić dla większej partii utworów albo tylko dla aktualnie otwartego utworu w edytorze metadanych. Wybrane utwory można zablokować przed kolejnym rozpoznaniem online, dzięki czemu ręcznie poprawione dane nie zostaną przypadkowo zastąpione.

## Publiczna wersja dla Windows

Kod źródłowy ALO Music jest dostępny w [publicznym repozytorium](https://github.com/DamianPPD/ALO-Music-Public). Gotowe wydania dla Windows mogą być udostępniane osobno jako program Portable i instalator.

Do każdego wydania będzie podawana suma **SHA-256**, aby można było sprawdzić integralność pobranego pliku.

## Stan projektu

ALO Music jest aktywnie rozwijany. Wersja aplikacji **0.4.23** porządkuje Ustawienia oraz poprawia wielokrotne kopiowanie fragmentów nazwy utworu w edytorze metadanych. Publikacja kodu źródłowego nie oznacza jeszcze wydania gotowego instalatora ani tagu v0.4.23.

## Licencja

ALO Music jest udostępniany na licencji **GNU GPL v3 lub nowszej** (`GPL-3.0-or-later`). Pełny tekst znajduje się w pliku [LICENSE](LICENSE).

---

**ALO Music — porządkuj bibliotekę, zachowując kontrolę nad każdym plikiem.**
