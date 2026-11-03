"""The shot planner: each scene becomes shots that cover all its elements, in order, and name only
what the script and the grounded extraction put there. docs/design/shots.md §4.

Ported from FrameFlow's shot_service.py: the shot-list call, the camera vocabularies, and the
explicit time of day (a CONTINUOUS heading once got "soft overcast light" in a night scene). Not
ported: the free-text frame description (where invention lived), the hard-coded no-model shots (a
placeholder), and the Redis cache (Redis is gone).
"""

import asyncio
from collections.abc import Sequence

from pydantic import ValidationError

from app.characters.labels import redaction_labels
from app.characters.redact import named_as_figure
from app.grounding import EntityKind, Extraction
from app.llm import LLMError, NebiusChatModel, StructuredResult, Tier, Usage, structured_chat
from app.script import Action, Dialogue, Scene, Screenplay, Span, match_speaker, resolve_times
from app.shots.model import Framing, Movement, PlanReport, Shot, ShotError, ShotPlan
from app.shots.schema import ProposedShot, ScenePlan

SYSTEM_PROMPT = (
    "You are a storyboard artist planning the shots for one screenplay scene. The scene's "
    "elements are numbered [0], [1] and so on. Plan 1 to 6 shots, never more shots than "
    "elements, that together cover every element in order: each shot covers a consecutive run "
    "of elements from `first` to `last`, and the next shot starts right after the previous one "
    "ends. For each shot choose a framing "
    "and a camera movement, list the characters and props in frame using only the names given "
    "for this scene, and give a one-sentence rationale. Describe nothing else: the frame is drawn "
    "only from what the script says."
)


def _normalise(
    proposed: Sequence[tuple[int, int]], n: int
) -> tuple[list[tuple[int, int]], int, list[int | None]]:
    """The partition, the number of repairs, and which proposal each range came from."""
    if n <= 0:
        return [], 0, []

    def clamp(i: int) -> int:
        return min(max(i, 0), n - 1)

    order = sorted(
        range(len(proposed)),
        key=lambda i: tuple(sorted((clamp(proposed[i][0]), clamp(proposed[i][1])))),
    )
    ranges: list[tuple[int, int]] = []
    origin: list[int | None] = []
    start = 0
    for i in order:
        last = max(clamp(proposed[i][0]), clamp(proposed[i][1]))  # its start is `start`
        if start >= n or last < start:
            continue  # wholly covered already
        # A gap before this range is absorbed by it; an overlap is trimmed off it.
        ranges.append((start, max(start, last)))
        origin.append(i)
        start = ranges[-1][1] + 1
    if not ranges:
        ranges, origin = [(0, n - 1)], [None]
    elif ranges[-1][1] < n - 1:
        ranges[-1] = (ranges[-1][0], n - 1)  # an uncovered tail extends the last shot

    as_proposed = set(proposed)
    kept = sum(1 for o in origin if o is not None)
    repairs = sum(1 for r in ranges if r not in as_proposed) + (len(proposed) - kept)
    return ranges, repairs, origin


def normalise_ranges(
    proposed: Sequence[tuple[int, int]], n: int
) -> tuple[list[tuple[int, int]], int]:
    """Any proposal becomes a partition of range(n): every element in exactly one range, in
    order. Deterministic; it only regroups real elements, so it can't invent anything."""
    ranges, repairs, _ = _normalise(proposed, n)
    return ranges, repairs


def render_scene(
    scene: Scene, characters: Sequence[str], props: Sequence[str], time_of_day: str | None
) -> str:
    lines = [scene.heading, ""]
    for i, element in enumerate(scene.elements):
        if isinstance(element, Dialogue):
            who = element.cue
            if element.extension:
                who += f" ({element.extension})"
            if element.parenthetical:
                who += f" ({element.parenthetical})"
            lines.append(f"[{i}] {who}: {element.text}")
        else:
            lines.append(f"[{i}] {element.text}")
    n = len(scene.elements)
    lines += [
        "",
        # Without the bounds the model padded a one-element scene with six shots over [0]-[14].
        f"{n} element{'s' if n != 1 else ''}, [0] to [{n - 1}]: no shot goes past [{n - 1}], "
        f"and at most {n} shot{'s' if n != 1 else ''}.",
        f"Characters in this scene: {', '.join(characters) or 'none'}",
        f"Props in this scene: {', '.join(props) or 'none'}",
    ]
    if time_of_day:
        lines.append(f"Time of day: {time_of_day}")
    return "\n".join(lines)


def _allowed(extraction: Extraction, kind: EntityKind, scene_index: int) -> list[str]:
    return [e.name for e in extraction.entities if e.kind is kind and scene_index in e.scenes]


def _keep(proposed: Sequence[str], allowed: Sequence[str]) -> tuple[tuple[str, ...], int]:
    """The allowed names the model meant, in its order; and how many names it invented."""
    kept: list[str] = []
    dropped = 0
    for name in proposed:
        match = match_speaker(name, allowed)
        if match is None:
            dropped += 1
        elif match not in kept:
            kept.append(match)
    return tuple(kept), dropped


def named_in_action(
    scene: Scene, elements: Sequence[int], extraction: Extraction, screenplay: Screenplay
) -> tuple[str, ...]:
    """Every character a covered Action element names as a figure, in extraction order (T092,
    shots.md §3): its own and paired names' tokens, less any token another character also has."""
    characters = [e.name for e in extraction.entities if e.kind is EntityKind.CHARACTER]
    tokens = {c: frozenset(redaction_labels(extraction, screenplay, only=c)) for c in characters}
    shared = {
        t
        for c in characters
        for t in tokens[c]
        if any(t in tokens[o] for o in characters if o != c)
    }
    texts = [e.text for i in elements if isinstance(e := scene.elements[i], Action)]
    return tuple(
        c for c in characters if any(named_as_figure(t, tokens[c] - shared) for t in texts)
    )


async def plan_shots(
    model: NebiusChatModel,
    screenplay: Screenplay,
    extraction: Extraction,
    *,
    concurrency: int = 4,
    temperature: float = 0.0,
) -> ShotPlan:
    times = resolve_times(screenplay.scenes)
    gate = asyncio.Semaphore(concurrency)

    async def one(scene: Scene) -> StructuredResult[ScenePlan]:
        characters = _allowed(extraction, EntityKind.CHARACTER, scene.index)
        props = _allowed(extraction, EntityKind.PROP, scene.index)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": render_scene(scene, characters, props, times[scene.index])},
        ]
        async with gate:
            try:
                return await structured_chat(
                    model, messages, ScenePlan, Tier.FAST, temperature=temperature, max_tokens=2048
                )
            except (LLMError, ValidationError) as exc:
                # A ValidationError quotes the model's output, which quotes the script.
                detail = str(exc) if isinstance(exc, LLMError) else type(exc).__name__
                raise ShotError(
                    f"Planning scene {scene.number} failed: {detail}", scene=scene.number
                ) from exc

    to_plan = [s for s in screenplay.scenes if s.elements]
    try:
        async with asyncio.TaskGroup() as group:
            tasks = {s.index: group.create_task(one(s)) for s in to_plan}
    except* ShotError as failures:
        raise failures.exceptions[0] from None
    results = {index: task.result() for index, task in tasks.items()}

    shots: list[Shot] = []
    repaired = chars_dropped = props_dropped = chars_added = 0
    for scene in screenplay.scenes:
        time = times[scene.index]
        if not scene.elements:
            heading = Span(scene.span.page, scene.span.line_start, scene.span.line_start)
            shots.append(
                Shot(
                    scene.index,
                    1,
                    Framing.WIDE,
                    Movement.STATIC,
                    (),
                    (),
                    (),
                    time,
                    "Establishes the location.",
                    heading,
                    scene.heading,
                )
            )
            continue

        proposed: list[ProposedShot] = results[scene.index].value.shots
        ranges, repairs, origin = _normalise(
            [(p.first, p.last) for p in proposed], len(scene.elements)
        )
        repaired += repairs
        allowed_chars = _allowed(extraction, EntityKind.CHARACTER, scene.index)
        allowed_props = _allowed(extraction, EntityKind.PROP, scene.index)
        for number, ((first, last), source) in enumerate(zip(ranges, origin, strict=True), 1):
            p = proposed[source] if source is not None else None
            characters, c_drop = _keep(p.characters if p else [], allowed_chars)
            props, p_drop = _keep(p.props if p else [], allowed_props)
            chars_dropped += c_drop
            props_dropped += p_drop
            # T092: whoever a covered action line names is in frame, offered or not.
            named = range(first, last + 1)
            added = tuple(
                c
                for c in named_in_action(scene, named, extraction, screenplay)
                if c not in characters
            )
            characters += added
            chars_added += len(added)
            covered = scene.elements[first : last + 1]
            shots.append(
                Shot(
                    scene_index=scene.index,
                    number=number,
                    framing=p.framing if p else Framing.WIDE,
                    movement=p.movement if p else Movement.STATIC,
                    elements=tuple(range(first, last + 1)),
                    characters=characters,
                    props=props,
                    time_of_day=time,
                    rationale=p.rationale.strip() if p else "Covers the whole scene.",
                    span=Span(
                        covered[0].span.page, covered[0].span.line_start, covered[-1].span.line_end
                    ),
                    source="\n".join(e.text for e in covered),
                )
            )

    chats = [r.chat for r in results.values()]
    return ShotPlan(
        shots=tuple(shots),
        report=PlanReport(
            scenes=len(screenplay.scenes),
            shots=len(shots),
            ranges_repaired=repaired,
            characters_dropped=chars_dropped,
            props_dropped=props_dropped,
            characters_added=chars_added,
        ),
        models=tuple(dict.fromkeys(c.model for c in chats)),
        usage=Usage(
            prompt_tokens=sum(c.usage.prompt_tokens for c in chats),
            completion_tokens=sum(c.usage.completion_tokens for c in chats),
            reasoning_tokens=sum(c.usage.reasoning_tokens for c in chats),
        ),
    )
