"""`ComicView` from a project's stored comic (web.md §6; comic.md §6 `comic_view`; T064). Pure: the
route signs the URLs and passes them in."""

from collections.abc import Sequence
from typing import Any

from app.api.v1.schemas import (
    ComicMade,
    ComicPageView,
    ComicPanelView,
    ComicView,
    Job,
    LetteringView,
    SpanRef,
)
from app.comic.job import COMIC_RESTARTED
from app.comic.rows import ComicRow
from app.jobs import JobRow
from app.jobs.model import RESTARTED
from app.projects.codec import load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.script import Dialogue, Screenplay


def comic_job_view(row: JobRow) -> Job:
    # A comic is remade, not re-uploaded: the sweep's copy is read back as the comic's (§4a).
    error = COMIC_RESTARTED if row.error == RESTARTED else row.error
    return Job.model_validate(
        {
            "id": row.id,
            "state": row.state,
            "stage": row.stage,
            "progress": row.progress,
            "error": error,
            "updated_at": row.updated_at,
        }
    )


def _lettering(screenplay: Screenplay, scene_index: int, item: dict[str, Any]) -> LetteringView:
    span = SpanRef.model_validate(item["span"])
    if item["kind"] == "scene":
        return LetteringView(
            kind="scene",
            speaker=None,
            cue=None,
            text=item["text"],
            span=span,
            rect=tuple(item["rect"]),
        )
    element = screenplay.scenes[scene_index].elements[int(item["element"])]
    if not isinstance(element, Dialogue):
        raise ValueError(f"lettering in scene {scene_index} cites a non-dialogue element")
    cue = element.cue if element.extension is None else f"{element.cue} ({element.extension})"
    return LetteringView(
        kind=item["kind"], speaker=element.cue, cue=cue, text=item["text"], span=span,
        rect=tuple(item["rect"]),
    )  # fmt: skip


def _panel(screenplay: Screenplay, panel: dict[str, Any]) -> ComicPanelView:
    scene_index, number = int(panel["shot"][0]), int(panel["shot"][1])
    captions = panel["captions"]
    scene = [c for c in captions if c["kind"] == "scene"]
    # The scene caption first, then bubbles and voice-over captions in element order: the reading
    # order T023 places them in.
    spoken = sorted(
        [*panel["bubbles"], *(c for c in captions if c["kind"] != "scene")],
        key=lambda item: item["element"],
    )
    return ComicPanelView(
        shot_id=f"{screenplay.scenes[scene_index].number}.{number}",
        rect=tuple(panel["rect"]),
        withheld=panel["withheld"],
        lettering=[_lettering(screenplay, scene_index, item) for item in [*scene, *spoken]],
    )


def comic_view(
    project: ProjectRow,
    job: JobRow | None,
    row: ComicRow | None,
    page_urls: Sequence[str],
    pdf_url: str | None,
    *,
    can_make: bool,
) -> ComicView:
    """web.md §6 `ComicView`. `page_urls` are the signed URLs of `row.pages`, in order."""
    screenplay = None if project.screenplay is None else load_screenplay(project.screenplay)
    shots = 0 if project.plan is None else len(load_plan(project.plan).shots)
    comic = None
    if row is not None and screenplay is not None and pdf_url is not None:
        pages = row.layout["pages"]
        if len(pages) != len(page_urls):
            raise ValueError("a signed URL is needed for every page")
        comic = ComicMade(
            made_at=row.made_at,
            pdf_url=pdf_url,
            pages=[
                ComicPageView(
                    number=page["number"],
                    width=page["width"],
                    height=page["height"],
                    image_url=url,
                    panels=[_panel(screenplay, panel) for panel in page["panels"]],
                )
                for page, url in zip(pages, page_urls, strict=True)
            ],
        )
    return ComicView(
        can_make=can_make,
        shots=shots,
        job=None if job is None else comic_job_view(job),
        comic=comic,
    )
