# Diagnostyka sporadycznego zamknięcia aplikacji na Windowsie

Aktualnego crusha nie odtworzono w runtime Linux/Qt. Ta zmiana dodaje
diagnostykę i testy; nie potwierdza naprawy crusha na Windowsie.

## Zebranie następnego wystąpienia

Uruchom aktualny `v0.4.25-dev` zwykłym sposobem. Na Windowsie diagnostyka
włącza się automatycznie przed importami GUI. Odtwórz dotychczasową pracę
w Bibliotece: pojedyncze kliknięcia, szybkie zmiany, odtwarzanie i stop.

Pliki są zapisywane w `%LOCALAPPDATA%\ALO Music\`:

- `alo_crash_debug.log`: wybór i szczegóły utworu, żądanie playbacku,
  ustawienie źródła playera, media/playback state, błędy, stworzenie/start/
  anulowanie/zakończenie zadania, emit i odrzucenie starego wyniku;
  również fatalny Python stack procesu GUI z `faulthandler`;
- `alo_crash_debug.waveform.log`: fazy dekodera w osobnym procesie,
  `SoundFile` open/read/close, wersje soundfile/libsndfile i jego fatalny stack.

Zachowaj oba pliki po nagłym zamknięciu aplikacji, przed kolejnymi próbami.
Log jest dopisywany przy kolejnych uruchomieniach. Jeśli przed startem ma
co najmniej 5 MiB, poprzednia zawartość przechodzi do pliku `.previous.log`.
Nie ma rotacji podczas pracy, aby deskryptor `faulthandler` pozostawał ważny.

Każde zdarzenie zawiera czas UTC, czas monotoniczny, PID i native thread ID.
Ścieżka utworu ma stabilne ID wyliczone z kanonicznej ścieżki; to identyfikator
ścieżki, nie hash zawartości audio. ID zadania łączy ID playera z generacją.
`job.start`/`job.finished` zawierają liczbę faktycznie działających zadań.
ID zadania łączy log GUI z logiem dekodera. Read jest podsumowany, bez
osobnej linii dla każdego bloku próbek.

Logi zawierają lokalne ścieżki. Diagnostyka niczego nie wysyła.

## Sterowanie diagnostyką

Zmienne środowiskowe ustawione przed uruchomieniem programu:

- `ALO_CRASH_DEBUG=0`: wyłącza tę diagnostykę;
- `ALO_CRASH_DEBUG=1`: włącza ją także na Linuxie;
- `ALO_CRASH_DEBUG_LOG=C:\wybrany-folder\alo_crash_debug.log`: zmienia
  lokalizację; waveform dostaje sąsiedni plik `alo_crash_debug.waveform.log`.

Błąd otwarcia logu nie blokuje aplikacji. Jeśli trwały log waveformu jest
niedostępny, dekoder korzysta ze zwykłego pliku tymczasowego. Błąd zapisu
diagnostyki nie jest traktowany jako naprawa ani jako błąd audio.

## Wynik analizy i testów

Poprzedni Windows stack wskazywał `SoundFile.read()` wywoływany w GUI
przez `WaveformJob`. W aktualnym kodzie waveform już odczytuje plik
w izolowanym procesie, pojedynczo. Anulowanie zabija i zbiera ten proces
przed uruchomieniem następnego. `SoundFile` i bufory NumPy należą tylko
do dekodera; do GUI wraca JSON z liczbami, kopiowany do slidera.
`QMediaPlayer` nadal używa natywnego backendu w procesie GUI.

Pojedynczy wybór w Bibliotece aktualizuje szczegóły i okładkę. Dopiero
żądanie playbacku uruchamia player i waveform. Ostatnie zmiany wizualne
nie zmieniły implementacji playera ani waveformu względem commitu
`fa46b5b`; względem taga `v0.4.24` istotną zmianą waveformu była jego
wcześniejsza izolacja procesowa.

Hipoteza: wynik zakolejkowany przed zniszczeniem playera trafia do
usuniętego widgetu. Minimalny test kończy worker bez przetwarzania GUI
events, usuwa receiver, dopiero potem przetwarza events. Callback nie
dociera do usuniętego widgetu, więc test nie potwierdził tej hipotezy.
Nie ustalono, czy aktualny Windows crash dotyczy bufora, SoundFile,
Qt media backendu, lifetime czy innego natywnego zasobu.

Test stress używa rzeczywistego `QMediaPlayer` i dekoderów: 100 pojedynczych
wyborów bez playbacku, 100 zmian z ukończonym waveformem, 100 szybkich
zmian z playbackiem, play/stop oraz zniszczenie receivera z nowym zadaniem.
Sprawdza WAV, FLAC, MP3 i M4A, jeśli dostępny jest encoder ffmpeg,
krótkie pliki, 120-sekundowy WAV i 6-kanałowy WAV 96 kHz. Obejmuje
zbieranie procesów, zwalnianie jobów/signals, zero aktywnych zadań na
końcu i brak akceptacji wyników ze starej generacji. Na Linuxie bez
urządzenia audio sprawdza lifecycle backendu, nie słyszalny odsłuch.
