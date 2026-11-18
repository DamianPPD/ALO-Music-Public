"""Read-only presentation of the backend's physical-file knowledge.

Colors describe the last confirmed observation. They never grant read/write
permission; each operation still goes through the existing read resolver.
"""
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib

from audio_library_organizer.domain.file_state import FileState, evaluate_file_state


@dataclass(frozen=True)
class FileStateColor:
    label: str
    accent: str
    background: str | None


FILE_STATE_COLORS = {
    FileState.IN_LIBRARY: FileStateColor('W bibliotece', '#6dcda0', '#142b23'),
    FileState.SOURCE_ONLY: FileStateColor('Tylko źródło', '#66aaf0', '#142235'),
    FileState.NEEDS_UPDATE: FileStateColor('Do aktualizacji', '#e5ad70', '#30251b'),
    FileState.SOURCE_UNAVAILABLE: FileStateColor('Źródło niedostępne', '#f08b96', '#351b24'),
    FileState.MANAGED_FILE_MISSING: FileStateColor('Brak pliku biblioteki', '#d8c56e', '#302b18'),
    FileState.CONFLICT: FileStateColor('Konflikt', '#db8fd4', '#302036'),
}

# The established dropdown/display order, not evaluator precedence or PL/EN text.
FILE_STATE_SORT_ORDER = {state: rank for rank, state in enumerate(FILE_STATE_COLORS)}


@dataclass(frozen=True)
class FileStatePresentation:
    state: FileState | None = None
    label: str = 'Stan pliku niepotwierdzony'
    accent: str | None = None
    background: str | None = None
    confirmed: bool = False
    last_confirmed_at: int | None = None
    reason: str = ''


def file_state_presentation(track, context, evaluation=None) -> FileStatePresentation:
    if context is None or not track.track_id:
        return FileStatePresentation()
    if evaluation is None:
        facts = [f for f in context.facts if f.track_id == track.track_id]
        if len(facts) != 1:
            return FileStatePresentation()
        evaluation = evaluate_file_state(facts[0])
    return presentation_from_evaluation(evaluation)


def presentation_from_evaluation(evaluation) -> FileStatePresentation:
    # The repository explicitly invalidates display history after a rebind.
    # A stale cache can describe the last confirmed state, never fresh safety.
    if evaluation.reason == 'TRACK_BINDING_CHANGED' or evaluation.state is None:
        return FileStatePresentation(last_confirmed_at=evaluation.last_confirmed_at, reason=evaluation.reason)
    color = FILE_STATE_COLORS[evaluation.state]
    return FileStatePresentation(evaluation.state, color.label, color.accent, color.background,
                                 evaluation.is_confirmed, evaluation.last_confirmed_at, evaluation.reason)


def index_file_state_presentations(context):
    """One pass per snapshot, preserving the refusal of duplicate facts."""
    result = {}
    if context is not None:
        for facts in context.facts:
            result[facts.track_id] = (FileStatePresentation() if facts.track_id in result
                                     else presentation_from_evaluation(evaluate_file_state(facts)))
    return result


def file_state_owner_revision(context):
    """One pure fingerprint of all owner proofs on a context refresh."""
    return hashlib.sha256(repr(context.managed_bindings).encode('utf-8')).hexdigest()


def file_state_context_key(track, context, *, owners_revision=None):
    """Pure display identity. Never an authorization token for file operations."""
    from audio_library_organizer.jobs.context_menu import frozen_value
    if context is None:
        return None
    if owners_revision is None:
        owners_revision = (file_state_owner_revision(context)
                           if any(b.track_id == track.track_id for b in context.managed_bindings) else '')
    # Legacy availability is a disposable UI/cache flag, not a record binding.
    # FileState observations/watermarks supply their own uncertainty evidence.
    record = replace(track, is_available=True)
    return (context.library_id, context.library_root, frozen_value(record),
            tuple(s for s in context.sources if s.source_id == track.source_id),
            owners_revision)


class FileStateSession:
    """GUI-owned observations, deliberately separate from historical SQLite."""
    def __init__(self):
        self._entries = {}
        self._context = None
        self._owners_revision = ''
        self._owned_ids = frozenset()

    def _key(self, track, context):
        if self._context is not context:
            self._context = context
            self._owners_revision = file_state_owner_revision(context)
            self._owned_ids = frozenset(b.track_id for b in context.managed_bindings)
        return file_state_context_key(track, context,
            owners_revision=self._owners_revision if track.track_id in self._owned_ids else '')

    def remember(self, track, context, evaluation):
        key = (context.library_id, track.track_id)
        previous = self._entries.get(key)
        if previous is not None and previous[2] > evaluation.checked_at:
            return False
        self._entries[key] = (self._key(track, context), evaluation, evaluation.checked_at)
        return True

    def retain_after_cancel(self, track, context, evaluation):
        """Keep a prior proof across an equivalent committed observation.

        Cancellation never creates a confirmation or advances its timestamp.
        The separate observation watermark only prevents the canceled task's
        identical cache row from revoking an earlier completed confirmation.
        """
        key = (context.library_id, track.track_id)
        previous = self._entries.get(key)
        if previous is None:
            return
        binding, current, observed_at = previous
        if (binding != self._key(track, context) or evaluation.checked_at < observed_at
                or not current.is_confirmed or not evaluation.is_confirmed
                or (current.state, current.reason) != (evaluation.state, evaluation.reason)):
            return
        self._entries[key] = (binding, current, evaluation.checked_at)

    def evaluation(self, track, context, historical):
        if context is None:
            return historical
        key = (context.library_id, track.track_id)
        entry = self._entries.get(key)
        if entry is None:
            return historical
        binding, current, observed_at = entry
        if (binding != self._key(track, context)
                or historical.checked_at > observed_at
                or historical.reason == 'TRACK_BINDING_CHANGED'):
            self._entries.pop(key, None)
            return historical
        if historical.checked_at >= current.checked_at and historical.reason != 'CACHE_REQUIRES_REVALIDATION':
            return historical
        return current


_EN_LABELS = {
    FileState.IN_LIBRARY: 'In library', FileState.SOURCE_ONLY: 'Source only',
    FileState.NEEDS_UPDATE: 'Needs update', FileState.SOURCE_UNAVAILABLE: 'Source unavailable',
    FileState.MANAGED_FILE_MISSING: 'Library file missing', FileState.CONFLICT: 'Conflict',
}

_EXPLANATIONS = {
    FileState.IN_LIBRARY: ('Plik wynikowy jest zgodny z potwierdzonym oczekiwanym stanem.',
                           'The output file matches the confirmed expected state.'),
    FileState.SOURCE_ONLY: ('Plik źródłowy jest dostępny; brak przypisanego pliku wynikowego.',
                           'The source file is available; no output file is assigned.'),
    FileState.NEEDS_UPDATE: ('Plik wynikowy istnieje, ale różni się od aktualnie oczekiwanego stanu.',
                            'The output file exists but differs from the currently expected state.'),
    FileState.SOURCE_UNAVAILABLE: ('Nie znaleziono pliku źródłowego w zapisanej lokalizacji.',
                                  'The source file was not found at its saved location.'),
    FileState.MANAGED_FILE_MISSING: ('Przypisany plik wynikowy nie został znaleziony w oczekiwanej lokalizacji.',
                                    'The assigned output file was not found at its expected location.'),
    FileState.CONFLICT: ('Wykryto sprzeczne dowody dotyczące pliku lub jego powiązania.',
                         'Conflicting evidence was found about the file or its binding.'),
}

_REASON_EXPLANATIONS = {
    'AMBIGUOUS_OWNERSHIP': ('Nie można jednoznacznie ustalić właściciela pliku.', 'The file owner cannot be determined unambiguously.'),
    'MULTIPLE_OWNERS': ('Plik jest powiązany z więcej niż jednym utworem.', 'The file is bound to more than one track.'),
    'OWNER_MISMATCH': ('Właściciel pliku nie odpowiada temu utworowi.', 'The file owner does not match this track.'),
    'TARGET_COLLISION': ('Więcej niż jeden plik zajmuje oczekiwaną lokalizację.', 'Multiple files conflict at the expected location.'),
    'CONTRADICTORY_FACTS': ('Dowody tożsamości lub powiązania pliku są sprzeczne.', 'File identity or binding evidence is contradictory.'),
    'TRACK_BINDING_CHANGED': ('Powiązanie utworu zmieniło się; ponów kontrolę.', 'The track binding changed; check again.'),
    'OUTPUT_SNAPSHOT_UNKNOWN': ('Nie potwierdzono pełnego porównania oczekiwanego pliku wynikowego.', 'A complete comparison with the expected output has not been confirmed.'),
    'SOURCE_CONTENT_CHANGED': ('Zawartość źródła różni się od zapisanego powiązania.', 'The source contents differ from the saved binding.'),
    'MANAGED_PRESENT_UNCONFIRMED': ('Przypisany plik wynikowy jest dostępny, ale jego aktualność wymaga potwierdzenia.', 'The assigned output is available, but its current state still needs confirmation.'),
    'OWNERSHIP_UNCONFIRMED': ('Nie potwierdzono jednoznacznej własności przypisanego pliku. Użyj pełnej kontroli Biblioteki.', 'The assigned file ownership has not been confirmed. Use the full Library check.'),
}


def file_state_tooltip(presentation, language='pl'):
    en = language == 'en'
    label = _EN_LABELS.get(presentation.state, 'File state unconfirmed') if en else presentation.label
    lines = [('State: ' if en else 'Stan: ') + label]
    if presentation.last_confirmed_at is not None:
        try:
            stamp = datetime.fromtimestamp(presentation.last_confirmed_at / 1_000_000_000).astimezone()
            lines.append(('Last confirmed: ' if en else 'Ostatnio potwierdzono: ') + stamp.strftime('%d.%m.%Y, %H:%M'))
        except (ValueError, OSError, OverflowError):
            pass
    lines.append(('Confirmed in the current session' if en else 'Potwierdzone w bieżącej sesji')
                 if presentation.confirmed else
                 (('Historical state — check again' if en else 'Stan historyczny — wymaga ponownej kontroli')
                  if presentation.state is not None else
                  ('Unconfirmed state — check again' if en else 'Stan niepotwierdzony — wymaga ponownej kontroli')))
    reason = presentation.reason
    explanation = _REASON_EXPLANATIONS.get(reason)
    if explanation is None and any(word in reason for word in ('OFFLINE', 'UNAVAILABLE')) and not presentation.confirmed:
        explanation = ('Lokalizacja jest niedostępna; nie potwierdzono braku pliku.', 'The location is unavailable; file absence has not been confirmed.')
    if explanation is None and any(word in reason for word in ('ERROR', 'UNREADABLE', 'UNOBSERVED', 'UNCONFIRMED', 'UNKNOWN')) and not presentation.confirmed:
        explanation = ('Nie udało się wiarygodnie sprawdzić pliku; poprzedni stan pozostaje historyczny.', 'The file could not be checked reliably; the previous state remains historical.')
    if explanation is None:
        explanation = _EXPLANATIONS.get(presentation.state)
    if explanation:
        lines.append(explanation[int(en)])
    lines.append('File operations require revalidation.' if en else
                 'Operacje na plikach wymagają ponownej weryfikacji.')
    return '\n'.join(lines)


def track_check_notice(evaluation, language='pl'):
    en = language == 'en'
    if evaluation is None or not evaluation.is_confirmed:
        return ('Could not confirm the track file state.' if en else 'Nie udało się potwierdzić stanu plików utworu.')
    return ('Check complete: ' if en else 'Kontrola zakończona: ') + _EXPLANATIONS[evaluation.state][int(en)]
