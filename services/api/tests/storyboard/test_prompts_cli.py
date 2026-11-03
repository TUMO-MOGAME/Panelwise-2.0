"""The prompt-printing live check's report (app/storyboard/prompts.py). No network."""

from app.llm import Usage
from app.script import Screenplay, Span, parse_text
from app.shots import PlanReport, ShotPlan
from app.storyboard import FramePrompt, PartKind, PromptPart, build_frame_prompt
from app.storyboard.prompts import cites_this_shot, main, names_in, report
from tests.script.conftest import two_page_text
from tests.storyboard.conftest import STYLE, extraction_of, shot_of


def lighthouse() -> Screenplay:
    return parse_text(*two_page_text())


def test_report_prints_every_part_with_its_span_and_passes_its_checks() -> None:
    screenplay = lighthouse()
    extraction = extraction_of(screenplay, [("NANDI", "NANDI (60s, oilskin coat)")])
    shots = (
        shot_of(screenplay, 0, [0, 1], characters=["NANDI"], time_of_day="NIGHT"),
        shot_of(screenplay, 1, [0, 1, 2, 3], characters=["THABO"], time_of_day="NIGHT", number=1),
        shot_of(screenplay, 2, [0], time_of_day="NIGHT"),
    )
    plan = ShotPlan(shots, PlanReport(3, 3, 0, 0, 0), ("m",), Usage(0, 0, 0))

    text, ok = report(plan, screenplay, extraction, STYLE, 55)

    assert ok
    lines = text.splitlines()
    assert "    setting   p.1 l.5        inside lighthouse kitchen" in lines
    assert "    time      p.1 l.5        night" in lines
    assert any(
        line.startswith("    action    p.1 l.7-8 ") and "a person (60s" in line for line in lines
    )
    # The CONTINUOUS gallery's night cites the kitchen heading.
    gallery = lines.index(next(line for line in lines if line.startswith("2.1 ")))
    assert lines[gallery + 4] == "    time      p.1 l.5        night"
    assert "NANDI" not in text and "THABO" not in text and "(beat)" not in text
    assert text.endswith("prompts with an extracted character's name: 0")


def test_the_checks_catch_a_part_from_outside_the_shot_and_a_name() -> None:
    screenplay = lighthouse()
    extraction = extraction_of(screenplay, [("NANDI", "NANDI (60s, oilskin coat)")])
    shot = shot_of(screenplay, 0, [1], characters=["NANDI"], time_of_day="NIGHT")
    good = build_frame_prompt(shot, screenplay, extraction, STYLE, max_words=55)
    assert cites_this_shot(good, shot, screenplay, extraction)

    elsewhere = PromptPart(PartKind.ACTION, "THABO steps out", Span(1, 24, 24))
    bad = FramePrompt((*good.parts, elsewhere), 0)
    assert not cites_this_shot(bad, shot, screenplay, extraction)
    assert names_in(bad, extraction) == ["THABO"]
    unspanned = FramePrompt((*good.parts, PromptPart(PartKind.ACTION, "DOORS SLAM.", None)), 0)
    assert not cites_this_shot(unspanned, shot, screenplay, extraction)
    # The right span, but words its line doesn't say.
    invented = PromptPart(PartKind.ACTION, "DOORS SLAM. A dragon lands.", Span(1, 10, 10))
    assert not cites_this_shot(
        FramePrompt((*good.parts, invented), 0), shot, screenplay, extraction
    )


async def test_wrong_arguments_print_the_usage() -> None:
    assert await main([]) == 2
    assert await main(["a.pdf", "--colour", "x"]) == 2
