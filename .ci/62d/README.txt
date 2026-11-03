ALO MUSIC — WINDOWS 11 / KONTYNUACJA OD PRZYPADKU 39

1. Rozpakuj CALY ZIP do nowego lokalnego folderu na NTFS.
2. Kliknij URUCHOM-TESTY.cmd. Bez administratora, instalacji i internetu.
3. Przeslij nowy ZIP wynikow i jego .sha256.txt z podfolderu wyniki.

Paczka wykonuje tylko EN39 oraz 106 pozostalych przypadkow: 107 wybranych.
Nie powtarza poprzednich 38 PASS. Wyniki historyczne BEA8 sa opisane osobno;
nie sa dodawane do nowych PASS. Wszystkie pierwotne asercje pozostaly bez zmian.

EN39 ma obserwacje testu, rzeczywistego MainWindow/Qt, SQLite, ochrony pary,
sygnalow workera, odswiezania tabeli oraz zamykania okna i watku.
Obserwator NIE ustawia wynikow, nie zamyka dialogow i nie podmienia Slot.
Po 150 s zapisze stosy Pythonowych watkow. Watchdog pozostaje na 180 s.
Przy timeoutie zapisze procesy tylko w prywatnym JobObject i dowod reaping.
Nie ma skanowania procesow innych aplikacji ani zrzutu prywatnego pulpitu.

Jesli EN ponownie dostanie TIMEOUT, ERROR zostaje zachowany. Pozostale 106
moze ruszyc tylko po potwierdzonym zamknieciu JobObject/reap, integralnosci
oraz braku bledow callback/Qt/izolacji. Nie oznacza to naprawy EN ani PASS.
Inny FAIL/ERROR/SKIP/crash zatrzymuje dalszy przebieg i zachowuje dowody.
Brak bezpiecznych warunkow DACL/junction oznacza BLOCKED, nie PASS.

Wyniki zawsze sa w nowym, osobnym podfolderze wyniki:
ALO-Music-Windows11-WYNIKI-KONTYNUACJA.zip
ALO-Music-Windows11-WYNIKI-KONTYNUACJA.zip.sha256.txt
Okno pozostaje otwarte do nacisniecia klawisza.

Produkt BEA8 / 425 plikow pozostaje niezmieniony:
bea8fc4fbc128fbfd99f2c6c1a3d0b62493844ee
Prywatny CPython3.11.9 x64 i komplet dotychczasowych zaleznosci Qt6.10.3/FFmpeg.
Brak pobierania runtime, pip ani bibliotek podczas testu. Bramka Windows OFF.
Testowy override wystepuje tylko w dotychczasowych izolowanych testach.

Wylacznie nowe syntetyczne MP3/SQLite/INI/TEMP. Nie otwiera rzeczywistej
Biblioteki, nie skanuje muzyki, nie eksportuje prywatnych danych, nie zmienia
rejestru ani globalnych zabezpieczen. Testowe okna moga pojawiac sie i zamykac.
Nie zamykaj ich recznie. Nie potrzeba poruszania mysza.
Logi eksportowane maja zredagowane znane prefiksy sciezek. Nie dolacza MP3/SQLite.

Przyczyna pierwotnego timeoutu Windows11 pozostaje NIEUSTALONA do pomiaru.
Paczka ma zebrac rozstrzygajace punkty kontrolne, a nie ukryc ten wynik.
Natywny test na WindowsServer2022 nie oznacza Windows11 PASS.
