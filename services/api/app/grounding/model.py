"""What an extraction is. docs/design/grounding.md §3."""

from dataclasses import dataclass
from enum import StrEnum

from app.characters.sex import Sex
from app.llm import Usage
from app.script import Span


class EntityKind(StrEnum):
    CHARACTER = "character"
    PROP = "prop"
    LOCATION = "location"


class Source(StrEnum):
    MODEL = "model"  # proposed by the model, then grounded
    CUE = "cue"  # a speaking character the model missed, from the parser's dialogue cues
    HEADING = "heading"  # a location, from the parser's scene headings


class ExtractionError(RuntimeError):
    """The extraction can't be completed; no partial result is returned.

    `scene` is the number of the first scene in the chunk that failed, as the script prints it;
    None only when the script is over the chunk budget and no call was made (web.md §4.1)."""

    def __init__(self, message: str, *, scene: str | None = None) -> None:
        super().__init__(message)
        self.scene = scene


@dataclass(frozen=True)
class Quote:
    """The model's quote, and the element (or heading) it was found inside."""

    text: str
    scene_index: int
    span: Span


@dataclass(frozen=True)
class Entity:
    kind: EntityKind
    name: str
    quotes: tuple[Quote, ...]
    scenes: tuple[int, ...]
    source: Source
    # T051, grounding.md §3: the script's word for an animal character; other names it gives.
    species: str | None = None
    other_names: tuple[str, ...] = ()
    # T082, grounding.md §3: the sex a copied sex_word gives, and the quote it sits in.
    sex: Sex | None = None
    sex_quote: Quote | None = None


@dataclass(frozen=True)
class Dropped:
    name: str
    kind: EntityKind
    reason: str


@dataclass(frozen=True)
class GroundingReport:
    entities_proposed: int
    entities_grounded: int
    faithfulness: float
    quotes_proposed: int
    quotes_located: int
    dropped: tuple[Dropped, ...]
    cues_total: int
    cues_found_by_model: int
    recall: float


@dataclass(frozen=True)
class Extraction:
    entities: tuple[Entity, ...]
    report: GroundingReport
    models: tuple[str, ...]
    usage: Usage
