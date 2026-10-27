"""Versioned evidence for output fields, distinct from ownership or write rights."""
from dataclasses import dataclass
from enum import StrEnum

NAMESPACE = 'alo.mp3-output-fields'
VERSION = 1
REQUIRED_FIELDS = frozenset(('artist','title','album','year','genre','bpm','comment',
    'track_number','disc_number','discogs_url','cover_sha256','relative_path'))


class FieldAction(StrEnum):
    SET = 'SET'
    PRESERVE = 'PRESERVE'
    REMOVE = 'REMOVE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True, slots=True)
class OutputField:
    name: str
    action: FieldAction
    value: str | None = None

    def __post_init__(self):
        if not self.name or not isinstance(self.action, FieldAction):
            raise ValueError('Invalid output field.')
        if ((self.action == FieldAction.SET and not isinstance(self.value, str))
                or (self.action != FieldAction.SET and self.value is not None)):
            raise ValueError('Output directive/value mismatch.')


@dataclass(frozen=True, slots=True)
class OutputSpec:
    fields: tuple[OutputField, ...]
    namespace: str = NAMESPACE
    version: int = VERSION
    provenance: str = 'desired-writer-policy'

    def __post_init__(self):
        if (not isinstance(self.fields, tuple) or not all(isinstance(f, OutputField) for f in self.fields)
                or len({f.name for f in self.fields}) != len(self.fields)
                or not self.namespace or type(self.version) is not int or self.version < 1):
            raise ValueError('Invalid OutputSpec.')

    def field(self, name):
        return next(f for f in self.fields if f.name == name)

    @property
    def complete(self):
        # A preserve directive is not a resolved resulting value. Historical
        # adoption coverage never becomes a full output specification.
        return (self.namespace == NAMESPACE and self.version == VERSION
                and {f.name for f in self.fields} == REQUIRED_FIELDS
                and self.provenance != 'legacy-adoption-v1-observed'
                and all(f.action in (FieldAction.SET, FieldAction.REMOVE) for f in self.fields))


@dataclass(frozen=True, slots=True)
class FieldDifference:
    field: str
    expected: str
    observed: str

    def __post_init__(self):
        if not self.field or not all(isinstance(v, str) for v in (self.expected, self.observed)) or self.expected == self.observed:
            raise ValueError('A difference requires unequal known values.')


@dataclass(frozen=True, slots=True)
class OutputDifference:
    """Prepared positive evidence, never a partial equality token or authority.

    Producers must validate ownership, physical material and live revisions.
    This transient type is intentionally not written into file_state_cache.
    """
    track_id: str
    checked_at: int
    fields: tuple[FieldDifference, ...]
    namespace: str = NAMESPACE
    version: int = VERSION

    def __post_init__(self):
        if (not self.track_id or type(self.checked_at) is not int or self.checked_at < 0
                or not isinstance(self.fields, tuple) or not self.fields
                or not all(isinstance(d, FieldDifference) for d in self.fields)):
            raise ValueError('Incomplete positive output difference.')


@dataclass(frozen=True, slots=True)
class OutputComparison:
    differences: tuple[FieldDifference, ...] = ()
    complete_match: bool = False

    def as_difference(self, track_id, checked_at):
        return OutputDifference(track_id, checked_at, self.differences) if self.differences else None


def compare_specs(desired: OutputSpec, observed: OutputSpec) -> OutputComparison:
    if ((desired.namespace, desired.version) != (NAMESPACE, VERSION)
            or (observed.namespace, observed.version) != (NAMESPACE, VERSION)):
        return OutputComparison()
    actual = {f.name: f for f in observed.fields}
    differences = []
    comparable = True
    for field in desired.fields:
        other = actual.get(field.name)
        if (other is None or field.action not in (FieldAction.SET, FieldAction.REMOVE)
                or other.action not in (FieldAction.SET, FieldAction.REMOVE)):
            comparable = False
            continue
        want = field.value if field.action == FieldAction.SET else ''
        got = other.value if other.action == FieldAction.SET else ''
        if want != got:
            differences.append(FieldDifference(field.name, want, got))
    return OutputComparison(tuple(differences), bool(desired.complete and observed.complete
        and comparable and set(actual) == {f.name for f in desired.fields} and not differences))
