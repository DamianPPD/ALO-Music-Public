# Historia zmian — ALO Music

Ten plik opisuje najważniejsze zmiany w kolejnych wersjach ALO Music.

## v0.4.23 — stan kodu źródłowego do publikacji

- uporządkowano Ustawienia w sekcje konfiguracyjne bez dublowania szybkiego dostępu do folderów ze Startu,
- umożliwiono zmianę lokalizacji biblioteki z walidacją folderu docelowego i zachowaniem skonfigurowanych źródeł,
- poprawiono zaznaczanie i wielokrotne kopiowanie fragmentów nazwy utworu w edytorze metadanych.

## v0.4.22 — zmiany rozwojowe

- dodano na ekranie Start szybki dostęp do folderów aktywnej biblioteki,
- uporządkowano karty integracji oraz informacje o ich konfiguracji,
- dopracowano pola gatunków, statusy metadanych i obsługę ładowania okładek.

## v0.4.21 — gałąź rozwojowa (bez release’u i tagu)

- ustabilizowano responsywny układ trzech głównych kolumn edytora metadanych,
- dopracowano pasek utworu, tabelę źródeł, panel okładki, statusy pól i dolne akcje,
- wprowadzono cienki, spójny system ikon edytora oraz lżejszą typografię,
- uproszczono akcje okładek do „Dodaj” i jednego wyszukiwania online; dodatkowe wyniki rozwija warunkowe „Pokaż więcej”,
- przeniesiono kompaktową blokadę do grupy rozpoznawania oraz pokolorowano kropki i nazwy źródeł,
- dodano bezpieczny preprocessing zapytań: wykrywanie tagów-witryn i watermarków, fallback z nazwy pliku oraz oszczędne warianty wyszukiwania bez zapisywania danych heurystycznych,
- ujednolicono kolory źródeł także w listach pól i informacji o rozpoznaniu, wyróżniono główną akcję online i wyrównano kłódkę,
- nazwa pliku w pasku utworu pozwala zaznaczać i kopiować fragmenty, a nagłówek oferuje nawigację po widocznej liście plików,
- powiększono i uporządkowano siatkę propozycji okładek oraz dodano własny dialog bezpiecznego zamykania obsługiwany jednakowo przez Esc i X,
- zachowano dotychczasową logikę edycji, rozpoznawania, okładek i odtwarzania,
- numer aplikacji i plików ustawiono na 0.4.21; release i tag wymagają osobnego zatwierdzenia.

## Zmiany rozwojowe — gałąź v0.4.21-dev (bez wydania)

Poniższe wcześniejsze zmiany rozwojowe powstały na bazie v0.4.20 i nie stanowiły release’u ani tagu v0.4.21.

- naprawiono niezgodny z Qt selektor `:not(:checked)`; błąd powodował komunikat o niepoprawnym arkuszu stylów i utrudniał stosowanie wcześniejszych zmian wyglądu,
- przebudowano główny player: okładka obejmuje dwa rzędy, tytuł jest nad wykonawcą, centralny transport ma biały Play z turkusowym obramowaniem, głośność jest obok osi czasu,
- dodano rzeczywisty przebieg amplitudy pliku z klikaniem i przeciąganiem pozycji; analiza działa w tle, z ograniczonym zużyciem pamięci i odrzucaniem wyników poprzedniego utworu,
- pliki nieobsługiwane przez dekoder waveform zachowują linię przewijania; nie są wyświetlane fikcyjne fale,
- dodano wybór rzeczywistych wyjść audio i obsługę odłączenia urządzenia,
- mini-player pokazuje nazwę i wykonawcę edytowanego utworu oraz zachowuje wspólną głośność i odtwarzanie,
- zabezpieczono układ przed rozpychaniem okna przez długie nazwy,
- zsynchronizowano przebieg audio mini-playera i zablokowano przewijanie innego utworu niż edytowany,
- przeniesiono blokadę online do górnego paska rozpoznawania i dodano wskaźniki statusu oraz kropki źródeł przy polach,
- dodano przewijany środek edytora z zawsze widocznym mini-playerem i dolnymi akcjami,
- zachowano dotychczasowe poprawki edytora v0.4.20; bez EXE, Portable i publicznej publikacji.

Weryfikacja lokalna obejmuje testy i renderowanie Qt na Linuxie. Odsłuch oraz przełączanie fizycznych urządzeń wymagają sprawdzenia na Windowsie.

## v0.4.20 — prywatna wersja testowa

- wymuszono kolory paska kroków 1–4 bezpośrednio na przyciskach, aby stare style nie mogły ponownie przywrócić bursztynowych/brązowych wariantów,
- panel propozycji okładek ma zwarty obramowany blok jak we wzorze, cztery miniatury w rzędzie i brak podpisów rozbijających układ,
- legenda źródeł używa tego samego symbolu ⓘ co Legenda statusów w Bibliotece,
- dodano automatyczne renderowanie kontrolnych screenshotów na Windowsie; wersja nie jest uznawana za gotową wyłącznie na podstawie testów kodu,
- nadal bez budowania EXE i Portable na prywatnej gałęzi.


## v0.4.19 — prywatna wersja testowa

### Edytor zgodny z zaakceptowanymi wzorami

- górna nawigacja i pasek kroków 1–4 zachowują dokładnie ustaloną zielono-turkusowo-niebieską kolorystykę,
- nagłówki kart edytora mają spokojny biały tekst i małe turkusowe ikony jak na wzorze,
- przyciski Rozpoznaj online i Przywróć dane sprzed online mają prawdziwe ikony,
- panel okładki ma dużą wybraną okładkę po lewej, przyciski pod nią oraz zwartą siatkę 4 propozycji w rzędzie po prawej,
- BRAK OKŁADKI jest zwykłą pozycją w siatce propozycji,
- tabela Porównanie źródeł ma niższy nagłówek i wiersze, mniejszy tekst źródła oraz większą kolorową kropkę,
- kolumna Akcja pozostaje wystarczająco szeroka, a Użyj danych mieści pełny tekst,
- dolne akcje edytora korzystają z ikon; status jest oddzielony od zielonego przycisku ZATWIERDŹ JAKO GOTOWE,
- prywatna gałąź nadal uruchamia tylko testy — bez EXE i Portable.


## v0.4.18 — prywatna wersja testowa

### Interfejs zgodny z zaakceptowanym wzorem

- wprowadzono własny zestaw wektorowych ikon ALO, niezależny od motywu Windows i fontów systemowych,
- górna nawigacja i kroki 1–4 używają spójnych ikon oraz neutralnych ciemnych przycisków; zielony akcent wskazuje aktywny element,
- edytor metadanych został ujednolicony jako zestaw kart: Metadane utworu, Status pliku, Rozpoznanie, Okładka, Nazwa wynikowa i Porównanie źródeł,
- Status pliku ma wyraźne zielone, bursztynowe i neutralne stany wraz z ikoną oraz kolorem tekstu,
- legenda źródeł korzysta z tej samej spokojnej ikony informacji co pozostałe elementy informacyjne,
- poszerzono kolumnę Akcja i przycisk Użyj danych, aby tekst nie był przycinany także przy skalowaniu Windows,
- opis pod nazwą wynikową jest mniejszy, przygaszony i pochylony,
- odtwarzacze używają własnych ikon ALO; symbole play/pause są białe,
- sekcja Integracje i klucze API ma osobne karty z ikonami dla AcoustID, Discogs, MusicBrainz i Apple/iTunes.

### Dystrybucja

- prywatna gałąź uruchamia tylko testy; EXE, Portable ZIP i instalator będą budowane dopiero przy przygotowaniu wersji publicznej.


## v0.4.17 — wersja testowa

### Interfejs i edytor metadanych

- zastąpiono tekstowe symbole w górnej nawigacji i workflow prawdziwymi ikonami Qt,
- dopracowano panel **Status pliku**: zielony = OK, bursztynowy = wymaga uwagi, szary = neutralny,
- przebudowano **Rozpoznanie** na osobne wiersze: źródło, liczba pól, długość, bitrate i pewność,
- tekst pomocniczy pod nazwą wynikową jest teraz mniejszy, szary i pochylony,
- legenda źródeł korzysta z normalnej ikony informacji oraz kolorowych oznaczeń źródeł,
- tabela porównania źródeł zaznacza cały wiersz jak Biblioteka, bez białej ramki aktywnej komórki,
- poprawiono czytelność przycisku **Użyj danych** i wysokość wierszy tabeli,
- mini-player w edytorze ma większy okrągły przycisk play/pause z prawdziwą ikoną,
- główny odtwarzacz ma bardziej zaokrąglone przyciski transportu i prawdziwe ikony odtwarzania.

### Rozpoznawanie

- pojedyncze rozpoznawanie online nie pyta już o brak kluczy, bo MusicBrainz i Apple/iTunes działają bez nich,
- zachowano obsługę prefiksów czasu, BPM z nazwy, `rmx → Remix` oraz wariantów `Relocate / Re:Locate`,
- pliki radiowe i wyraźne różnice długości nadal pozostają **DO SPRAWDZENIA**.


## v0.4.16 — wersja testowa

### Edytor metadanych i interfejs

- odświeżono edytor metadanych bez zmiany modelu ręcznej edycji każdego pola,
- połączono dane główne i dodatkowe w jeden zwarty formularz oraz dodano kompaktowy status pliku,
- usunięto powielony górny pasek statusu; status pozostaje na dole edytora,
- dodano pomocnicze porównanie źródeł z możliwością zastosowania danych z wybranego źródła i małą rozwijaną legendą,
- przebudowano wybór okładki: większy podgląd, galeria wszystkich dostępnych propozycji i źródła online,
- zmieniono przycisk nazwy na **Przywróć nazwę z metadanych**,
- dodano minimalistyczny odtwarzacz wewnątrz edytora: play/pause, szeroki pasek przewijania, czas i głośność,
- uproszczono główny odtwarzacz i ujednolicono wygląd przycisków oraz nawigacji z ikonami.

### Rozpoznawanie i źródła

- dodano bezkluczowy katalog **Apple / iTunes** jako dodatkowe źródło danych i okładek,
- rozpoznawanie może działać bez kluczy API przez MusicBrainz + Apple/iTunes; AcoustID i Discogs pozostają opcjonalnym rozszerzeniem,
- parser nazw usuwa prefiksy czasu typu `12-07-56 -`, rozpoznaje `[138bpm]` i normalizuje `rmx` do `Remix`,
- wyszukiwanie obsługuje warianty `Relocate` / `Re:Locate` bez automatycznej zmiany danych,
- pliki wyglądające na fragment audycji lub istotnie różniące się długością od wydania pozostają **DO SPRAWDZENIA**.


## v0.4.13 — 14.09.2026

### Biblioteka i edytor metadanych

- zmiana statusu **GOTOWE / DO SPRAWDZENIA** z edytora metadanych nie powoduje już ponownego centrowania ani przeskakiwania wiersza w Bibliotece,
- po zmianie statusu zachowywana jest bieżąca pozycja listy, przewinięcie i kolejność utworów; sortowanie zmienia się dopiero po świadomej akcji użytkownika,
- stan odtwarzania nie wpływa już na tekst używany do sortowania tabeli,
- aktualnie odtwarzany utwór jest wyróżniony podświetleniem całego wiersza bez zmiany jego pozycji.

### Rozpoznawanie i metadane

- poprawiono czyszczenie tytułów zawierających dopiski stron internetowych, np. `Www.Djwitek.Org`,
- poprawiono dopasowywanie wykonawców zapisanych w różny sposób, np. `Get Far & Sagi Rei` oraz `Get Far feat. Sagi Rei`,
- rozdzielono brak dopasowania od rzeczywistego błędu usług MusicBrainz / Discogs, dzięki czemu komunikaty są bardziej jednoznaczne.

### Stabilność

- dodano testy regresyjne dla zmian w rozpoznawaniu, sortowaniu, statusach i podświetlaniu aktualnie granego utworu.

## v0.4.12 — 14.09.2026

- poprawiono wielokrotne przełączanie odsłuchu **A/B** w Duplikatach — kolejne A → B → A zachowują bieżący moment utworu,
- naprawiono zamykanie aplikacji po zakończeniu **Rozpoznaj online** dla pojedynczego utworu,
- dodano rozpoznawanie online pojedynczego utworu bezpośrednio z edytora metadanych,
- dopracowano blokadę utworu przed ponownym rozpoznaniem online,
- dodano praktyczne statystyki biblioteki na Dashboardzie,
- dodano ekran ładowania z logo ALO przy uruchamianiu,
- przyspieszono grupowanie potencjalnych duplikatów oraz ograniczono zbędne zapisy dostępności plików,
- usunięto natywny obrys aktywnej komórki w tabeli Biblioteki — pozostaje czytelne zaznaczenie całego wiersza,
- przycisk tworzenia playlisty pokazuje teraz format **Utwórz playlistę (.m3u8)**,
- poprawiono stabilność odtwarzacza i bezpieczne przekazywanie wyniku pracy z wątku roboczego do interfejsu.

## v0.4.11

- dopracowano czytelność Biblioteki i legendę statusów,
- zachowano ręczne decyzje dla duplikatów oraz ich widoczność po rozstrzygnięciu,
- poprawiono fokus komórek tabeli i spójność statusu `NIE WYBIERAM`,
- przygotowano proces budowania wydań Windows: EXE, Portable ZIP, instalator per-user i SHA-256.

## v0.4.10

- Biblioteka zachowuje sortowanie, filtry, zaznaczenie, przewijanie i szerokości kolumn podczas odświeżania,
- uproszczono prezentację decyzji w Duplikatach,
- powiększono i uporządkowano główny panel sterowania odtwarzaczem.

## v0.4.9

- uporządkowano prezentację decyzji w Duplikatach,
- rozdzielono techniczny status pliku od decyzji użytkownika.

## v0.4.8

- poprawiono pierwszy wybór języka i układ Biblioteki,
- dodano wygodniejszą blokadę ponownego rozpoznawania online,
- przebudowano bezpieczne zarządzanie dodatkowymi bibliotekami.

## v0.4.7

- dodano blokadę całego utworu przed ponownym rozpoznaniem przez AcoustID, MusicBrainz i Discogs,
- zablokowane utwory nadal można edytować ręcznie,
- zablokowane pozycje są oznaczane ikoną kłódki.

## v0.4.6

- uproszczono ekran Start i górny workflow,
- uporządkowano historię skanów,
- pliki wynikowe mają czyszczone pola Track Number i Disc Number.

## v0.4.5

- przebudowano Duplikaty na porównanie danych bez automatycznego rekomendowania zwycięzcy,
- dodano informacyjne rodziny wersji utworów,
- dopracowano folder docelowy biblioteki i podgląd konfliktów przed eksportem.

## v0.4.4

- ujednolicono stan wymagający uwagi jako `DO SPRAWDZENIA`,
- rozdzielono zaznaczanie utworu od jego odtwarzania,
- dodano status `TERAZ GRA` i kolejkę **Odtwórz jako następny**.

## v0.4.3

- dodano wybór języka przy pierwszym uruchomieniu,
- dodano bezpieczny reset ALO bez usuwania muzyki,
- pełna synchronizacja usuwa z indeksu rekordy plików, których nie ma już na dysku.
