"""T118: one speaker's consecutive lines are linked, one balloon split in two (comic.md §3, §4 steps
7-8, §6): the first bubble has the tail, each linked one a connector to the bubble before it."""

import logging

import pytest

from app.comic import Panel, bubbles, place_lettering, render, to_json
from app.comic.bubbles import LINK_GAP, connector, tail_hull, tails_cross
from app.comic.model import Rect
from app.script import Dialogue, Span
from tests.comic.test_t112 import framed, panel_of, second

SPAN = Span(1, 1, 1)
corners = bubbles._corners  # pyright: ignore[reportPrivateUsage]
gap = bubbles._gap  # pyright: ignore[reportPrivateUsage]


def say(cue: str, text: str, extension: str | None = None, note: str | None = None) -> Dialogue:
    return Dialogue(cue, extension, note, text, SPAN)


def lettered(*lines: Dialogue) -> Panel:
    screenplay, plan, book = panel_of(*lines)
    return second(place_lettering(book, screenplay, plan, framed(book)))


def test_two_lines_of_one_speaker_are_one_balloon_split_in_two() -> None:
    panel = lettered(say("NANDI", "You came back."), say("NANDI", "The boat didn't."))
    first, then = panel.bubbles
    assert not first.linked and then.linked
    assert sum(b.tail is not None for b in panel.bubbles) == 1  # one tail (T119: on either box)
    assert gap(first.rect, then.rect) <= LINK_GAP
    assert [b.text for b in panel.bubbles] == ["You came back.", "The boat didn't."]


def test_three_lines_chain() -> None:
    panel = lettered(
        say("NANDI", "You came back."), say("NANDI", "The boat didn't."), say("NANDI", "I walked.")
    )
    assert [b.linked for b in panel.bubbles] == [False, True, True]
    assert sum(b.tail is not None for b in panel.bubbles) == 1
    for before, bubble in zip(panel.bubbles, panel.bubbles[1:], strict=False):
        assert gap(before.rect, bubble.rect) <= LINK_GAP


@pytest.mark.parametrize(
    "lines",
    [
        (say("NANDI", "You came back."), say("THABO", "I did."), say("NANDI", "Why?")),
        (say("NANDI", "You came back."), say("NANDI", "Thabo?", "O.S.")),  # another kind
        (say("NANDI", "You came back."), say("NANDI", "Run!", None, "shouting")),  # another voice
        (
            say("NANDI", "You came back.", None, "whispering"),
            say("NANDI", "Why?", None, "whispering"),
        ),
        (
            say("NANDI", "He came back.", None, "thinking"),
            say("NANDI", "Why?", None, "thinking"),
        ),
        (
            say("NANDI", "Hello?", "O.S.", "on the phone"),
            say("NANDI", "Are you there?", "O.S.", "on the phone"),
        ),
        (say("NANDI", "You came back."), say("NANDI", "I knew.", "V.O."), say("NANDI", "Why?")),
    ],
)
def test_lines_that_dont_link(lines: tuple[Dialogue, ...]) -> None:
    panel = lettered(*lines)
    assert not any(b.linked for b in panel.bubbles)
    assert all(b.tail is not None for b in panel.bubbles)


def test_two_shouts_link() -> None:
    panel = lettered(say("NANDI", "Run!", None, "shouting"), say("NANDI", "Now!", None, "shouting"))
    assert panel.bubbles[1].linked


def test_the_gap_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bubbles, "LINK_GAP", 30)  # a grid row apart, about 14 px, at most
    panel = lettered(say("NANDI", "You came back."), say("NANDI", "The boat didn't."))
    first, then = panel.bubbles
    assert then.linked and gap(first.rect, then.rect) <= 30


def test_a_connector_runs_clear_of_another_speakers_box_and_tail() -> None:
    panel = lettered(
        say("NANDI", "You came back."), say("NANDI", "The boat didn't."), say("THABO", "I did.")
    )
    first, then, other = panel.bubbles
    band = connector(first.rect, then.rect)
    assert not tails_cross(band, corners(other.rect))
    assert other.tail is not None
    hull = tail_hull(other.voice, other.rect, other.tail)
    assert hull is None or not tails_cross(band, hull)


def test_the_last_resort_search_unlinks(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always(a: tuple[tuple[float, float], ...], b: tuple[tuple[float, float], ...]) -> bool:
        return True

    screenplay, plan, book = panel_of(
        say("NANDI", "You came back."),
        say("NANDI", "The boat didn't."),
        say("THABO", "Nandi?", "O.S."),
    )
    monkeypatch.setattr(bubbles, "tails_cross", always)
    caplog.set_level(logging.WARNING, logger="app.comic.bubbles")
    panel = second(place_lettering(book, screenplay, plan, framed(book)))
    assert "tails cross on scene 0, shot 2" in caplog.text
    assert not any(b.linked for b in panel.bubbles)  # as before T112: a tail on every bubble
    assert all(b.tail is not None for b in panel.bubbles)


def test_the_json_carries_linked() -> None:
    screenplay, plan, book = panel_of(say("NANDI", "You came back."), say("NANDI", "Why?"))
    data = to_json(place_lettering(book, screenplay, plan, framed(book)), {})
    got = data["pages"][0]["panels"][1]["bubbles"]  # type: ignore[index]
    assert [b["linked"] for b in got] == [False, True]  # type: ignore[index]
    assert sum(b["tail"] is not None for b in got) == 1  # type: ignore[index]


def test_render_draws_the_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    screenplay, plan, book = panel_of(say("NANDI", "You came back."), say("NANDI", "Why?"))
    given = framed(book)
    placed = place_lettering(book, screenplay, plan, given)
    asked: list[tuple[Rect, Rect]] = []

    def recording(a: Rect, b: Rect) -> tuple[tuple[float, float], ...]:
        asked.append((a, b))
        return connector(a, b)

    monkeypatch.setattr(render, "connector", recording)
    render.render_pages(placed, given)
    first, then = second(placed).bubbles
    assert asked == [(first.rect, then.rect)]
