"""parse_text / parse_pdf -- docs/design/script.md §3, §4, §9."""

import pytest
from fpdf import FPDF

from app.script import (
    Action,
    Dialogue,
    IntExt,
    Screenplay,
    ScriptParseError,
    Span,
    parse_pdf,
    parse_text,
)

from .conftest import (
    ACTION,
    CUE,
    DIALOGUE,
    PAGE_1,
    PAGE_2,
    PAREN,
    Row,
    heading,
    layout,
    pdf_bytes,
    two_page_text,
)


@pytest.fixture
def screenplay() -> Screenplay:
    text, breaks = two_page_text()
    return parse_text(text, breaks)


def texts(screenplay: Screenplay, scene: int) -> list[str]:
    return [e.text for e in screenplay.scenes[scene].elements]


# --- scenes ------------------------------------------------------------------------


def test_scenes_come_out_in_order_with_the_scripts_own_numbers(screenplay: Screenplay) -> None:
    assert [(s.index, s.number) for s in screenplay.scenes] == [(0, "1"), (1, "2"), (2, "3")]
    assert screenplay.page_count == 2


def test_heading_fields_are_split_and_the_repeated_number_dropped(screenplay: Screenplay) -> None:
    first, second = screenplay.scenes[:2]
    assert (first.heading, first.int_ext, first.location, first.time_of_day) == (
        "INT. LIGHTHOUSE KITCHEN - NIGHT",
        IntExt.INT,
        "LIGHTHOUSE KITCHEN",
        "NIGHT",
    )
    assert (second.int_ext, second.location, second.time_of_day) == (
        IntExt.EXT,
        "LIGHTHOUSE GALLERY",
        "CONTINUOUS",
    )


def test_a_heading_without_a_time_has_none_rather_than_an_invented_day(
    screenplay: Screenplay,
) -> None:
    assert screenplay.scenes[2].time_of_day is None


@pytest.mark.parametrize(
    ("slug", "int_ext", "location", "time"),
    [
        ("INT/EXT. BAKKIE -- CONTINUOUS", IntExt.INT_EXT, "BAKKIE", "CONTINUOUS"),
        ("EXT/INT. FARMHOUSE - DAWN", IntExt.INT_EXT, "FARMHOUSE", "DAWN"),
        ("int. hallway -- later", IntExt.INT, "hallway", "LATER"),
        ("EXT. ROOFTOP--NIGHT", IntExt.EXT, "ROOFTOP", "NIGHT"),
        # T039: the form screenwriting software writes, with a dot on both sides of the slash.
        ("INT./EXT. BAKKIE -- DAY", IntExt.INT_EXT, "BAKKIE", "DAY"),
        ("EXT./INT. FARMHOUSE - DUSK", IntExt.INT_EXT, "FARMHOUSE", "DUSK"),
        # T039: two separators, and the last segment is a known time: that is the time.
        ("INT. SIPHO'S HOUSE - KITCHEN - NIGHT", IntExt.INT, "SIPHO'S HOUSE - KITCHEN", "NIGHT"),
        ("INT./EXT. BAKKIE - MOVING - DAY", IntExt.INT_EXT, "BAKKIE - MOVING", "DAY"),
        ("EXT. PIER -- END -- MOMENTS LATER", IntExt.EXT, "PIER -- END", "MOMENTS LATER"),
        # ...and when it is not a known time, the first separator splits, as before.
        ("INT. HOUSE - KITCHEN - FLASHBACK", IntExt.INT, "HOUSE", "KITCHEN - FLASHBACK"),
    ],
)
def test_heading_variants(slug: str, int_ext: IntExt, location: str, time: str) -> None:
    scene = parse_text(layout([(ACTION, slug), (ACTION, "Something happens.")])).scenes[0]
    assert (scene.int_ext, scene.location, scene.time_of_day) == (int_ext, location, time)
    assert scene.number == "1"


# --- elements ----------------------------------------------------------------------


def test_elements_keep_script_order_and_join_wrapped_lines(screenplay: Screenplay) -> None:
    assert texts(screenplay, 0) == [
        "Rain hammers the window. NANDI (60s, oilskin coat) pours tea into two chipped mugs.",
        "DOORS SLAM.",
        "You came back.",
        "The boat didn't. I walked the last mile along the cliff.",
    ]
    kinds = [type(e) for e in screenplay.scenes[0].elements]
    assert kinds == [Action, Action, Dialogue, Dialogue]


def test_a_line_break_hyphen_joins_with_no_space_and_a_spaced_dash_keeps_its_space() -> None:
    # T048, script.md §3: the same rule grounding applies to the raw lines.
    rows = [
        heading("1", "EXT. JETTY - DAY"),
        None,
        (ACTION, "A fisherman in a sea-"),
        (ACTION, "green oilskin. A sign: LOST PROPERTY -"),
        (ACTION, "PLATFORM 9. He stops--"),
        (ACTION, "then turns. Wait\u2014"),
        (ACTION, "what? WAIT --"),
        (ACTION, "NO."),
        (ACTION, "-"),
        (ACTION, "Gone."),
        None,
        (CUE, "SIPHO"),
        (DIALOGUE, "In the teeth of a south-"),
        (DIALOGUE, "westerly."),
    ]
    action, speech = parse_text(layout(rows)).scenes[0].elements

    assert action.text == (
        "A fisherman in a sea-green oilskin. A sign: LOST PROPERTY - PLATFORM 9. "
        "He stops--then turns. Wait\u2014what? WAIT -- NO. - Gone."
    )
    assert speech.text == "In the teeth of a south-westerly."
    # Spans are unchanged: still the eight and two lines the element came from.
    assert (action.span.line_start, action.span.line_end) == (3, 10)
    assert (speech.span.line_start, speech.span.line_end) == (13, 14)


def test_an_all_caps_line_at_the_action_margin_is_action_not_a_character(
    screenplay: Screenplay,
) -> None:
    doors = screenplay.scenes[0].elements[1]
    assert isinstance(doors, Action)


def test_cue_extension_and_parenthetical_are_separate_fields(screenplay: Screenplay) -> None:
    nandi, thabo = screenplay.scenes[0].elements[2:]
    assert isinstance(nandi, Dialogue) and isinstance(thabo, Dialogue)
    assert (nandi.cue, nandi.extension, nandi.parenthetical) == ("NANDI", None, "without turning")
    assert (thabo.cue, thabo.extension, thabo.parenthetical) == ("THABO", "O.S.", None)


def test_a_parenthetical_mid_speech_starts_a_new_dialogue_for_the_same_cue(
    screenplay: Screenplay,
) -> None:
    speeches = [e for e in screenplay.scenes[1].elements if isinstance(e, Dialogue)]
    assert [(d.cue, d.extension, d.parenthetical, d.text) for d in speeches] == [
        ("THABO", None, None, "It's gone."),
        ("THABO", None, "beat", "All of it."),
        ("THABO", "CONT'D", None, "The whole coast."),
    ]


def test_title_page_transitions_and_page_furniture_are_not_content(
    screenplay: Screenplay,
) -> None:
    everything = " ".join(e.text for s in screenplay.scenes for e in s.elements)
    for noise in ("THE KEEPER'S LIGHT", "FADE IN", "CUT TO", "MORE", "2."):
        assert noise not in everything


def test_dialogue_continuing_onto_a_new_page_without_a_cue_stays_dialogue() -> None:
    rows = [heading("1", "INT. ROOM - DAY"), None, (CUE, "NANDI"), (DIALOGUE, "One more")]
    text = layout([*rows, (DIALOGUE, "thing.")])
    scene = parse_text(text, [len(rows) + 1]).scenes[0]

    assert [(type(e), e.text, e.span.page) for e in scene.elements] == [
        (Dialogue, "One more", 1),
        (Dialogue, "thing.", 2),
    ]


def test_shouted_all_caps_dialogue_is_not_mistaken_for_a_new_speaker() -> None:
    rows = [
        heading("1", "INT. ROOM - DAY"),
        None,
        (CUE, "NANDI"),
        (DIALOGUE, "NO!"),
        None,
        (CUE, "THABO"),
        (DIALOGUE, "Yes."),
    ]
    elements = parse_text(layout(rows)).scenes[0].elements

    assert [(type(e), getattr(e, "cue", None), e.text) for e in elements] == [
        (Dialogue, "NANDI", "NO!"),
        (Dialogue, "THABO", "Yes."),
    ]


def test_an_int_ext_heading_with_dots_starts_a_scene_and_keeps_its_prefix() -> None:
    rows = [
        heading("2", "INT. ROOM - DAY"),
        None,
        (ACTION, "A chair."),
        None,
        heading("3", "INT./EXT. SIPHO'S BAKKIE - MOVING - DAY"),
        None,
        (ACTION, "The truck rattles on."),
    ]
    scenes = parse_text(layout(rows)).scenes

    assert [(s.number, s.heading) for s in scenes] == [
        ("2", "INT. ROOM - DAY"),
        ("3", "INT./EXT. SIPHO'S BAKKIE - MOVING - DAY"),
    ]
    assert [e.text for e in scenes[1].elements] == ["The truck rattles on."]


def test_a_parenthetical_that_wraps_is_one_parenthetical_not_dialogue() -> None:
    rows = [
        heading("1", "INT. SHOP - DAY"),
        None,
        (CUE, "MAMA THEMBI"),
        (PAREN, "(sliding a bucket across"),
        (PAREN, "the counter, then leaning"),
        (PAREN, "in close)"),
        (DIALOGUE, "Kazi. Is it true, what they"),
        (DIALOGUE, "say?"),
        (PAREN, "(beat, then almost"),
        (PAREN, "to herself)"),
        (DIALOGUE, "The letter came."),
    ]
    screenplay = parse_text(layout(rows))
    speeches = screenplay.scenes[0].elements

    assert [(type(e), getattr(e, "parenthetical", None), e.text) for e in speeches] == [
        (
            Dialogue,
            "sliding a bucket across the counter, then leaning in close",
            "Kazi. Is it true, what they say?",
        ),
        (Dialogue, "beat, then almost to herself", "The letter came."),
    ]
    # The parenthetical's lines are not in the speech's span: its span is the spoken lines only.
    assert speeches[0].span == Span(page=1, line_start=7, line_end=8)


def test_an_unclosed_bracket_in_dialogue_stays_dialogue() -> None:
    # Only a bracket closed at the same column is a parenthetical; otherwise nothing is lost.
    rows = [
        heading("1", "INT. SHOP - DAY"),
        None,
        (CUE, "NANDI"),
        (DIALOGUE, "(and I mean this"),
        (DIALOGUE, "kindly: go home."),
        None,
        (CUE, "THABO"),
        (PAREN, "(quietly, as if"),
        (DIALOGUE, "No."),
    ]
    elements = parse_text(layout(rows)).scenes[0].elements

    assert [
        (getattr(e, "cue", None), getattr(e, "parenthetical", None), e.text) for e in elements
    ] == [
        ("NANDI", None, "(and I mean this kindly: go home."),
        ("THABO", None, "(quietly, as if No."),
    ]


def test_a_location_ending_in_the_scene_number_keeps_it() -> None:
    scene = parse_text(layout([(ACTION, "1 INT. ROOM 1 - DAY"), (ACTION, "A chair.")])).scenes[0]
    assert (scene.number, scene.location) == ("1", "ROOM 1")


def test_a_dialogue_heavy_script_still_finds_the_action_margin() -> None:
    # More dialogue lines than action lines: the most common indent is the dialogue column.
    rows = [heading("1", "INT. OFFICE - DAY"), None, (ACTION, "They sit.")]
    for i in range(6):
        rows += [None, (CUE, "AMARA" if i % 2 else "JONAS"), (DIALOGUE, f"Line {i}.")]
    scene = parse_text(layout(rows)).scenes[0]

    assert [type(e) for e in scene.elements] == [Action] + [Dialogue] * 6


# --- spans -------------------------------------------------------------------------


def test_a_line_that_starts_with_continued_keeps_every_word() -> None:
    rows = [
        heading("1", "INT. VALLEY - DAY"),
        None,
        (ACTION, "Continued gunfire echoes."),
        None,
        (ACTION, "CONTINUED: (2)"),
        (ACTION, "CONTINUED: INT. VALLEY - DAY"),
    ]
    screenplay = parse_text(layout(rows))

    assert len(screenplay.scenes) == 1  # a merged CONTINUED: heading is not a second scene
    first = screenplay.scenes[0].elements[0]
    assert first.text == "Continued gunfire echoes."
    for e in screenplay.scenes[0].elements:
        source = screenplay.text.split("\n")[e.span.line_start - 1 : e.span.line_end]
        assert " ".join(line.strip() for line in source) == e.text


def test_every_element_span_slices_back_to_exactly_its_text(screenplay: Screenplay) -> None:
    lines = screenplay.text.split("\n")
    for scene in screenplay.scenes:
        for element in scene.elements:
            source = lines[element.span.line_start - 1 : element.span.line_end]
            assert " ".join(line.strip() for line in source) == element.text


def test_spans_report_the_real_page(screenplay: Screenplay) -> None:
    last_speech = screenplay.scenes[1].elements[-1]
    assert last_speech.span.page == 2
    assert screenplay.scenes[2].span == Span(
        page=2, line_start=len(PAGE_1) + 5, line_end=len(PAGE_1) + 7
    )
    assert screenplay.scenes[0].elements[0].span == Span(page=1, line_start=7, line_end=8)


# --- errors ------------------------------------------------------------------------


def test_text_with_no_scene_headings_is_an_error_not_an_empty_screenplay() -> None:
    with pytest.raises(ScriptParseError, match="no scene headings") as caught:
        parse_text(layout([(ACTION, "Just some prose."), (ACTION, "No headings at all.")]))
    assert caught.value.code == "no_headings"


def test_a_pdf_with_text_but_no_headings_says_no_headings() -> None:
    with pytest.raises(ScriptParseError) as caught:
        parse_pdf(pdf_bytes([[(ACTION, "Just some prose."), (ACTION, "No headings at all.")]]))
    assert caught.value.code == "no_headings"


def test_a_pdf_with_no_text_layer_is_an_error() -> None:
    pdf = FPDF(format="letter")
    pdf.add_page()
    pdf.rect(20, 20, 50, 50)  # drawn, not written: no text layer
    with pytest.raises(ScriptParseError, match="no text layer") as caught:
        parse_pdf(bytes(pdf.output()))
    assert caught.value.code == "no_text_layer"


def test_bytes_that_are_not_a_pdf_are_an_error() -> None:
    with pytest.raises(ScriptParseError, match="not a readable PDF") as caught:
        parse_pdf(b"this is not a pdf")
    assert caught.value.code == "not_a_pdf"


# --- page_starts ---------------------------------------------------------------------


def test_page_starts_is_one_then_each_page_break(screenplay: Screenplay) -> None:
    assert screenplay.page_starts == (1, len(PAGE_1) + 1)
    assert len(screenplay.page_starts) == screenplay.page_count


def test_one_page_text_starts_at_line_one() -> None:
    one = parse_text(layout([heading("1", "INT. ROOM - DAY"), None, (ACTION, "Quiet.")]))
    assert (one.page_starts, one.page_count) == ((1,), 1)


def test_a_real_pdf_reports_where_each_page_starts() -> None:
    parsed = parse_pdf(pdf_bytes([PAGE_1, PAGE_2]))
    lines = parsed.text.split("\n")
    assert parsed.page_starts[0] == 1
    assert len(parsed.page_starts) == parsed.page_count == 2
    # Page 1 ends with its (MORE); page 2's number is its first text.
    split = parsed.page_starts[1] - 1
    first_text = next(i for i, line in enumerate(lines) if i >= split and line.strip())
    assert lines[first_text].strip() == "2."
    assert "(MORE)" in "\n".join(lines[:split])


# --- end to end ----------------------------------------------------------------------


def test_a_real_two_page_pdf_parses_like_its_layout_text() -> None:
    parsed = parse_pdf(pdf_bytes([PAGE_1, PAGE_2]))
    text, breaks = two_page_text()
    expected = parse_text(text, breaks)

    assert parsed.page_count == 2
    assert [s.heading for s in parsed.scenes] == [s.heading for s in expected.scenes]
    assert [[type(e) for e in s.elements] for s in parsed.scenes] == [
        [type(e) for e in s.elements] for s in expected.scenes
    ]
    assert [[e.text for e in s.elements] for s in parsed.scenes] == [
        [e.text for e in s.elements] for s in expected.scenes
    ]
    assert parsed.scenes[1].elements[-1].span.page == 2
    lines = parsed.text.split("\n")
    for scene in parsed.scenes:
        for e in scene.elements:
            source = lines[e.span.line_start - 1 : e.span.line_end]
            assert " ".join(line.strip() for line in source) == e.text


def test_a_blank_line_between_paragraphs_in_a_12pt_pdf_is_never_lost() -> None:
    # T039: pdfplumber's default 13 pt layout rows round some 24 pt gaps (one blank 12 pt line)
    # down to no blank row, and two paragraphs parse as one. 12 pt rows keep every break.
    rows: list[Row] = [heading("1", "INT. ROOM - DAY"), None]
    for i in range(20):
        rows += [
            (ACTION, f"Paragraph {i} begins here and"),
            (ACTION, "wraps onto a second line."),
            None,
        ]
    scene = parse_pdf(pdf_bytes([rows])).scenes[0]

    assert [e.text for e in scene.elements] == [
        f"Paragraph {i} begins here and wraps onto a second line." for i in range(20)
    ]
