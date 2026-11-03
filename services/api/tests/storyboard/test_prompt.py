"""build_frame_prompt and its helpers: storyboard.md §3.1 and §9. Pure, no network."""

import pytest

from app.grounding import Extraction
from app.script import Screenplay, Span, parse_text
from app.shots import Framing
from app.storyboard import (
    FRAMING_WORDS,
    OFF_SCREEN_MARKS,
    PLACEMENT_PHRASES,
    PartKind,
    PromptError,
    build_frame_prompt,
    heading_span,
    introduced_age,
    time_source,
    visible_characters,
)
from app.storyboard.prompts import cites_this_shot
from tests.script.conftest import ACTION, CUE, DIALOGUE, PAREN, heading, two_page_text
from tests.storyboard.conftest import (
    SENTINEL_RATIONALE,
    STYLE,
    extraction_of,
    screenplay_of,
    shot_of,
)

K = PartKind
PAIR = "one figure on the left, one on the right"


@pytest.fixture
def lighthouse() -> Screenplay:
    """Kitchen (NIGHT): [0] Rain… NANDI (60s, oilskin coat) pours tea…, [1] DOORS SLAM.,
    [2] NANDI (without turning) You came back., [3] THABO (O.S.) The boat didn't…
    Gallery (CONTINUOUS): [0] THABO steps out…, [1] to [3] THABO speaks. Stairwell (no time)."""
    return parse_text(*two_page_text())


@pytest.fixture
def cast(lighthouse: Screenplay) -> Extraction:
    return extraction_of(
        lighthouse,
        [("NANDI", "NANDI (60s, oilskin coat)"), ("THABO", "holding a torn map")],
    )


def kinds(parts: object) -> list[PartKind]:
    return [p.kind for p in parts]  # type: ignore[attr-defined]


def test_the_contract_tables() -> None:
    assert FRAMING_WORDS == {
        Framing.WIDE: "wide shot",
        Framing.MEDIUM: "medium shot",
        Framing.CLOSE_UP: "close-up",
        Framing.EXTREME_CLOSE_UP: "extreme close-up",
        Framing.OVER_SHOULDER: "over-the-shoulder shot",
        Framing.POV: "point-of-view shot",
        Framing.INSERT: "close-up insert shot",
    }
    assert PLACEMENT_PHRASES == frozenset({PAIR})
    assert OFF_SCREEN_MARKS == ("V.O.", "O.S.", "O.C.", "OFF")


def test_fixed_order_then_actions_in_element_order_redacted(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    shot = shot_of(
        lighthouse, 0, [0, 1, 2, 3], characters=["NANDI", "THABO"], time_of_day="NIGHT",
        framing=Framing.WIDE,
    )  # fmt: skip
    prompt = build_frame_prompt(shot, lighthouse, cast, STYLE, max_words=100)

    assert [(p.kind, p.text, p.span) for p in prompt.parts] == [
        (K.STYLE, "storyboard sketch, grayscale", None),
        (K.FRAMING, "wide shot", None),
        (K.SETTING, "inside lighthouse kitchen", Span(1, 5, 5)),
        (K.TIME, "night", Span(1, 5, 5)),
        # THABO is only heard (O.S.): one figure on screen.
        (K.COUNT, "one figure", None),
        # T074: NANDI's age, from the line that introduces her.
        (K.AGE, "a person in their 60s", Span(1, 7, 8)),
        (
            K.ACTION,
            "Rain hammers the window. a person (60s, oilskin coat) pours tea into two chipped "
            "mugs.",
            Span(1, 7, 8),
        ),
        (K.ACTION, "DOORS SLAM.", Span(1, 10, 10)),
    ]
    assert prompt.trimmed == 0
    assert prompt.text() == ", ".join(p.text for p in prompt.parts)


def test_dialogue_only_shot_has_no_speech_no_parenthetical_and_no_action(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    shot = shot_of(lighthouse, 0, [2, 3], characters=["NANDI", "THABO"], time_of_day="NIGHT")
    prompt = build_frame_prompt(shot, lighthouse, cast, STYLE, max_words=100)

    # T079: NANDI's look from her introduction, which this shot doesn't cover.
    assert kinds(prompt.parts) == [K.STYLE, K.FRAMING, K.SETTING, K.TIME, K.COUNT, K.AGE, K.LOOK]
    text = prompt.text().lower()
    for absent in ("came back", "without turning", "boat", "cliff", "nandi", "thabo"):
        assert absent not in text
    assert SENTINEL_RATIONALE.lower() not in text


def test_a_character_introduced_in_an_earlier_shot_contributes_nothing(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    doors = build_frame_prompt(
        shot_of(lighthouse, 0, [1], characters=["NANDI"], time_of_day="NIGHT"),
        lighthouse, cast, STYLE, max_words=100,
    )  # fmt: skip
    assert "oilskin" not in doors.text() and "tea" not in doors.text()
    # NANDI is listed by the planner but "DOORS SLAM." doesn't show her.
    assert K.COUNT not in kinds(doors.parts)

    gallery = build_frame_prompt(
        shot_of(lighthouse, 1, [1, 2, 3], characters=["THABO"], time_of_day="NIGHT"),
        lighthouse, cast, STYLE, max_words=100,
    )  # fmt: skip
    assert "map" not in gallery.text()
    assert "(beat)" not in gallery.text() and "beat" not in gallery.text()


def test_a_borrowed_time_cites_the_heading_that_supplied_it(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    # The gallery is CONTINUOUS: its night is the kitchen heading's.
    assert time_source(lighthouse.scenes, 1) == 0
    assert time_source(lighthouse.scenes, 2) == 0
    assert time_source(lighthouse.scenes, 0) == 0
    prompt = build_frame_prompt(
        shot_of(lighthouse, 1, [0], characters=["THABO"], time_of_day="NIGHT"),
        lighthouse, cast, STYLE, max_words=100,
    )  # fmt: skip
    setting, time = prompt.parts[2], prompt.parts[3]
    assert (setting.text, setting.span) == ("outside lighthouse gallery", Span(1, 22, 22))
    assert (time.kind, time.text, time.span) == (
        K.TIME,
        "night",
        heading_span(lighthouse.scenes[0]),
    )
    assert prompt.parts[-1].text == "a person steps out into the wind, holding a torn map."


def test_no_time_is_omitted_and_a_time_the_script_did_not_give_is_refused(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    prompt = build_frame_prompt(
        shot_of(lighthouse, 2, [0], time_of_day=None), lighthouse, cast, STYLE, max_words=100
    )
    assert kinds(prompt.parts) == [K.STYLE, K.FRAMING, K.SETTING, K.ACTION]
    assert prompt.parts[2].text == "inside lighthouse stairwell"
    with pytest.raises(ValueError, match="DAWN"):
        build_frame_prompt(
            shot_of(lighthouse, 2, [0], time_of_day="DAWN"), lighthouse, cast, STYLE,
            max_words=100,
        )  # fmt: skip


def test_time_source_is_none_before_any_clock() -> None:
    screenplay = screenplay_of(
        [heading("1", "INT. HALL"), None, (ACTION, "Dust."), None,
         heading("2", "INT. HALL - LATER"), None, (ACTION, "More dust.")]
    )  # fmt: skip
    assert time_source(screenplay.scenes, 0) is None
    assert time_source(screenplay.scenes, 1) is None
    with pytest.raises(ValueError, match="NIGHT"):
        build_frame_prompt(
            shot_of(screenplay, 1, [0], time_of_day="NIGHT"), screenplay,
            extraction_of(screenplay), STYLE, max_words=100,
        )  # fmt: skip


@pytest.mark.parametrize(
    ("slug", "setting"),
    [
        ("INT. NANDI'S KITCHEN - NIGHT", "inside a person's kitchen"),
        ("EXT. HARBOUR WALL -- DAWN", "outside harbour wall"),
        ("INT./EXT. NANDI'S BAKKIE - MOVING - DAY", "at a person's bakkie - moving"),
    ],
)
def test_prepositions_and_a_redacted_lower_cased_location(slug: str, setting: str) -> None:
    screenplay = screenplay_of([heading("1", slug), None, (ACTION, "NANDI waits.")])
    extraction = extraction_of(screenplay, [("NANDI", "NANDI waits.")])
    time = screenplay.scenes[0].time_of_day
    prompt = build_frame_prompt(
        shot_of(screenplay, 0, [0], characters=["NANDI"], time_of_day=time),
        screenplay, extraction, STYLE, max_words=100,
    )  # fmt: skip
    assert prompt.parts[2].kind is K.SETTING
    assert prompt.parts[2].text == setting
    assert prompt.parts[3].text == (time or "").lower()
    assert "nandi" not in prompt.text().lower()


CROWD_ROWS = [
    heading("1", "INT. HALL - DAY"),
    None,
    (ACTION, "ANNA, BEN, CARA, DAVE and EVE wait."),  # [0]
    None,
    (ACTION, "Ben sits."),  # [1]
    None,
    (CUE, "CARA"),
    (DIALOGUE, "Sit down."),  # [2]
    None,
    (CUE, "DAVE (V.O.)"),
    (DIALOGUE, "I remember."),  # [3]
    None,
    (CUE, "EVE (O.S.)"),
    (DIALOGUE, "Hello?"),  # [4]
    None,
    (CUE, "ANNA (CONT'D)"),
    (PAREN, "(quietly)"),
    (DIALOGUE, "Now."),  # [5]
    None,
    (ACTION, "The lights hum."),  # [6]
]
CROWD = ["ANNA", "BEN", "CARA", "DAVE", "EVE"]


@pytest.mark.parametrize(
    ("elements", "visible", "count"),
    [
        ([6], (), None),  # all five planner-listed, none shown
        ([1], ("BEN",), "one figure"),  # a named actor
        ([1, 2], ("BEN", "CARA"), "two figures"),  # plus an on-screen speaker
        ([1, 2, 3, 4], ("BEN", "CARA"), "two figures"),  # V.O. and O.S. are not on screen
        ([1, 2, 5], ("ANNA", "BEN", "CARA"), "three figures"),  # CONT'D is on screen
        ([1, 2, 3, 4, 5], ("ANNA", "BEN", "CARA"), "three figures"),
        ([0], tuple(CROWD), "a group of figures"),
    ],
)
def test_count_is_the_characters_the_covered_elements_put_on_screen(
    elements: list[int], visible: tuple[str, ...], count: str | None
) -> None:
    screenplay = screenplay_of(CROWD_ROWS)
    extraction = extraction_of(screenplay, [(n, f"{n}") for n in ("BEN",)])
    shot = shot_of(screenplay, 0, elements, characters=CROWD, time_of_day="DAY")
    assert visible_characters(shot, screenplay, extraction) == visible
    prompt = build_frame_prompt(shot, screenplay, extraction, STYLE, max_words=100)
    counts = [p.text for p in prompt.parts if p.kind is K.COUNT]
    assert counts == ([count] if count else [])
    assert all(p.span is None for p in prompt.parts if p.kind is K.COUNT)


def test_four_figures() -> None:
    screenplay = screenplay_of(
        [heading("1", "INT. HALL - DAY"), None, (ACTION, "ANNA, BEN, CARA and DAVE wait.")]
    )
    shot = shot_of(screenplay, 0, [0], characters=CROWD, time_of_day="DAY")
    prompt = build_frame_prompt(shot, screenplay, extraction_of(screenplay), STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is K.COUNT] == ["four figures"]


def test_a_placement_follows_the_count_and_needs_exactly_two_on_screen() -> None:
    screenplay = screenplay_of(CROWD_ROWS)
    extraction = extraction_of(screenplay)
    two = shot_of(screenplay, 0, [1, 2], characters=CROWD, time_of_day="DAY")
    prompt = build_frame_prompt(two, screenplay, extraction, STYLE, max_words=100, placement=PAIR)
    assert kinds(prompt.parts)[4:6] == [K.COUNT, K.PLACEMENT]
    assert (prompt.parts[5].text, prompt.parts[5].span) == (PAIR, None)

    with pytest.raises(ValueError, match="placement"):
        build_frame_prompt(
            two, screenplay, extraction, STYLE, max_words=100,
            placement="ANNA on the left, BEN on the right",
        )  # fmt: skip
    one = shot_of(screenplay, 0, [1], characters=CROWD, time_of_day="DAY")
    with pytest.raises(ValueError, match="two"):
        build_frame_prompt(one, screenplay, extraction, STYLE, max_words=100, placement=PAIR)


def test_a_named_person_extraction_missed_is_left_in_the_prompt(
    lighthouse: Screenplay,
) -> None:
    """The residual risk (storyboard.md §3.1, §8), pinned so any change to it is deliberate: a
    named person who never speaks and whom extraction omits is not known to be a name."""
    screenplay = screenplay_of(
        [heading("1", "INT. HALL - DAY"), None,
         (ACTION, "MARTA watches from the doorway as NANDI sweeps."), None,
         (CUE, "NANDI"), (DIALOGUE, "Go home.")]
    )  # fmt: skip
    extraction = extraction_of(screenplay)  # NANDI from her cue; MARTA nowhere
    prompt = build_frame_prompt(
        shot_of(screenplay, 0, [0], characters=["NANDI"], time_of_day="DAY"),
        screenplay, extraction, STYLE, max_words=100,
    )  # fmt: skip
    assert prompt.parts[-1].text == "MARTA watches from the doorway as a person sweeps."


# Budget: style 3 words + "medium shot" 2 + "inside lighthouse kitchen" 3 + "night" 1 +
# "one figure" 2 + T074's "a person in their 60s" 5 = 16 fixed words; [0] is 15 words, [1] "DOORS
# SLAM." 2.
@pytest.mark.parametrize(
    ("max_words", "actions", "trimmed"),
    [
        (33, ["Rain hammers the window. a person (60s, oilskin coat) pours tea into two "
              "chipped mugs.", "DOORS SLAM."], 0),
        (32, ["Rain hammers the window. a person (60s, oilskin coat) pours tea into two "
              "chipped mugs."], 1),
        (22, ["Rain hammers the window."], 2),  # six words fit: cut at the sentence end
        (20, ["Rain hammers the window."], 2),
        (19, ["Rain hammers the"], 2),  # no sentence end fits: a word boundary
        (17, ["Rain"], 2),
        (16, [], 2),  # not one word fits: dropped
    ],
)  # fmt: skip
def test_the_budget_drops_actions_from_the_tail_then_cuts_the_first(
    lighthouse: Screenplay, cast: Extraction, max_words: int, actions: list[str], trimmed: int
) -> None:
    shot = shot_of(lighthouse, 0, [0, 1], characters=["NANDI"], time_of_day="NIGHT")
    prompt = build_frame_prompt(shot, lighthouse, cast, STYLE, max_words=max_words)
    assert [p.text for p in prompt.parts if p.kind is K.ACTION] == actions
    assert prompt.trimmed == trimmed
    assert len(prompt.text().split()) <= max_words
    assert kinds(prompt.parts)[:5] == [K.STYLE, K.FRAMING, K.SETTING, K.TIME, K.COUNT]


def test_fixed_parts_over_the_budget_raise_naming_the_shot(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    shot = shot_of(lighthouse, 0, [0], characters=["NANDI"], time_of_day="NIGHT", number=4)
    with pytest.raises(PromptError, match=r"shot 4 of scene 1"):
        build_frame_prompt(shot, lighthouse, cast, STYLE, max_words=10)


def test_the_heading_span_is_the_heading_line(lighthouse: Screenplay) -> None:
    assert heading_span(lighthouse.scenes[1]) == Span(1, 22, 22)


def test_a_character_named_like_a_clock_leaves_the_time_alone() -> None:
    """PR #27 review: TIME is ABSOLUTE_TIMES' own word, never redacted into "a person"."""
    screenplay = screenplay_of(
        [heading("1", "EXT. HARBOUR -- DAWN"), None, (ACTION, "DAWN mends a net.")]
    )
    extraction = extraction_of(screenplay, [("DAWN", "DAWN mends a net.")])
    prompt = build_frame_prompt(
        shot_of(screenplay, 0, [0], characters=["DAWN"], time_of_day="DAWN"),
        screenplay, extraction, STYLE, max_words=100,
    )  # fmt: skip
    assert [(p.kind, p.text) for p in prompt.parts[3:]] == [
        (K.TIME, "dawn"),
        (K.COUNT, "one figure"),
        (K.ACTION, "a person mends a net."),
    ]


# --- T074: a visible character's age, from the script's introduction ------------------------------


def kite() -> Screenplay:
    return screenplay_of(
        [
            heading("1", "EXT. FLAT ROOF - DAY"),
            (ACTION, "A flat tin roof. LERATO (10), braids tied back, grips a kite."),
            (ACTION, "MOKGOSI (70s) climbs the ladder. OLDLERATO waves."),
            (CUE, "LERATO"),
            (DIALOGUE, "Come on, wind."),
        ]
    )


def test_introduced_age_reads_the_number_after_the_name() -> None:
    sp = kite()
    lerato = introduced_age("LERATO", sp)
    assert lerato is not None and lerato[0] == "a 10-year-old"
    assert lerato[1] == sp.scenes[0].elements[0].span
    mokgosi = introduced_age("MOKGOSI", sp)
    assert mokgosi is not None and mokgosi[0] == "a person in their 70s"
    assert mokgosi[1] == sp.scenes[0].elements[0].span  # one action element introduces both


def test_introduced_age_is_none_without_a_number_or_inside_another_word(
    lighthouse: Screenplay,
) -> None:
    assert introduced_age("THABO", lighthouse) is None  # introduced with no parenthesis
    assert introduced_age("NANDI", lighthouse) == ("a person in their 60s", Span(1, 7, 8))
    sp = screenplay_of(
        [
            heading("1", "INT. ROOM - DAY"),
            (ACTION, "BIGLERATO (10) sits. SAM (tall, thin) waits."),
        ]
    )
    assert introduced_age("LERATO", sp) is None  # "LERATO" only inside another name
    assert introduced_age("SAM", sp) is None  # a parenthesis that gives no number


def test_each_visible_character_s_age_follows_the_count_and_counts_as_fixed_words() -> None:
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)"), ("MOKGOSI", "MOKGOSI (70s)")])
    shot = shot_of(sp, 0, [0, 1], characters=["LERATO", "MOKGOSI"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    ages = [(p.kind, p.text) for p in prompt.parts if p.kind is K.AGE]
    assert ages == [(K.AGE, "a 10-year-old"), (K.AGE, "a person in their 70s")]
    assert kinds(prompt.parts).index(K.AGE) == kinds(prompt.parts).index(K.COUNT) + 1
    fixed = len(" ".join(p.text for p in prompt.parts if p.kind is not K.ACTION).split())
    with pytest.raises(PromptError):
        build_frame_prompt(shot, sp, cast, STYLE, max_words=fixed - 1)


def test_an_off_screen_speaker_gets_no_age(lighthouse: Screenplay, cast: Extraction) -> None:
    shot = shot_of(lighthouse, 0, [3], characters=["THABO"], time_of_day="NIGHT")
    prompt = build_frame_prompt(shot, lighthouse, cast, STYLE, max_words=100)
    assert K.AGE not in kinds(prompt.parts)


@pytest.mark.parametrize(
    ("intro", "age"),
    [
        ("BABY (5 months) sleeps.", None),  # T074 review: months are no years
        ("BABY (6 weeks) sleeps.", None),
        ("BABY (30s-40s) waits.", None),  # a range: no one age
        ("BABY (early 30s) waits.", None),
        ("BABY (10-ish) waits.", None),
        ("BABY (8 years old) waits.", "a 8-year-old"),
        ("BABY (8; small) waits.", "a 8-year-old"),
        ("BABY (40s, tired) waits.", "a person in their 40s"),
    ],
)
def test_only_an_age_in_years_reads_as_one(intro: str, age: str | None) -> None:
    sp = screenplay_of([heading("1", "INT. ROOM - DAY"), (ACTION, intro)])
    found = introduced_age("BABY", sp)
    assert (found[0] if found else None) == age


def test_two_characters_introduced_in_one_line_both_pass_the_live_check() -> None:
    """T074 review: LERATO (10) and MOKGOSI (70s) share one Action span; the CLI's check must
    accept both ages, not only the last one it saw."""
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)"), ("MOKGOSI", "MOKGOSI (70s)")])
    shot = shot_of(sp, 0, [0], characters=["LERATO", "MOKGOSI"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is K.AGE] == [
        "a 10-year-old",
        "a person in their 70s",
    ]
    assert cites_this_shot(prompt, shot, sp, cast)
