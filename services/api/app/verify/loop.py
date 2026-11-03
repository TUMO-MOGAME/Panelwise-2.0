"""Render, audit, re-render until a frame is accepted or withheld. docs/design/verify.md §4, §5, §6.

Every attempt is audited and logged, pass or fail. A frame is never accepted without a PASS or WARN
audit: an audit that can't run (ERROR) withholds it, and running out of attempts withholds it.
"""

from collections.abc import Awaitable, Callable

from app.grounding import Extraction
from app.llm import NebiusChatModel
from app.script import Screenplay
from app.shots import Shot
from app.verify.audit import apply_ladder, audit_frame, find_heads, seed_for
from app.verify.model import (
    Audit,
    Check,
    FrameOutcome,
    FrameState,
    RenderedFrame,
    Renderer,
    Verdict,
)

MAX_RENDERS = 3  # the first render and two re-renders (verify.md §4, k = 2)

_ACCEPTED = {Verdict.PASS: FrameState.PASSED, Verdict.WARN: FrameState.WARNED}


async def render_until_accepted(
    model: NebiusChatModel,
    renderer: Renderer,
    shot: Shot,
    screenplay: Screenplay,
    extraction: Extraction,
    *,
    width: int,
    height: int,
    max_renders: int = MAX_RENDERS,
    first_attempt: int = 1,
    log: Callable[[Audit], Awaitable[None]],
    on_state: Callable[[FrameState, int], Awaitable[None]] | None = None,
    withholding: frozenset[Check] | None = None,
    heads: bool = False,
) -> FrameOutcome:
    """Attempts `first_attempt` .. `first_attempt + max_renders - 1`, each seeded `seed_for(shot,
    attempt)`. `on_state` is awaited on every §5 transition, before the new state's work. A renderer
    exception moves the frame to FAILED and is re-raised: the caller fails its job. `heads` (T097,
    the comic job): the accepted attempt gets the head agent before it is logged."""
    if max_renders < 1 or first_attempt < 1:
        raise ValueError("max_renders and first_attempt are at least 1")
    key = (shot.scene_index, shot.number)
    audits: list[Audit] = []

    async def enter(state: FrameState, attempt: int) -> None:
        if on_state is not None:
            await on_state(state, attempt)

    attempt = first_attempt
    for attempt in range(first_attempt, first_attempt + max_renders):
        await enter(FrameState.RENDERING, attempt)
        try:
            frame: RenderedFrame = await renderer.render(
                shot, attempt, seed_for(shot, attempt), width, height
            )
        except Exception:
            await enter(FrameState.FAILED, attempt)
            raise
        await enter(FrameState.AUDITING, attempt)
        audit = await audit_frame(model, frame, shot, screenplay, extraction)
        audit = apply_ladder(audit, withholding)  # T094: off the ladder, a hard check warns
        if heads and audit.verdict in _ACCEPTED:  # T097: never on a frame thrown away
            audit = await find_heads(model, frame, audit)
        await log(audit)
        audits.append(audit)
        if (accepted := _ACCEPTED.get(audit.verdict)) is not None:
            await enter(accepted, attempt)
            return FrameOutcome(key, accepted, frame, tuple(audits))
        if audit.verdict is Verdict.ERROR:
            break  # an audit that couldn't run never earns a retry that might pass unaudited
    await enter(FrameState.WITHHELD, attempt)
    return FrameOutcome(key, FrameState.WITHHELD, None, tuple(audits))
