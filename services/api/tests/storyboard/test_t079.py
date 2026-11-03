"""T079: each visible character's sex and look from their introduction; an off-screen line has its
listeners on screen (storyboard.md §3.1, §6, §9)."""

import pytest

from app.script import Screenplay
from app.storyboard import (
    PartKind as K,
)
from app.storyboard import (
    build_frame_prompt,
    introduced_age,
    introduced_look,
    introduced_sex,
)
from app.storyboard.prompts import cites_this_shot
from tests.script.conftest import ACTION, CUE, DIALOGUE, heading
from tests.storyboard.conftest import STYLE, extraction_of, screenplay_of, shot_of

LERATO = "LERATO (10), braids tied back, grips a RED KITE almost as tall as she is."
MOKGOSI = "MOKGOSI (70s), reading glasses pushed up on his forehead, solders a wire."


def one_line(text: str) -> Screenplay:
    return screenplay_of([heading("1", "INT. ROOM - DAY"), (ACTION, text)])


@pytest.mark.parametrize(
    ("line", "who", "sex"),
    [
        (LERATO, "LERATO", "female"),
        (MOKGOSI, "MOKGOSI", "male"),
        # "her" after MAMA THEMBI is the girl she watches, an object, not her own description.
        (
            "MAMA THEMBI (60s), the shop's owner, watches her over half-moon glasses.",
            "MAMA THEMBI",
            None,
        ),
        ("ZANELE (30s), cardigan over her railway uniform, sits.", "ZANELE", "female"),
        ("SIPHO (50s).", "SIPHO", None),
        # A later sentence's "She" may be anyone.
        ("KOOS (70s), the night cleaner, pushes a broom. She waves.", "KOOS", None),
        # The stretch ends at the next introduction: Lerato's "she" isn't Mokgosi's.
        ("MOKGOSI (70s) waits. LERATO (10) runs as fast as she can.", "MOKGOSI", None),
    ],
)
def test_introduced_sex(line: str, who: str, sex: str | None) -> None:
    assert introduced_sex(who, one_line(line)) == sex


@pytest.mark.parametrize(
    ("line", "who", "look"),
    [
        (LERATO, "LERATO", "braids tied back"),
        (MOKGOSI, "MOKGOSI", "reading glasses pushed up on his forehead"),
        ("NANDI (60s, oilskin coat) pours tea.", "NANDI", "oilskin coat"),
        (
            "DUBE (60s), the station master, waistcoat and pocket watch, backs in.",
            "DUBE",
            "the station master",
        ),
        (
            "GRACE (30s, tired), a nurse still in her scrubs, comes in.",
            "GRACE",
            "tired, a nurse still in her scrubs",
        ),
        # No comma closes the phrase before the sentence ends: an action, not a look.
        (
            "AMAHLE (8), who is wearing pyjamas under a yellow raincoat and has been crying.",
            "AMAHLE",
            None,
        ),
        (
            "PRIYA (20), soaked through and shivering from head to foot today, runs.",
            "PRIYA",
            None,
        ),  # 9 words
        ("SIPHO (50s).", "SIPHO", None),
        ("SIPHO (50s) waits.", "SIPHO", None),
    ],
)
def test_introduced_look(line: str, who: str, look: str | None) -> None:
    sp = one_line(line)
    found = introduced_look(who, sp)
    assert (found[0] if found else None) == look
    if found:
        assert found[1] == sp.scenes[0].elements[0].span


@pytest.mark.parametrize(
    ("line", "who", "age"),
    [
        (LERATO, "LERATO", "a 10-year-old girl"),
        (MOKGOSI, "MOKGOSI", "a man in his 70s"),
        ("ZANELE (30s), cardigan over her uniform, sits.", "ZANELE", "a woman in her 30s"),
        ("PRIYA (20), soaked through, runs as fast as she can.", "PRIYA", "a 20-year-old woman"),
        ("TEBOGO (17), a busker, tunes the violin he loves.", "TEBOGO", "a 17-year-old boy"),
        ("SIPHO (50s).", "SIPHO", "a person in their 50s"),
        ("BABY (8) sleeps.", "BABY", "a 8-year-old"),
    ],
)
def test_the_age_carries_the_sex(line: str, who: str, age: str) -> None:
    found = introduced_age(who, one_line(line))
    assert found is not None and found[0] == age


def kite() -> Screenplay:
    return screenplay_of(
        [
            heading("1", "EXT. FLAT ROOF - DAY"),
            (ACTION, LERATO),
            (CUE, "MOKGOSI (O.S.)"),
            (DIALOGUE, "Is that my good shirt you are flying?"),
            (ACTION, MOKGOSI),
            (CUE, "LERATO"),
            (DIALOGUE, "Come on, wind."),
            (ACTION, "LERATO runs to the edge. MOKGOSI laughs."),
        ]
    )


def test_each_visible_character_s_age_then_look_cite_the_introduction() -> None:
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)"), ("MOKGOSI", "MOKGOSI (70s)")])
    # A later line: the introductions aren't covered, so their looks come from there.
    shot = shot_of(sp, 0, [4], characters=["LERATO", "MOKGOSI"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    people = [(p.kind, p.text) for p in prompt.parts if p.kind in (K.AGE, K.LOOK)]
    assert people == [
        (K.AGE, "a 10-year-old girl"),
        (K.LOOK, "braids tied back"),
        (K.AGE, "a man in his 70s"),
        (K.LOOK, "reading glasses pushed up on his forehead"),
    ]
    assert cites_this_shot(prompt, shot, sp, cast)


def test_a_look_that_isn_t_the_introduction_s_is_refused() -> None:
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)")])
    shot = shot_of(sp, 0, [4], characters=["LERATO"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    parts = tuple(
        p.__class__(p.kind, "grips a RED KITE", p.span) if p.kind is K.LOOK else p
        for p in prompt.parts
    )
    assert not cites_this_shot(prompt.__class__(parts, prompt.trimmed), shot, sp, cast)


def test_an_off_screen_line_puts_its_listeners_on_screen() -> None:
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)"), ("MOKGOSI", "MOKGOSI (70s)")])
    # Only Mokgosi's O.S. line: Lerato hears it.
    shot = shot_of(sp, 0, [1], characters=["LERATO", "MOKGOSI"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is K.COUNT] == ["one figure"]
    assert [p.text for p in prompt.parts if p.kind is K.AGE] == ["a 10-year-old girl"]
    assert cites_this_shot(prompt, shot, sp, cast)


def test_no_look_when_the_shot_covers_the_introduction() -> None:
    """Its ACTION part already says it, word for word."""
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)")])
    shot = shot_of(sp, 0, [0], characters=["LERATO"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    assert K.LOOK not in [p.kind for p in prompt.parts]


def test_looks_give_way_to_the_budget_and_never_fail_a_render() -> None:
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)"), ("MOKGOSI", "MOKGOSI (70s)")])
    shot = shot_of(sp, 0, [4], characters=["LERATO", "MOKGOSI"], time_of_day="DAY")
    roomy = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    fixed = len(" ".join(p.text for p in roomy.parts if p.kind not in (K.LOOK, K.ACTION)).split())
    tight = build_frame_prompt(shot, sp, cast, STYLE, max_words=fixed + 12 + 3)
    # Room for Lerato's 3-word look and 12 action words, not for Mokgosi's 7.
    assert [p.text for p in tight.parts if p.kind is K.LOOK] == ["braids tied back"]
    none = build_frame_prompt(shot, sp, cast, STYLE, max_words=fixed + 1)
    assert K.LOOK not in [p.kind for p in none.parts]


def test_no_listener_when_someone_is_already_on_screen() -> None:
    sp = kite()
    cast = extraction_of(sp, [("LERATO", "LERATO (10)"), ("MOKGOSI", "MOKGOSI (70s)")])
    shot = shot_of(sp, 0, [1, 2], characters=["LERATO", "MOKGOSI"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is K.AGE] == ["a man in his 70s"]


# --- T079 review ---------------------------------------------------------------------------------


def test_a_he_after_another_character_s_name_is_theirs() -> None:
    sp = screenplay_of(
        [
            heading("1", "INT. SHOP - DAY"),
            (ACTION, "MAMA THEMBI (60s), the shop's owner, watches SIPHO as he counts."),
            (CUE, "SIPHO"),
            (DIALOGUE, "Forty."),
        ]
    )
    assert introduced_sex("MAMA THEMBI", sp) is None
    found = introduced_age("MAMA THEMBI", sp)
    assert found is not None and found[0] == "a person in their 60s"


def test_a_prop_in_capitals_doesn_t_cut_the_pronoun_off() -> None:
    assert introduced_sex("LERATO", one_line(LERATO)) == "female"  # RED KITE is no name


@pytest.mark.parametrize(
    "line",
    [
        "OFFICER MOLOI (40s), and OFFICER VAN WYK (20s), new, eager.",  # another introduction
        "PRIYA (20), as the train leaves, runs.",  # a conjunction
        "GRACE (30s), with 2 bags, comes in.",  # a number
        "LERATO (10, braids. She holds a kite (red), runs.",  # no ")" before the sentence ends
    ],
)
def test_what_is_not_a_look_is_left_out(line: str) -> None:
    who = line.split(" (")[0]
    assert introduced_look(who, one_line(line)) is None


def test_another_character_s_name_is_never_a_look() -> None:
    sp = screenplay_of(
        [
            heading("1", "INT. ROOM - DAY"),
            (ACTION, "AMAHLE (8), Grace's daughter, sleeps."),
            (CUE, "GRACE"),
            (DIALOGUE, "Shh."),
        ]
    )
    assert introduced_look("AMAHLE", sp) is None


def test_a_voice_over_the_planner_doesn_t_list_still_brings_listeners() -> None:
    """The RADIO ANNOUNCER (V.O.) isn't one of the shot's characters; Lerato still hears him."""
    sp = screenplay_of(
        [
            heading("1", "INT. WORKSHOP - DAY"),
            (ACTION, LERATO),
            (CUE, "RADIO ANNOUNCER (V.O.)"),
            (DIALOGUE, "A storm moving in from the west."),
        ]
    )
    cast = extraction_of(sp, [("LERATO", "LERATO (10)")])
    shot = shot_of(sp, 0, [1], characters=["LERATO"], time_of_day="DAY")
    prompt = build_frame_prompt(shot, sp, cast, STYLE, max_words=100)
    assert [p.text for p in prompt.parts if p.kind is K.COUNT] == ["one figure"]
