HELP_TOPICS = {
    'Pierwsze uruchomienie': '''
<h2>Bezpieczny start</h2>
<p>Dodaj jeden lub wiele folderów źródłowych. Następnie wskaż miejsce dla nowej biblioteki i wpisz jej nazwę. Program sam utworzy podfoldery <b>GOTOWE</b>, <b>NIE_WYBRANE</b>, <b>DO_SPRAWDZENIA</b> oraz <b>raporty</b>.</p>
<p>Folderów źródłowych nie trzeba wcześniej porządkować. Mogą zawierać podfoldery, różne nazwy i pliki o niepełnych metadanych.</p>
''',
    'Bezpieczeństwo plików': '''
<h2>Oryginały pozostają nietknięte</h2>
<p>Program traktuje źródła jako materiał tylko do odczytu. Nie zmienia nazw, nie nadpisuje tagów i nie usuwa oryginalnych plików. Zmiana nazwy, tagów oraz okładki wykonywana jest dopiero na kopii w nowej bibliotece.</p>
<ul><li>brak automatycznego kasowania,</li><li>brak transkodowania audio,</li><li>brak nadpisywania konfliktów nazw,</li><li>zbiorcze kopiowanie wymaga potwierdzenia.</li></ul>
''',
    'Duplikaty': '''
<h2>Duplikaty — tabela danych, decyzja należy do Ciebie</h2>
<p>ALO Music traktuje grupę duplikatów jako <b>pliki podejrzane o bycie tym samym nagraniem</b>. Program pokazuje w tabeli m.in. nazwę pliku, długość, BPM, format, bitrate, częstotliwość próbkowania i rozmiar. Różniące się wartości są wyróżniane, ale ALO <b>nie rekomenduje zwycięzcy</b>.</p>
<h3>Jak rozstrzygać grupę</h3>
<ol><li>Kliknij wiersz, aby zaznaczyć wariant; dwuklik uruchamia jego odsłuch.</li><li>Dla każdego pliku wybierz <b>ZACHOWAJ</b> albo <b>NIE WYBIERAM</b>.</li><li>Jeśli trzeba, kliknij <b>EDYTUJ</b> i popraw dane bez opuszczania zakładki Duplikaty.</li><li>Kolor decyzji jest pokazany tylko w kolumnie <b>Decyzja</b>: ZACHOWAJ ma zielone tło, a NIE WYBIERAM jest pokazane na szaro. Nierozstrzygnięta decyzja pozostaje na zwykłym ciemnym tle.</li></ol>
<h3>Rodzina wersji utworu</h3>
<p>Radio Edit, Extended Mix, Original Mix, Club Mix i remix mogą być poprawnymi, osobnymi wersjami tego samego utworu. ALO grupuje wyraźnie nazwane wersje w <b>rodzinę wersji</b> i nie traktuje ich automatycznie jako duplikatów, gdy dane wskazują na rzeczywiście inną wersję.</p>
<p><b>Ważne:</b> dane służą do porównania — o zachowaniu lub odłożeniu pliku zawsze decydujesz Ty.</p>
''',
    'Jak program podejmuje decyzje': '''
<h2>Nie jest to „pierwszy wynik z internetu”</h2>
<p>Każdy kandydat dostaje wynik pewności. Program bierze pod uwagę fingerprint AcoustID, dokładnego wykonawcę i tytuł, nazwę remixu/wersji, długość, istniejący album i rok oraz zgodność MusicBrainz z konkretnym Discogs Release.</p>
<p>W panelu szczegółów widzisz procent pewności oraz powody, np. <i>AcoustID 98% · dokładny tytuł/wersja · długość zgodna · album zgodny</i>. Przy zbyt małej pewności plik trafia do <b>DO_SPRAWDZENIA</b>.</p>
''',
    'Rozpoznawanie utworów': '''
<h2>Źródła danych</h2>
<p><b>MusicBrainz</b> i katalog <b>Apple / iTunes</b> działają bez kluczy API. MusicBrainz pomaga potwierdzić nagranie, a Apple/iTunes dostarcza dodatkowe dane katalogowe oraz propozycje okładek. <b>AcoustID/Chromaprint</b> (opcjonalny klucz) rozpoznaje sam dźwięk, również dla nazw typu <code>34.mp3</code>. <b>Discogs</b> (opcjonalny token) pomaga przy dokładnym wydaniu, nazwie remixu, gatunku i roku.</p>
<p>ALO porównuje kilka źródeł i nie powinno wybierać pierwszego wyniku w ciemno. Dokładna wersja/remix, długość i istniejące dane utworu mają znaczenie przy ocenie dopasowania.</p>
''',
    'Konfiguracja AcoustID i Discogs': '''
<h2>Klucze do rozpoznawania online</h2>
<p>Wszystko ustawiasz w <b>Ustawienia → Integracje i klucze API</b>. Do podstawowego rozpoznawania nie musisz wpisywać żadnego klucza: MusicBrainz oraz Apple/iTunes działają od razu. AcoustID i Discogs są opcjonalnymi rozszerzeniami.</p>
<div class="help-card">
<h3>1. AcoustID — Application API Key</h3>
<p><b>Do czego:</b> rozpoznawanie nagrania po fingerprint, także gdy plik ma nazwę typu <code>34.mp3</code>.</p>
<ol><li>Otwórz <a href="https://acoustid.org/new-application">acoustid.org/new-application</a> i zaloguj się.</li><li>Zarejestruj aplikację, np. <b>Audio Library Organizer</b>.</li><li>Skopiuj <b>Application API Key / client key</b>.</li><li>W ALO Music wklej go do pola <b>AcoustID client key</b>.</li></ol>
</div>
<div class="help-card">
<h3>2. Discogs — Personal Access Token</h3>
<p><b>Do czego:</b> dokładne wydanie, remix / wersja, rok, gatunek i dane release.</p>
<ol><li>Zaloguj się do Discogs.</li><li>Otwórz <a href="https://www.discogs.com/settings/developers">Settings → Developers</a>.</li><li>Wygeneruj i skopiuj <b>Personal Access Token</b>.</li><li>W ALO Music wklej go do pola <b>Discogs token</b>.</li></ol>
</div>
<div class="help-card">
<h3>3. MusicBrainz — bez klucza API</h3>
<p>MusicBrainz <b>nie wymaga</b> osobnego klucza do zwykłego odczytu i jest gotowy od razu po instalacji.</p>
</div>
<div class="help-card">
<h3>4. Apple / iTunes — bez klucza API</h3>
<p>ALO korzysta z publicznego katalogu wyszukiwania Apple do dodatkowego potwierdzania utworu, albumu, roku, gatunku i propozycji okładek. Nie musisz logować się do Apple Music.</p>
</div>
<div class="ok"><b>Na końcu:</b> klucze AcoustID / Discogs zapisuj tylko wtedy, gdy chcesz używać tych dodatkowych źródeł. Pozostają w lokalnych ustawieniach użytkownika i nie trafiają do raportów CSV.</div>
<div class="important"><b>Ważne:</b> nie wysyłaj ani nie udostępniaj swoich kluczy w wiadomościach. Dla AcoustID potrzebny jest <b>Application API Key</b>, a dla Discogs <b>Personal Access Token</b>.</div>
<p style="color:#9eabbc">This application uses Discogs’ API but is not affiliated with, sponsored or endorsed by Discogs. “Discogs” is a trademark of Zink Media, LLC.</p>
''',
    'BPM': '''
<h2>Tempo liczone lokalnie</h2>
<p>Jeśli plik ma już BPM w tagu, program go zachowuje. Jeżeli tagu nie ma, ale nazwa zawiera jawne <b>[139bpm]</b>, ta wartość ma pierwszeństwo przed analizą audio. Dopiero gdy nie ma żadnej jawnej wartości, tempo jest obliczane lokalnie z dźwięku.</p>
<p>Analiza uwzględnia typowy problem połowy/podwójnego tempa spotykany w muzyce klubowej, ale w przypadku niepewności nie powinna zastępować sprawdzonych danych użytkownika.</p>
''',
    'Okładki': '''
<h2>Automatyczna okładka bez ręcznego wybierania</h2>
<p>Jeśli wydanie jest odpowiednio pewne, program pobiera okładkę automatycznie. Dla trwałego osadzania grafiki preferowany jest Cover Art Archive powiązany z MusicBrainz. Jeżeli nie ma wystarczająco pewnego dopasowania, losowa okładka nie jest dodawana.</p>
<p>W edytorze widzisz większy podgląd wybranej okładki oraz kompaktową galerię wszystkich dostępnych propozycji z różnych źródeł. Możesz też dodać własny plik albo pozostawić wspólny placeholder <b>BRAK OKŁADKI</b>. Wybraną grafikę ALO zapisuje do pliku wynikowego.</p>
''',
    'Statusy i zatwierdzanie': '''
<h2>Cztery proste statusy</h2>
<p><b>GOTOWE</b> — komplet głównych danych. <b>DUPLIKAT</b> — plik oznaczony jako duplikat. <b>DO SPRAWDZENIA</b> — brakuje głównych danych lub utwór wymaga kontroli. <b>NIE WYBIERAM</b> — plik świadomie odłożony przez użytkownika.</p>
<p>Nie zatwierdzasz kilku tysięcy plików jeden po drugim. W edytorze mały panel <b>Status pliku</b> pokazuje przy każdym kluczowym polu, co jest uzupełnione, a co wymaga uwagi. Status GOTOWE wymaga danych głównych: wykonawcy, tytułu/wersji, roku, gatunku i BPM. Album, Discogs URL oraz komentarz są dodatkowe i ich brak nie blokuje GOTOWE.</p>
''',
    'Odtwarzacz': '''
<h2>Odsłuch bez wychodzenia z aplikacji</h2>
<p>Wbudowany player ma Play/Pause, przewijanie, głośność oraz skoki ±10 sekund. W Bibliotece pojedynczy klik tylko zaznacza utwór, a dwuklik rozpoczyna odtwarzanie. Zmiana zaznaczenia nie przerywa aktualnie grającego utworu.</p>
<p>W Duplikatach każdy plik ma trzy proste akcje: <b>ZACHOWAJ</b>, <b>NIE WYBIERAM</b> oraz <b>EDYTUJ</b>. Jeśli plik okaże się Radio Edit, Extended Mix albo remixem, popraw jego metadane przez EDYTUJ i zachowaj go jak normalny utwór. <b>DUPLIKAT</b> jest automatycznym stanem technicznym programu, nie osobnym przyciskiem.</p>
''',

    'Format nazwy pliku': '''
<h2>Format nazwy pliku</h2>
<p>W <b>Ustawieniach</b> możesz zdecydować, jakie informacje mają znaleźć się w nazwie gotowego pliku. Domyślny szablon to:</p>
<p><code>{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]</code></p>
<h3>Dostępne pola</h3>
<ul><li><code>{Artist}</code> — wykonawca,</li><li><code>{Title}</code> — tytuł bez wersji,</li><li><code>{Version}</code> — remix / edit / mix,</li><li><code>{Year}</code> — rok,</li><li><code>{BPM}</code> — tempo,</li><li><code>{Genre}</code> — gatunek,</li><li><code>{Album}</code> — album / wydanie.</li></ul>
<p>Pod szablonem od razu widzisz <b>podgląd nazwy wynikowej</b>. Jeżeli opcjonalnego pola brakuje, ALO Music usuwa także puste nawiasy lub nawiasy kwadratowe.</p>
<h3>Wyjątek dla jednego utworu</h3>
<p>W edytorze metadanych możesz wpisać własną nazwę tylko dla bieżącego utworu. Nie zmienia to globalnego szablonu dla reszty biblioteki.</p>
''',
    'DO SPRAWDZENIA i cofanie zmian': '''
<h2>Jedna kolejka wymagająca uwagi</h2>
<p>ALO Music używa jednego statusu <b>DO SPRAWDZENIA</b> dla utworów, które wymagają kontroli: brak danych głównych, niska pewność rozpoznania, konflikt danych lub problem z plikiem. Zwykłe przypadki są pomarańczowe, a naprawdę poważne problemy są wyróżniane na czerwono — tekst statusu pozostaje ten sam.</p>
<p>Ręcznie zatwierdzone, kompletne <b>GOTOWE</b> nie wraca automatycznie do sprawdzania z powodu starego ostrzeżenia. Edytor pokazuje wyraźny aktualny status oraz osobny panel <b>DANE SPRZED ROZPOZNANIA ONLINE</b>, z którego można przywrócić wcześniejsze dane.</p>
''',
    'Ręczne poprawki i blokady': '''
<h2>Twoje poprawki mają pierwszeństwo</h2>
<p>Ręcznie poprawione pola, np. wykonawca, tytuł, rok lub <b>gatunek</b>, mają pierwszeństwo przed późniejszym rozpoznawaniem online. Chronione pole nie jest bez pytania nadpisywane przez Discogs/MusicBrainz.</p>
<p>Blokady pól są zapisywane w trwałej bibliotece i chronią ręczną korektę także po ponownym uruchomieniu programu.</p>
<p>Jeśli chcesz zatrzymać cały utwór w obecnym stanie, w edytorze użyj przełącznika <b>Zablokowane / Zablokuj online</b>. Taki plik jest pomijany przez AcoustID, MusicBrainz, Apple/iTunes i Discogs, ale nadal możesz edytować go ręcznie i w każdej chwili odblokować.</p>
''',
    'Ponowne skanowanie': '''
<h2>Trwała biblioteka i szybkie odświeżanie</h2>
<p>Każda biblioteka ma własną bazę i folder wynikowy. ALO zapisuje <b>historię skanowanych źródeł</b> (ścieżka, ostatni skan, liczba plików), ale sama historia nie uruchamia ponownego skanowania po restarcie. Skanowanie zaczyna się po jawnej akcji użytkownika.</p>
<p>Pełne odświeżenie pozostawia niezmienione pliki bez ponownej analizy i analizuje tylko pliki nowe lub zmienione. Jeśli chcesz dołożyć kolejną partię muzyki, użyj <b>Dodaj utwory do biblioteki</b>; istniejąca biblioteka nie jest ponownie analizowana.</p>
<p>Brakujące pliki są sygnalizowane na Start i ukrywane w normalnym widoku Biblioteki. Po pełnym odświeżeniu nieaktualne rekordy są porządkowane.</p>
''',
    'Rozwiązywanie problemów': '''
<h2>Najczęstsze sytuacje</h2>
<p><b>34.mp3 pozostaje nierozpoznany:</b> sprawdź AcoustID client key i połączenie z internetem. Nie każdy utwór istnieje w bazie fingerprintów.</p>
<p><b>Brak dokładnego wydania:</b> program może znać utwór, ale nie mieć dość dowodów na konkretny Discogs Release. Wtedy pozostawia go do sprawdzenia zamiast zgadywać.</p>
<p><b>Brak okładki:</b> jeśli nie znaleziono grafiki zewnętrznej, ALO Music zachowuje okładkę źródłową, jeśli plik ją miał. Gdy nie ma ani zewnętrznej, ani źródłowej, program osadza wspólną grafikę <b>BRAK OKŁADKI</b>, więc plik wynikowy nie zostaje bez grafiki.</p>
<p><b>Skan został przerwany:</b> możesz uruchomić go ponownie. Zapisana biblioteka pozostaje na dysku, a niezmienione pliki nie wymagają ponownej analizy.</p>
''',
    'Kopiowanie i weryfikacja': '''
<h2>Skąd wiadomo, że kopie naprawdę są w folderze?</h2>
<p>Podczas eksportu program najpierw wykonuje surową kopię i porównuje ją ze źródłem przez <b>SHA-256 oraz rozmiar</b>. Dopiero po tej kontroli zapisuje nowe tagi i okładkę na kopii.</p>
<p>Na końcu sprawdza, czy plik końcowy nadal istnieje i ma poprawny, niezerowy rozmiar. To jest <b>kontrola techniczna kopii</b>, a nie ręczna weryfikacja metadanych. Dlatego przed utworzeniem plików program przypomina o pozycji <b>SPRAWDŹ W BIBLIOTECE</b>. Po operacji zobaczysz wynik kontroli, przycisk <b>Przejdź do Biblioteki</b>, przycisk <b>Otwórz folder biblioteki</b> oraz raport <code>weryfikacja_kopii_....csv</code>.</p>
<p>Plik, który nie przejdzie kontroli, nie jest liczony jako poprawnie zweryfikowany.</p>
''',
    'O programie': '''
<h2>ALO Music — Audio Library Organizer</h2>
<p>Wersja <b>0.4.23</b> · 2026. Lokalny organizator biblioteki muzycznej dla Windows z bezpiecznym kopiowaniem, rozpoznawaniem nagrań, edycją metadanych, tabelą duplikatów, rodzinami wersji, okładkami i BPM.</p>
<p>Biblioteki są trwałe i rozdzielają folder wynikowy od źródeł używanych do skanowania. Historia skanów jest informacyjna; ALO nie uruchamia automatycznie starego źródła tylko dlatego, że było wcześniej skanowane.</p>
'''

}
