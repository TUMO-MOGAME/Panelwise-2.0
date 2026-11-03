"""panel_weight / layout_geometry: comic.md §4 steps 1-5, §9 (Geometry). Pure, no images."""

import random
from collections.abc import Sequence
from pathlib import Path

import pytest
from PIL import ImageFont

from app.comic import ComicBook, ComicError, Page, Panel, layout, layout_geometry, panel_weight
from app.comic.layout import scene_caption
from app.llm import Usage
from app.script import Action, Dialogue, Element, IntExt, Scene, Screenplay, Span, parse_text
from app.shots import Framing, Movement, PlanReport, Shot, ShotPlan
from tests.script.conftest import two_page_text

WIDTH, HEIGHT, MARGIN, GUTTER = 1988, 3075, 120, 36
SPAN = Span(1, 1, 1)


def say(text: str, extension: str | None = None) -> Dialogue:
    return Dialogue("NANDI", extension, None, text, SPAN)


def scene(index: int, *elements: Element, location: str = "HARBOUR") -> Scene:
    return Scene(
        index, str(index + 1), f"EXT. {location}", IntExt.EXT, location, None, elements, SPAN
    )


def shot(scene_index: int, number: int, framing: Framing, *elements: int) -> Shot:
    return Shot(scene_index, number, framing, Movement.STATIC, elements, (), (), None, "", SPAN, "")


def plan_of(*shots: Shot) -> ShotPlan:
    return ShotPlan(shots, PlanReport(0, len(shots), 0, 0, 0), (), Usage(0, 0, 0))


def book_of(scenes: Sequence[Scene], *shots: Shot) -> ComicBook:
    return layout_geometry(plan_of(*shots), Screenplay("", 1, tuple(scenes), (1,)))


def tiers(page: Page) -> list[list[Panel]]:
    """A page's panels grouped into tiers by their top edge, top to bottom."""
    rows: dict[int, list[Panel]] = {}
    for panel in page.panels:
        rows.setdefault(panel.rect[1], []).append(panel)
    return [rows[y] for y in sorted(rows)]


def rects(book: ComicBook) -> list[list[tuple[int, int, int, int]]]:
    return [[p.rect for p in page.panels] for page in book.pages]


# ---------------------------------------------------------------- step 1: weights


@pytest.mark.parametrize(
    ("framing", "base"),
    [
        (Framing.WIDE, 2.0),
        (Framing.MEDIUM, 1.0),
        (Framing.OVER_SHOULDER, 1.0),
        (Framing.POV, 1.0),
        (Framing.CLOSE_UP, 0.8),
        (Framing.EXTREME_CLOSE_UP, 0.6),
        (Framing.INSERT, 0.6),
    ],
)
def test_base_weight_by_framing_and_the_establishing_beat(framing: Framing, base: float) -> None:
    s = scene(0)
    assert panel_weight(shot(0, 2, framing), s, False, 0) == pytest.approx(base)
    assert panel_weight(shot(0, 1, framing), s, True, 0) == pytest.approx(base + 0.5)


@pytest.mark.parametrize(
    ("chars", "extra"),
    [(0, 0.0), (1, 0.25), (59, 0.25), (60, 0.25), (61, 0.5), (120, 0.5), (121, 0.75)],
)
def test_lettering_adds_a_quarter_per_started_sixty_characters(chars: int, extra: float) -> None:
    weight = panel_weight(shot(0, 2, Framing.MEDIUM), scene(0), False, chars)
    assert weight == pytest.approx(1.0 + extra)


def test_a_shot_weighed_against_another_scene_is_refused() -> None:
    with pytest.raises(ComicError, match="scene 1, shot 2"):
        panel_weight(shot(1, 2, Framing.MEDIUM), scene(0), False, 0)


def test_scene_caption_letters_only_an_absolute_clock() -> None:
    text, breaks = two_page_text()
    kitchen, gallery, stairwell = parse_text(text, breaks).scenes
    assert scene_caption(kitchen) == "LIGHTHOUSE KITCHEN — NIGHT"
    assert scene_caption(gallery) == "LIGHTHOUSE GALLERY"  # CONTINUOUS borrows a clock
    assert scene_caption(stairwell) == "LIGHTHOUSE STAIRWELL"  # no time at all


# ------------------------------------------------------ steps 2-4: tiers, pages, rects


def test_the_sample_lays_out_one_panel_per_shot_in_plan_order() -> None:
    text, breaks = two_page_text()
    screenplay = parse_text(text, breaks)
    plan = plan_of(
        shot(0, 1, Framing.WIDE, 0, 1),  # 2.0 + 0.5 + caption (26 chars) 0.25: solo
        shot(0, 2, Framing.CLOSE_UP, 2, 3),  # 0.8 + 70 chars 0.5 = 1.3
        shot(1, 1, Framing.WIDE, 0),  # 2.0 + 0.5 + caption (18 chars) 0.25: solo
        shot(1, 2, Framing.MEDIUM, 1, 2, 3),  # 1.0 + 36 chars 0.25 = 1.25
        shot(2, 1, Framing.MEDIUM, 0),  # 1.0 + 0.5 + caption (20 chars) 0.25 = 1.75
    )
    book = layout_geometry(plan, screenplay)

    panels = [p for page in book.pages for p in page.panels]
    assert [(p.scene_index, p.shot_number) for p in panels] == [
        (s.scene_index, s.number) for s in plan.shots
    ]
    # Page 1: solo, normal, solo. H = 3075 - 240 - 72 = 2763; u = 2763 / 3.5 = 789.4.
    # Page 2: two normal tiers, stretched. H = 2835 - 36 = 2799; u = 1399.5.
    assert rects(book) == [
        [(120, 120, 1748, 986), (120, 1142, 1748, 789), (120, 1967, 1748, 988)],
        [(120, 120, 1748, 1399), (120, 1555, 1748, 1400)],
    ]
    assert all(p.bubbles == () and p.captions == () for p in panels)  # placed by T023
    assert (book.report.panels, book.report.bubbles, book.report.captions) == (5, 0, 0)
    assert book.report.relayouts == 0
    assert [(p.number, p.width, p.height) for p in book.pages] == [
        (1, WIDTH, HEIGHT),
        (2, WIDTH, HEIGHT),
    ]
    assert layout_geometry(plan, screenplay) == book  # deterministic


def test_a_heavy_shot_gets_a_solo_tier_one_and_a_quarter_tall() -> None:
    s = scene(0)  # caption "HARBOUR" adds 0.25 to the first shot
    book = book_of(
        [s],
        shot(0, 1, Framing.MEDIUM),  # 1.75: opens a tier
        shot(0, 2, Framing.WIDE),  # 2.0: solo, closing the open tier
        shot(0, 3, Framing.CLOSE_UP),
        shot(0, 4, Framing.CLOSE_UP),  # 0.8 + 0.8 = 1.6: stays open, the plan ends
    )
    # u = 2763 / 3.25 = 850.15: tiers 850, 1062, and 850 + the 1 px remainder.
    assert rects(book) == [
        [
            (120, 120, 1748, 850),
            (120, 1006, 1748, 1062),
            (120, 2104, 856, 851),
            (1012, 2104, 856, 851),
        ]
    ]


def test_a_scenes_first_shot_always_opens_a_tier() -> None:
    # 1.75 then 1.55: together they'd share a tier (it closes only after the second joins).
    book = book_of([scene(0), scene(1)], shot(0, 1, Framing.MEDIUM), shot(1, 1, Framing.CLOSE_UP))
    assert [len(t) for t in tiers(book.pages[0])] == [1, 1]


def test_a_tier_closes_at_three_panels() -> None:
    book = book_of(
        [scene(0)],
        shot(0, 1, Framing.WIDE),
        *(shot(0, n, Framing.INSERT) for n in range(2, 6)),  # 0.6 x 3 = 1.8 < 2.0
    )
    assert [[p.shot_number for p in t] for t in tiers(book.pages[0])] == [[1], [2, 3, 4], [5]]


def test_a_tier_closes_when_its_weights_reach_two() -> None:
    book = book_of(
        [scene(0)],
        shot(0, 1, Framing.WIDE),
        shot(0, 2, Framing.MEDIUM),
        shot(0, 3, Framing.MEDIUM),  # 1.0 + 1.0 = 2.0 exactly: closes
        shot(0, 4, Framing.CLOSE_UP),
    )
    assert [[p.shot_number for p in t] for t in tiers(book.pages[0])] == [[1], [2, 3], [4]]


def test_panel_widths_are_proportional_with_the_remainder_last() -> None:
    book = book_of(
        [scene(0)],
        shot(0, 1, Framing.WIDE),
        shot(0, 2, Framing.MEDIUM),
        shot(0, 3, Framing.INSERT),
        shot(0, 4, Framing.INSERT),  # 1.0 : 0.6 : 0.6 of W = 1748 - 72 = 1676
    )
    row = tiers(book.pages[0])[1]
    assert [(p.rect[0], p.rect[2]) for p in row] == [(120, 761), (917, 457), (1410, 458)]


def test_dialogue_widens_a_panel_and_action_does_not() -> None:
    s = scene(0, Action("A gull cries over the harbour wall. " * 5, SPAN), say("x" * 61))
    book = book_of(
        [s],
        shot(0, 1, Framing.WIDE),
        shot(0, 2, Framing.MEDIUM, 0),  # 1.0: action is never lettered
        shot(0, 3, Framing.MEDIUM, 1),  # 1.0 + 0.5 for 61 characters
    )
    assert [p.rect[2] for p in tiers(book.pages[0])[1]] == [684, 1028]  # 1712 x 1/2.5, rest


def test_the_scene_caption_counts_as_lettering_on_the_first_panel() -> None:
    s = scene(0, location="THE LONG GALLERY BELOW THE LAMP ROOM OF THE OLD NORTH LIGHTHOUSE")
    # 1.0 + 0.5 + 0.5 for a 64-character caption = 2.0: a solo tier, so the close-up can't join.
    book = book_of([s], shot(0, 1, Framing.MEDIUM), shot(0, 2, Framing.CLOSE_UP))
    assert [[p.shot_number for p in t] for t in tiers(book.pages[0])] == [[1], [2]]


def test_three_normal_tiers_split_the_page_evenly_and_a_last_page_stretches() -> None:
    scenes = [scene(i) for i in range(4)]
    book = book_of(scenes, *(shot(i, 1, Framing.MEDIUM) for i in range(4)))
    assert rects(book) == [
        [(120, 120, 1748, 921), (120, 1077, 1748, 921), (120, 2034, 1748, 921)],
        [(120, 120, 1748, 2835)],
    ]


def test_geometry_holds_for_any_plan() -> None:
    rng = random.Random(11)
    framings = list(Framing)
    for _ in range(30):
        scenes: list[Scene] = []
        shots: list[Shot] = []
        for index in range(rng.randint(1, 6)):
            lines = [say("Hold the light steady. " * rng.randint(1, 3)) for _ in range(3)]
            scenes.append(scene(index, *lines, location=f"DECK {index}"))
            for number in range(1, rng.randint(2, 7)):
                element = rng.randrange(3)
                shots.append(shot(index, number, rng.choice(framings), element))
        book = book_of(scenes, *shots)

        panels = [p for page in book.pages for p in page.panels]
        assert [(p.scene_index, p.shot_number) for p in panels] == [
            (s.scene_index, s.number) for s in shots
        ]
        for page in book.pages:
            rows = tiers(page)
            assert 1 <= len(rows) <= 3
            assert rows[0][0].rect[1] == MARGIN
            bottom = MARGIN
            for row in rows:
                assert 1 <= len(row) <= 3
                y, h = row[0].rect[1], row[0].rect[3]
                assert y == (MARGIN if row is rows[0] else bottom + GUTTER)
                assert all((p.rect[1], p.rect[3]) == (y, h) for p in row)
                right = MARGIN - GUTTER
                for p in sorted(row, key=lambda p: p.rect[0]):
                    assert p.rect[0] == right + GUTTER and p.rect[2] > 0
                    right = p.rect[0] + p.rect[2]
                assert right == WIDTH - MARGIN
                bottom = y + h
            assert bottom == HEIGHT - MARGIN
        # A scene's first shot is always the first panel of its tier.
        firsts = {s.scene_index: (s.scene_index, s.number) for s in reversed(shots)}
        heads = {(t[0].scene_index, t[0].shot_number) for page in book.pages for t in tiers(page)}
        assert set(firsts.values()) <= heads


# ---------------------------------------------------------- step 5: lettering budget


def test_a_panel_over_its_lettering_budget_is_grown_until_it_fits() -> None:
    # Sixty short lines: 180 characters (weight 0.6 + 0.75), but sixty padded boxes.
    s = scene(0, *(say("No.") for _ in range(60)))
    shots = (
        shot(0, 1, Framing.WIDE),
        shot(0, 2, Framing.WIDE),
        shot(0, 3, Framing.INSERT, *range(60)),
        shot(0, 4, Framing.INSERT),
        shot(0, 5, Framing.INSERT),
    )
    book = book_of([s], *shots)

    assert book.report.relayouts == 1
    heavy = tiers(book.pages[0])[2]
    # Raised by 0.5 to 1.85, it closes its tier with one neighbour instead of two.
    assert [p.shot_number for p in heavy] == [3, 4]
    assert heavy[0].rect[2] == 1292  # 1712 x 1.85 / 2.45


def test_a_panel_still_over_budget_after_three_passes_gets_a_solo_tier() -> None:
    # Found by search: the second relayout reshuffles the tiers and squeezes scene 2's shot 2
    # (0.6 + 0.75 = 1.35) over its budget; the third raises it to 1.85, still short of a solo
    # tier, and it is still over. Past the passes it gets a solo tier; that layout fits.
    wide, medium, ecu = Framing.WIDE, Framing.MEDIUM, Framing.EXTREME_CLOSE_UP
    spec = [
        [(wide, 60), (ecu, 10), (wide, 90), (medium, 50), (ecu, 50)],
        [(ecu, 60), (medium, 90), (medium, 50), (wide, 10), (wide, 0)],
        [(medium, 30), (ecu, 60), (medium, 0)],
    ]
    scenes: list[Scene] = []
    shots: list[Shot] = []
    for index, specs in enumerate(spec):
        first = 0
        for number, (framing, lines) in enumerate(specs, start=1):
            shots.append(shot(index, number, framing, *range(first, first + lines)))
            first += lines
        scenes.append(scene(index, *(say("No.") for _ in range(first))))
    book = book_of(scenes, *shots)

    assert book.report.relayouts == 4
    row = next(
        t
        for page in book.pages
        for t in tiers(page)
        if any((p.scene_index, p.shot_number) == (2, 2) for p in t)
    )
    assert [(p.scene_index, p.shot_number, p.rect[2]) for p in row] == [(2, 2, WIDTH - 2 * MARGIN)]


def test_a_panel_over_budget_even_in_a_solo_tier_fails_naming_the_shot() -> None:
    s = scene(0, say("The lamp went out and the ships came in blind. " * 120))
    with pytest.raises(ComicError, match="scene 0, shot 2"):
        book_of([s], shot(0, 1, Framing.WIDE), shot(0, 2, Framing.MEDIUM, 0))


def test_a_missing_font_fails_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(layout, "FONT_PATH", tmp_path / "ComicNeue-Regular.ttf")
    with pytest.raises(ComicError, match="font"):
        book_of([scene(0)], shot(0, 1, Framing.WIDE))


def test_lettering_uses_pillows_basic_layout_engine_on_every_host() -> None:
    # Pillow picks raqm (kerning) when the host has libfribidi, else basic: a CI runner has
    # it, the API image and Windows don't, so unpinned the same text measured 260 px or 266.
    font = layout.font_at(layout.FONT_PATH, layout.FONT_PX)
    assert font.layout_engine == ImageFont.Layout.BASIC
