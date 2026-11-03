"""The API's response types: web.md §6, one Pydantic model per TypeScript interface and per nested
object, field names identical (a test reads the doc's TypeScript and compares them).

String unions that already exist as domain enums use those enums, so the API can't drift from the
model it describes; they serialise as their values. `Job` and `ProjectSummary` are defined here
with the rest, though their data arrives with T009 and T047. Built by `app/projects/views.py`
(T044) and, for frames and audits, by T047 and T021, which own that data.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.grounding import EntityKind, Source
from app.projects.pipeline import Stage
from app.shots import Framing, Movement
from app.verify.model import Position, Severity, Verdict

type JobState = Literal["queued", "running", "done", "failed"]
type FrameStateView = Literal["rendering", "auditing", "passed", "warned", "withheld", "failed"]


class _View(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Job(_View):
    id: UUID
    state: JobState
    stage: Stage | None
    progress: int
    error: str | None
    updated_at: datetime


class FrameCounts(_View):
    """settled = passed + warned + withheld + failed (web.md §3); active = rendering + auditing."""

    settled: int
    total: int
    withheld: int
    active: int


class ProjectSummary(_View):
    id: UUID
    title: str
    created_at: datetime
    pages: int | None
    scenes: int | None
    shots: int | None
    frames: FrameCounts | None
    job: Job


class SpanRef(_View):
    page: int
    line_start: int
    line_end: int


class QuoteView(_View):
    text: str
    span: SpanRef


class EntityView(_View):
    kind: EntityKind
    name: str
    source: Source
    scenes: list[int]
    quotes: list[QuoteView]


class SceneView(_View):
    index: int
    number: str
    heading: str
    time_of_day: str | None
    time_carried: bool
    elements: int
    shots: int | None


class ReportView(_View):
    faithfulness: float
    entities_proposed: int
    entities_grounded: int
    quotes_proposed: int
    quotes_located: int
    recall: float
    cues_total: int
    cues_found_by_model: int
    models: list[str]
    prompt_tokens: int
    completion_tokens: int


class Project(ProjectSummary):
    scene_list: list[SceneView] | None
    entities: list[EntityView] | None
    report: ReportView | None


class LinesView(_View):
    lines: list[str]
    page_starts: list[int]


class Segment(_View):
    line_start: int
    line_end: int
    cue: str | None
    extension: str | None  # the cue's bracket without its parentheses ("O.S."), T045
    on_screen: bool


class ShotView(_View):
    id: str
    scene_index: int
    number: int
    framing: Framing
    movement: Movement
    characters: list[str]
    props: list[str]
    time_of_day: str | None
    rationale: str
    span: SpanRef
    source: str
    segments: list[Segment]


class CheckView(_View):
    check: str
    severity: Severity
    ok: bool
    detail: str


class DescribedPerson(_View):
    position: Position
    appearance: str


class DescribedObject(_View):
    name: str
    category: str
    held: bool


class DescriptionView(_View):
    people: list[DescribedPerson]
    setting: str
    light: str
    shot_size: str
    objects: list[DescribedObject]
    has_text: bool
    text: list[str] = []  # T071; a row logged before it has none
    signature: bool = False  # T072; likewise
    signature_text: list[str] = []  # T107: the signature's letters; a row before T107 has none


class JudgedPerson(_View):
    person: int
    character: str | None
    support: str | None


class JudgedObject(_View):
    object: int
    kind: str
    support: str | None


class JudgementView(_View):
    people: list[JudgedPerson]
    objects: list[JudgedObject]


class AuditView(_View):
    """One `frame_audits` row (verify.md §6). Built by T021."""

    attempt: int
    seed: int
    verdict: Verdict
    description: DescriptionView | None
    judgement: JudgementView | None
    checks: list[CheckView]
    positions: dict[str, Position]
    models: list[str]
    created_at: datetime


class FrameView(_View):
    """One `frames` row. Built by T047; `image_url` is non-null only when passed or warned."""

    shot_id: str
    state: FrameStateView
    attempt: int
    max_renders: int
    image_url: str | None
    withheld_check: str | None
    failure: Literal["render", "restart"] | None  # T021: why a failed frame failed; null otherwise
    audits: list[AuditView]

    @model_validator(mode="after")
    def _image_only_when_accepted(self) -> FrameView:
        # web.md §4.3: no frame is shown outside passed/warned; refuse to build one that would be.
        if self.image_url is not None and self.state not in ("passed", "warned"):
            raise ValueError("image_url is sent only for passed or warned frames")
        if self.failure is not None and self.state != "failed":
            raise ValueError("failure is sent only for failed frames")
        return self


class StoryboardPdfView(_View):
    """GET /projects/{id}/storyboard/pdf (T027): a signed URL to the PDF, valid an hour."""

    pdf_url: str


# --- the comic (web.md §6 comic types; comic.md §4a; T064) ------------------------------------

type LetteringKind = Literal["speech", "off_panel", "voice_over", "scene"]
type Rect = tuple[int, int, int, int]  # x, y, w, h in page px


class LetteringView(_View):
    """One bubble or caption of a panel, verbatim from the script, with its span."""

    kind: LetteringKind
    speaker: str | None
    cue: str | None
    text: str
    span: SpanRef
    rect: Rect


class ComicPanelView(_View):
    shot_id: str
    rect: Rect
    withheld: bool
    lettering: list[LetteringView]


class ComicPageView(_View):
    number: int
    width: int
    height: int
    image_url: str
    panels: list[ComicPanelView]


class ComicMade(_View):
    """The last finished comic: its pages and PDF, signed at read time."""

    made_at: datetime
    pdf_url: str
    pages: list[ComicPageView]


class ComicView(_View):
    """GET /projects/{id}/comic. Built by `app/comic/views.py`."""

    can_make: bool
    shots: int
    job: Job | None
    comic: ComicMade | None
