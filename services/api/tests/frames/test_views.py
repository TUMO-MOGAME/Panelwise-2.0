"""frame_view: one `frames` row as web.md §6's FrameView (T047). Pure."""

import uuid
from datetime import UTC, datetime

import pytest

from app.frames.model import FrameAuditRow, FrameRow
from app.frames.views import MAX_RENDERS, audit_view, frame_view
from app.script import parse_pdf
from tools.build_samples import SAMPLES

SCREENPLAY = parse_pdf((SAMPLES / "the-red-kite.pdf").read_bytes())


def row(state: str, asset: str | None = None, withheld: str | None = None) -> FrameRow:
    return FrameRow(
        project_id=uuid.uuid4(),
        scene_index=1,
        shot_number=3,
        state=state,
        attempt=2,
        job_id=uuid.uuid4(),
        asset=asset,
        withheld_check=withheld,
        updated_at=datetime(2026, 10, 3, tzinfo=UTC),
    )


@pytest.mark.parametrize("state", ["passed", "warned"])
def test_an_accepted_frame_carries_its_signed_url(state: str) -> None:
    view = frame_view(row(state, asset="frames/abc.png"), SCREENPLAY, "https://signed/abc")
    assert view.shot_id == f"{SCREENPLAY.scenes[1].number}.3"
    assert (view.state, view.attempt, view.max_renders) == (state, 2, MAX_RENDERS)
    assert view.image_url == "https://signed/abc" and view.audits == []


@pytest.mark.parametrize("state", ["rendering", "auditing", "withheld", "failed"])
def test_no_other_state_ever_has_an_image(state: str) -> None:
    view = frame_view(
        row(state, withheld="unscripted_person" if state == "withheld" else None), SCREENPLAY, None
    )
    assert view.image_url is None
    assert view.withheld_check == ("unscripted_person" if state == "withheld" else None)


def test_max_renders_is_verify_mds_three() -> None:
    assert MAX_RENDERS == 3


def test_max_renders_is_the_setting_it_is_given() -> None:
    assert (
        frame_view(row("withheld"), SCREENPLAY, None, max_renders=1).max_renders == 2
    )  # attempt 2
    assert frame_view(row("withheld"), SCREENPLAY, None, max_renders=3).max_renders == 3


def test_an_audit_logged_before_t071_reads_its_text_as_empty() -> None:
    old = FrameAuditRow(
        project_id=uuid.uuid4(), job_id=uuid.uuid4(), scene_index=1, shot_number=3, attempt=1,
        seed=7, frame_asset="frames/a.png",
        description={
            "people": [], "setting": "interior", "light": "night", "shot_size": "medium",
            "objects": [], "has_text": True,
        },
        judgement=None, checks=[], positions={}, verdict="fail", models=["v"],
        prompt_tokens=1, completion_tokens=1, created_at=datetime(2026, 10, 10, tzinfo=UTC),
    )  # fmt: skip
    view = audit_view(old)
    assert view.description is not None and view.description.text == []
    assert view.description.signature is False  # T072: a row from before it


def test_max_renders_grows_with_a_users_extra_attempt() -> None:
    late = row("rendering")
    late.attempt = 5
    assert frame_view(late, SCREENPLAY, None).max_renders == 5
