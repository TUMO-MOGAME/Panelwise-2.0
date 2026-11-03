"""Parse a screenplay PDF, extract, plan, and print every shot's frame prompt, part by part.

    cd services/api && uv run python -m app.storyboard.prompts path/to/script.pdf [--style KEY]

Each part is printed with its kind and, for a script part, the page and lines it came from, so
the prompts can be read against the script before any GPU exists (T008). Ends with two checks:
every script part cites this shot's heading, its clock's heading or an element it covers; and no
prompt contains an extracted character's name. Only public-domain or self-written scripts: never
a copyrighted one.
"""

import asyncio
import re
import sys
from pathlib import Path

from app.characters import name_tokens, redact
from app.characters.labels import redaction_labels
from app.core.config import Settings
from app.grounding import EntityKind, Extraction, ExtractionError, extract, normalize_for_grounding
from app.llm import LLMError, NebiusChatModel
from app.script import ABSOLUTE_TIMES, Action, Screenplay, ScriptParseError, Span, parse_pdf
from app.shots import Shot, ShotError, ShotPlan, plan_shots
from app.storyboard.prompt import (
    FramePrompt,
    PartKind,
    PromptError,
    build_frame_prompt,
    heading_span,
    introduced_age,
    introduced_look,
    sex_part,
    time_source,
    visible_characters,
)
from app.storyboard.styles import PUBLIC_STYLES, Style, StyleError, load_styles

_SCRIPT_KINDS = frozenset(
    {PartKind.SETTING, PartKind.TIME, PartKind.AGE, PartKind.SEX, PartKind.LOOK, PartKind.ACTION}
)


def _span(span: Span | None) -> str:
    if span is None:
        return ""
    if span.line_start == span.line_end:
        return f"p.{span.page} l.{span.line_start}"
    return f"p.{span.page} l.{span.line_start}-{span.line_end}"


def _characters(extraction: Extraction) -> list[str]:
    return [e.name for e in extraction.entities if e.kind is EntityKind.CHARACTER]


def cites_this_shot(
    prompt: FramePrompt, shot: Shot, screenplay: Screenplay, extraction: Extraction
) -> bool:
    """Every script part cites this scene's heading (SETTING), the heading its clock came from
    (TIME), the line that introduces a visible character (AGE, T074, with exactly the age
    `introduced_age` reads there) or an Action element the shot covers (ACTION), and says only
    what that line says, redacted; no other part cites anything. storyboard.md §3.1's invariant,
    checked live."""
    scene = screenplay.scenes[shot.scene_index]
    lines = screenplay.text.split("\n")
    source = time_source(screenplay.scenes, scene.index)
    heading = heading_span(scene)
    allowed: dict[PartKind, dict[Span, str]] = {
        PartKind.SETTING: {heading: lines[heading.line_start - 1]},
        PartKind.TIME: {},
        PartKind.ACTION: {
            e.span: e.text for i in shot.elements if isinstance(e := scene.elements[i], Action)
        },
    }
    visible = visible_characters(shot, screenplay, extraction)
    ages = [introduced_age(c, screenplay, extraction) for c in visible]
    # T082: a sexed character with no age, "a female person", cited with its evidence's span.
    sexes = {s for c in visible if (s := sex_part(c, screenplay, extraction)) is not None}
    # Keyed by (age, span): two characters introduced in one line share its span (T074 review).
    introduced = {age for age in ages if age is not None}
    if source is not None:
        clock = heading_span(screenplay.scenes[source])
        allowed[PartKind.TIME] = {clock: lines[clock.line_start - 1]}
    labels = redaction_labels(extraction, screenplay)
    # T079: each visible character's look, redacted and collapsed as the prompt writes it.
    looks = {
        (" ".join(redact(look[0], labels).split()), look[1])
        for c in visible
        if (look := introduced_look(c, screenplay)) is not None
    }
    for p in prompt.parts:
        if p.span is None:
            if p.kind in _SCRIPT_KINDS:
                return False
            continue
        if p.kind is PartKind.LOOK:
            if (p.text, p.span) not in looks:  # exactly the introduction's own description
                return False
            continue
        if p.kind is PartKind.AGE:
            if (p.text, p.span) not in introduced:  # the phrase around the script's own number
                return False
            continue
        if p.kind is PartKind.SEX:
            if (p.text, p.span) not in sexes:  # the code's phrase, keyed by the script's word
                return False
            continue
        cited = allowed.get(p.kind, {}).get(p.span)
        if cited is None:
            return False
        if p.kind is PartKind.TIME:
            # A closed vocabulary, not redacted: the clock word itself, from that heading.
            if p.text.upper() not in ABSOLUTE_TIMES or normalize_for_grounding(
                p.text
            ) not in normalize_for_grounding(cited):
                return False
            continue
        # SETTING's leading preposition is the code's word, not the script's.
        text = p.text.split(" ", 1)[-1] if p.kind is PartKind.SETTING else p.text
        if normalize_for_grounding(text) not in normalize_for_grounding(redact(cited, labels)):
            return False
    return True


def names_in(prompt: FramePrompt, extraction: Extraction) -> list[str]:
    """Words of the prompt written the way screenplays write names (capitalised) that are a
    name token of an extracted character, or of any character's or prop's other name (T052)."""
    tokens = name_tokens(
        _characters(extraction) + [o for e in extraction.entities for o in e.other_names]
    )
    return [
        w
        for w in re.findall(r"[^\W\u02bc]+", prompt.text())
        if w[0].isupper() and w.upper() in tokens
    ]


def report(
    plan: ShotPlan, screenplay: Screenplay, extraction: Extraction, style: Style, max_words: int
) -> tuple[str, bool]:
    out: list[str] = []
    uncited = named = trimmed = 0
    for shot in plan.shots:
        scene = screenplay.scenes[shot.scene_index]
        prompt = build_frame_prompt(shot, screenplay, extraction, style, max_words=max_words)
        ok = cites_this_shot(prompt, shot, screenplay, extraction)
        names = names_in(prompt, extraction)
        uncited += not ok
        named += bool(names)
        trimmed += prompt.trimmed
        out.append(
            f"{scene.number or scene.index + 1}.{shot.number:<3} {shot.framing:<16} "
            f"{_span(shot.span):<14} words={len(prompt.text().split())} trimmed={prompt.trimmed}"
            + ("" if ok else "  UNCITED PART")
            + (f"  NAMES {names}" if names else "")
        )
        out += [f"    {p.kind:<9} {_span(p.span):<14} {p.text}" for p in prompt.parts]
    out += [
        "",
        f"style        {style.key} ({style.label}); budget {max_words} words; "
        f"{trimmed} action parts trimmed over {len(plan.shots)} shots",
        f"cited        every script part cites this shot's heading, its clock's heading or a "
        f"covered element: {'yes' if not uncited else f'NO ({uncited} shots)'}",
        f"names        prompts with an extracted character's name: {named}",
    ]
    return "\n".join(out), not uncited and not named


async def main(argv: list[str]) -> int:
    style_key: str | None = None
    if len(argv) == 3 and argv[1] == "--style":
        style_key = argv[2]
    elif len(argv) != 1:
        print(__doc__)
        return 2
    settings = Settings()
    try:
        private = settings.panelwise_private_styles.strip()
        style = load_styles(PUBLIC_STYLES, Path(private) if private else None).get(style_key)
        screenplay = parse_pdf(await asyncio.to_thread(Path(argv[0]).read_bytes))
        model = NebiusChatModel.from_settings(settings)
    except (OSError, StyleError, ScriptParseError, LLMError) as exc:
        print(f"FAIL  {exc}")
        return 1
    try:
        extraction = await extract(model, screenplay)
        plan = await plan_shots(model, screenplay, extraction)
    except (ExtractionError, ShotError) as exc:
        print(f"FAIL  {exc}")
        return 1
    finally:
        await model.aclose()
    try:
        text, ok = report(plan, screenplay, extraction, style, settings.comfyui_max_words)
    except PromptError as exc:
        print(f"FAIL  {exc}")
        return 1
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
