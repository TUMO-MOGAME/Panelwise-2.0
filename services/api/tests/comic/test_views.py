"""T064: `comic_view` (web.md §6 ComicView; comic.md §6). Pure: a hand-built layout, no database."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.comic.job import COMIC_RESTARTED
from app.comic.rows import ComicRow
from app.comic.views import comic_view
from app.jobs import JobKind, JobRow, JobState
from app.jobs.model import RESTARTED
from app.projects.codec import dump_screenplay
from app.projects.model import ProjectRow
from app.script import Action, Dialogue, IntExt, Scene, Screenplay, Span

NOW = datetime(2026, 10, 9, 14, 20, tzinfo=UTC)


def span(line: int) -> dict[str, int]:
    return {"page": 1, "line_start": line, "line_end": line}


SCREENPLAY = Screenplay(
    "",
    1,
    (
        Scene(
            0,
            "7",
            "EXT. HARBOUR - NIGHT",
            IntExt.EXT,
            "HARBOUR",
            "NIGHT",
            (
                Dialogue("NANDI", None, None, "You came back.", Span(1, 3, 3)),
                Dialogue("THABO", "V.O.", None, "I never left.", Span(1, 5, 5)),
                Action("Rain.", Span(1, 6, 6)),
                Dialogue("THABO", "O.S.", None, "Open the door.", Span(1, 8, 8)),
            ),
            Span(1, 1, 1),
        ),
    ),
    (1,),
)

# A panel whose JSON lists bubbles before captions and the bubbles out of element order: the view
# must read scene caption, then element 0, 1 (the voice-over caption), 3.
PANEL: dict[str, Any] = {
    "shot": [0, 2],
    "rect": [120, 120, 1748, 986],
    "frame_url": "frames/a.png",
    "withheld": False,
    "bubbles": [
        {"kind": "off_panel", "speaker": "THABO", "text": "Open the door.", "element": 3,
         "span": span(8), "rect": [1, 2, 3, 4], "tail": [9, 9], "font_px": 32},
        {"kind": "speech", "speaker": "NANDI", "text": "You came back.", "element": 0,
         "span": span(3), "rect": [5, 6, 7, 8], "tail": None, "font_px": 32},
    ],
    "captions": [
        {"kind": "voice_over", "text": "I never left.", "element": 1, "span": span(5),
         "rect": [9, 10, 11, 12], "font_px": 32},
        {"kind": "scene", "text": "HARBOUR — NIGHT", "element": None, "span": span(1),
         "rect": [13, 14, 15, 16], "font_px": 32},
    ],
}  # fmt: skip


def project() -> ProjectRow:
    return ProjectRow(
        id=uuid.uuid4(), owner=uuid.uuid4(), title="t", pdf_path="p",
        screenplay=dump_screenplay(SCREENPLAY), plan=None,
    )  # fmt: skip


def comic_row(project_id: uuid.UUID) -> ComicRow:
    layout = {"pages": [{"number": 1, "width": 1988, "height": 3075, "panels": [PANEL]}]}
    return ComicRow(
        project_id=project_id, job_id=uuid.uuid4(), layout=layout, pages=["comics/p1.png"],
        pdf="comics/c.pdf", made_at=NOW,
    )  # fmt: skip


def job(error: str | None, state: JobState = JobState.FAILED) -> JobRow:
    return JobRow(
        id=uuid.uuid4(), project_id=uuid.uuid4(), kind=JobKind.COMIC, state=state,
        stage="rendering", progress=40, error=error, updated_at=NOW,
    )  # fmt: skip


def test_lettering_reads_the_scene_caption_then_every_line_in_element_order() -> None:
    p = project()
    view = comic_view(p, None, comic_row(p.id), ["https://s/p1"], "https://s/c", can_make=True)
    assert view.comic is not None
    (page,) = view.comic.pages
    (panel,) = page.panels
    assert (panel.shot_id, panel.rect, panel.withheld) == ("7.2", (120, 120, 1748, 986), False)
    assert [(item.kind, item.text) for item in panel.lettering] == [
        ("scene", "HARBOUR — NIGHT"),
        ("speech", "You came back."),
        ("voice_over", "I never left."),
        ("off_panel", "Open the door."),
    ]
    # The cue as the script prints it; the speaker bare; a scene caption has neither.
    assert [(item.speaker, item.cue) for item in panel.lettering] == [
        (None, None),
        ("NANDI", "NANDI"),
        ("THABO", "THABO (V.O.)"),
        ("THABO", "THABO (O.S.)"),
    ]
    assert panel.lettering[3].span.line_start == 8
    assert (page.image_url, view.comic.pdf_url, view.comic.made_at) == (
        "https://s/p1",
        "https://s/c",
        NOW,
    )


def test_a_restart_reads_as_make_it_again_and_other_errors_verbatim() -> None:
    p = project()
    restarted = comic_view(p, job(RESTARTED), None, [], None, can_make=False).job
    other = comic_view(p, job("A panel couldn't be drawn, so the comic stopped."), None, [], None,
                       can_make=False).job  # fmt: skip
    assert restarted is not None and restarted.error == COMIC_RESTARTED
    assert other is not None and other.error == "A panel couldn't be drawn, so the comic stopped."


def test_no_comic_and_no_plan_reads_empty() -> None:
    view = comic_view(project(), None, None, [], None, can_make=False)
    assert (view.can_make, view.shots, view.job, view.comic) == (False, 0, None, None)


def test_every_page_needs_its_signed_url() -> None:
    p = project()
    with pytest.raises(ValueError, match="every page"):
        comic_view(p, None, comic_row(p.id), [], "https://s/c", can_make=True)
