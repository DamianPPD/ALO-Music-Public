"""Read-only presentation of the backend's physical-file knowledge.

Colors describe the last confirmed observation. They never grant read/write
permission; each operation still goes through the existing read resolver.
"""
from dataclasses import dataclass

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
        return FileStatePresentation()
    color = FILE_STATE_COLORS[evaluation.state]
    return FileStatePresentation(evaluation.state, color.label, color.accent, color.background,
                                 evaluation.is_confirmed)


def index_file_state_presentations(context):
    """One pass per snapshot, preserving the refusal of duplicate facts."""
    result = {}
    if context is not None:
        for facts in context.facts:
            result[facts.track_id] = (FileStatePresentation() if facts.track_id in result
                                     else presentation_from_evaluation(evaluate_file_state(facts)))
    return result
