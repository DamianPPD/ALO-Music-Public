ALO MUSIC - KONCOWA WALIDACJA WINDOWS 11

1. Rozpakuj CALY ZIP do nowego, lokalnego folderu.
2. Kliknij dwukrotnie URUCHOM-TESTY.cmd (bez administratora).
3. Po zakonczeniu przeslij ZIP wynikow i plik .sha256.txt z folderu wyniki.

Nie potrzeba Pythona, instalacji bibliotek ani polaczenia z internetem.
Nie uzywaj plikow bezposrednio z podgladu ZIP. Podczas testow moga pojawiac
sie i automatycznie zamykac syntetyczne okna ALO. Nie zamykaj ich recznie.
Nie trzeba poruszac mysza ani analizowac okien; to testy logiki/Qt.

Produkt: TREE bea8fc4fbc128fbfd99f2c6c1a3d0b62493844ee, 425 plikow.
CPython 3.11.9 x64, PySide6/Shiboken/Qt 6.10.3, pytest 8.4.2, Mutagen 1.47.0.
Zestaw: 145 istniejacych przypadkow N2 (117 native/integracyjne/fault-injection,
28 modeli protokolu). Nie zmieniono ich asercji ani kodu ALO.
DACL/junction wymagaja odpowiednich warunkow na wlasnych danych syntetycznych.
Gdy brakuje warunkow, przypadek otrzymuje BLOCKED, nie PASS. Historyczne testy
symlink wymagajace dodatkowych uprawnien nie zostaly dodane do tych 145.
FAIL/ERROR/SKIP/crash/timeout zatrzymuje dalsze przypadki i zachowuje dowody.
Windows gate produktu nadal jest OFF. Testowy override dziala tylko w osobnych
procesach diagnostycznych. Paczka nie uruchamia normalnej biblioteki uzytkownika.

Dane testowe powstaja w nowym, losowym katalogu ALO-W11-* w prywatnym TEMP.
Ustawienia sa w osobnych INI; SQLite i MP3 sa syntetyczne. Nie ma automatycznego
skanowania muzyki. Pliki wynikowe sa w nowym podfolderze wyniki obok launchera.
Pozostawione dane syntetyczne nie sa automatycznie usuwane szerokim cleanup.
Eksportowane logi maja zredagowane znane prefiksy sciezek i nazwe komputera.

Jesli preflight odrzuci filesystem, potrzeba lokalnego NTFS, a nie udzialu
sieciowego lub katalogu reparse/OneDrive. Nie zmieniaj zabezpieczen systemu.
STOP/BLOCKED nie jest dowodem uszkodzenia ALO ani zaliczeniem testow.
Wyniki na Twoim Windows 11 pozostaja NOT RUN, dopoki nie uruchomisz paczki.
Szczegoly kontroli gotowej paczki znajduja sie w PACKAGE-VALIDATION.txt.
