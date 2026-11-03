"""The storyboard (storyboard.md §3.3, §4, §6 `build.py`; T026): every shot through verify's loop,
at most `concurrency` at once, each attempt and state written by T021's writer as it happens.

A shot whose renderer fails ends FAILED, logged, and the storyboard goes on (T066). Only a renderer
that looks down stops it -- no frame drawn yet (none has reached its audit) and min(3, shots)
frames failed: then no new shot
starts, the shots in flight are awaited (their drawings and audits are paid for, and their rows are
kept), and StoryboardError names the first failed shot in plan order. A withheld frame is
information, not a failure.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.frames.writer import FrameWriter, frame_hooks
from app.grounding import Extraction
from app.llm import NebiusChatModel
from app.script import Screenplay
from app.shots import Shot, ShotPlan
from app.storyboard.model import Storyboard, StoryboardError, StoryboardFrame
from app.storyboard.render import RenderRecord, RenderRecorder
from app.verify.loop import render_until_accepted
from app.verify.model import Check, FrameOutcome, FrameState, Severity, Verdict

log = logging.getLogger(__name__)

DOWN_AFTER = 3  # failures with no frame drawn that mean the renderer is down (storyboard.md §4)

_CHECK_ORDER = {check: i for i, check in enumerate(Check)}


def frame_of(outcome: FrameOutcome, record: RenderRecord | None) -> StoryboardFrame:
    """The storyboard's view of one outcome (§3.3), from its last attempt's record. Pure."""
    last = outcome.audits[-1] if outcome.audits else None
    accepted = outcome.state in (FrameState.PASSED, FrameState.WARNED)
    noted: tuple[Check, ...] = ()
    if last is not None and outcome.state in (FrameState.WITHHELD, FrameState.WARNED):
        # A warned frame names every check it failed: with AUDIT_WITHHOLDS off, hard ones too.
        wanted = {Severity.HARD} if outcome.state is FrameState.WITHHELD else set(Severity)
        failed = (c.check for c in last.checks if c.severity in wanted and not c.ok)
        noted = tuple(sorted(failed, key=_CHECK_ORDER.__getitem__))
    if outcome.frame is not None:
        prompt: str | None = outcome.frame.prompt
    else:
        prompt = None if record is None else record.prompt.text()
    return StoryboardFrame(
        shot=outcome.shot,
        state=outcome.state,
        asset=record.asset if accepted and record is not None else None,
        prompt=prompt,
        seed=None if last is None else last.seed,
        attempts=len(outcome.audits),
        verdict=Verdict.ERROR if last is None else last.verdict,
        noted_checks=noted,
    )


def _failed(shot: tuple[int, int], states: list[FrameState]) -> StoryboardFrame:
    """A frame whose renderer raised (§4): FAILED, no drawing, no audit at that attempt."""
    return StoryboardFrame(
        shot=shot,
        state=FrameState.FAILED,
        asset=None,
        prompt=None,
        seed=None,
        attempts=states.count(FrameState.RENDERING),
        verdict=Verdict.ERROR,
        noted_checks=(),
        failure="render",
    )


async def build_storyboard(
    model: NebiusChatModel,
    renderer: RenderRecorder,
    plan: ShotPlan,
    screenplay: Screenplay,
    extraction: Extraction,
    *,
    writer: FrameWriter,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
    width: int = 1280,
    height: int = 720,
    concurrency: int = 2,
    max_renders: int = 3,
    withholding: frozenset[Check] | None = None,
) -> Storyboard:
    gate = asyncio.Semaphore(concurrency)
    failed: list[tuple[int, int]] = []  # shots whose renderer raised
    errors: list[BaseException] = []  # anything else (an audit or database error)
    settled = 0
    drawn: set[tuple[int, int]] = set()  # shots that reached their audit: a drawing exists
    total = len(plan.shots)
    down = False

    async def one(shot: Shot) -> FrameOutcome | StoryboardFrame | None:
        nonlocal settled, down
        key = (shot.scene_index, shot.number)
        async with gate:
            if down or errors:  # the renderer looks down, or something else broke: start nothing
                return None
            log_audit, write_state = frame_hooks(writer, renderer, key)
            states: list[FrameState] = []

            async def on_state(state: FrameState, attempt: int) -> None:
                if state is FrameState.AUDITING:  # drawn, though not yet judged (§4)
                    drawn.add(key)
                await write_state(state, attempt)
                # Recorded once written: the loop enters FAILED only when the renderer raised, so a
                # write that fails first is never mistaken for the renderer's failure.
                states.append(state)

            try:
                outcome = await render_until_accepted(
                    model,
                    renderer,
                    shot,
                    screenplay,
                    extraction,
                    width=width,
                    height=height,
                    max_renders=max_renders,
                    withholding=withholding,
                    log=log_audit,
                    on_state=on_state,
                )
            except Exception as error:
                if not states or states[-1] is not FrameState.FAILED:
                    errors.append(error)
                    return None
                # Never silent (§3.5): the renderer's own message, never the key or prompt.
                log.warning("shot %s couldn't be drawn: %s", key, error)
                failed.append(key)  # the loop has already written the frame FAILED
                if not drawn and len(failed) >= min(DOWN_AFTER, total):
                    down = True
                result: FrameOutcome | StoryboardFrame = _failed(key, states)
            else:
                result = outcome
        settled += 1
        if progress is not None:
            try:
                await progress(settled, total)
            except Exception:  # progress is shown, not load-bearing: never fail a shot over it
                log.warning("storyboard progress %d/%d not written", settled, total, exc_info=True)
        return result

    outcomes = await asyncio.gather(*(one(shot) for shot in plan.shots))
    if errors:
        raise errors[0]
    if down:
        order = {(s.scene_index, s.number): i for i, s in enumerate(plan.shots)}
        first = min(failed, key=order.__getitem__)
        raise StoryboardError(f"the renderer looks down: {len(failed)} frame(s) failed", shot=first)

    frames: list[StoryboardFrame] = []
    renders = cached = 0
    for outcome in outcomes:
        if outcome is None:  # unreachable unless stopped; kept for the type
            continue
        if isinstance(outcome, StoryboardFrame):  # a frame whose renderer failed
            frames.append(outcome)
            continue
        records = [renderer.record(outcome.shot, a.attempt) for a in outcome.audits]
        renders += sum(not r.cached for r in records)
        cached += sum(r.cached for r in records)
        frames.append(frame_of(outcome, records[-1] if records else None))
    return Storyboard(renderer.style.key, width, height, tuple(frames), renders, cached)
