import sys

if len(sys.argv) > 1 and sys.argv[1] == '--waveform-worker':
    # The frozen EXE can decode in a child process without starting Qt or GUI.
    from audio_library_organizer.audio.waveform_worker import main
    raise SystemExit(main(sys.argv[2:]))

from audio_library_organizer.main import main

raise SystemExit(main())
