"""T117: balloon voices from the script's own words (comic.md §3, §4 steps 7-8, §6). Every word is
lettered as before; only the outline changes, and only where the script says so."""

import math

import pytest
from PIL import Image, ImageDraw

from app.comic import (
    Bubble,
    BubbleKind,
    Caption,
    CaptionKind,
    Panel,
    Voice,
    bubbles,
    place_lettering,
    render,
    to_json,
    voice_of,
)
from app.comic.bubbles import radio_zigzag, tail_hull, tail_triangle, tails_cross, thought_trail
from app.script import Dialogue, Span
from app.verify.model import HeadSeen
from tests.comic.test_t112 import framed, panel_of, second

SPAN = Span(1, 1, 1)
to_mouth = bubbles._to_mouth  # pyright: ignore[reportPrivateUsage]
letter = render._letter  # pyright: ignore[reportPrivateUsage]


def say(cue: str, text: str, extension: str | None = None, note: str | None = None) -> Dialogue:
    return Dialogue(cue, extension, note, text, SPAN)


# --- voice_of: the script's words only ------------------------------------------------------------


@pytest.mark.parametrize(
    ("dialogue", "voice"),
    [
        # the samples' own lines
        (say("LERATO", "There you are.", None, "whispering"), Voice.WHISPER),
        (say("MRS. ABRAHAMS", "Come in before you drown.", None, "quietly"), Voice.WHISPER),
        (say("PRIYA", "No. No, no, no.", None, "under her breath"), Voice.WHISPER),
        (
            say(
                "SIPHO",
                "Where?",
                None,
                "barely audible over the storm, and not quite looking at her",
            ),
            Voice.WHISPER,
        ),
        (say("LWAZI", "Mrs. Abrahams, the plants!", None, "shouting over the rain"), Voice.SHOUT),
        (say("REFILWE", "My dog is in the drain!", "V.O.", "on the phone, crying"), Voice.RADIO),
        (say("AUNT LINDIWE", "Hello? Zodwa?", "V.O.", "on the phone"), Voice.RADIO),
        (say("RADIO ANNOUNCER", "Strong winds this afternoon.", "V.O."), Voice.RADIO),
        (
            say("MS. NAIDOO", "One last inspection.", None, "into her phone, on speaker"),
            Voice.PLAIN,
        ),
        (
            say("COASTGUARD", "All vessels, all vessels.", "V.O."),
            Voice.PLAIN,
        ),  # device only in the action
        (say("BONGANI", "R, O, U, N, D...", None, "to himself"), Voice.PLAIN),
        (say("LERATO", "I promise.", None, "smiling"), Voice.PLAIN),
        # the other lists, and the extension
        (say("NANDI", "He never listens.", None, "thinking"), Voice.THOUGHT),
        (say("NANDI", "He never listens.", "THINKING"), Voice.THOUGHT),
        (say("NANDI", "He never listens.", None, "in her head"), Voice.THOUGHT),
        (say("NANDI", "I can't.", None, "weakly"), Voice.DISTRESS),
        (say("NANDI", "I can't.", None, "through tears"), Voice.DISTRESS),
        (say("NANDI", "Hello?", "FILTERED"), Voice.RADIO),
        (say("NANDI", "Hello?", "ON THE PHONE"), Voice.RADIO),
        (say("NANDI", "Help!", None, "screaming"), Voice.SHOUT),
        # first that applies; whole words only
        (say("NANDI", "Run.", None, "thinking, then shouting"), Voice.THOUGHT),
        (say("NANDI", "Run.", None, "shouting, then whispering"), Voice.SHOUT),
        (say("NANDI", "Fine.", None, "thoughtful"), Voice.PLAIN),
        (say("NANDI", "Fine.", None, "shoutless"), Voice.PLAIN),
        (say("NANDI", "HELP!"), Voice.PLAIN),  # capitals and "!" are not a shout the script states
    ],
)
def test_voice_of_reads_the_scripts_words(dialogue: Dialogue, voice: Voice) -> None:
    assert voice_of(dialogue) is voice


def lettering(*lines: Dialogue) -> Panel:
    screenplay, plan, book = panel_of(*lines)
    return second(place_lettering(book, screenplay, plan, framed(book)))


def test_narrator_is_a_narration_box_and_a_radio_voice_over_a_broadcast_box() -> None:
    panel = lettering(
        say("NARRATOR", "That night the kite stayed up."),
        say("RADIO ANNOUNCER", "Strong winds this afternoon.", "V.O."),
        say("LERATO", "I know.", "V.O.", "whispering"),
    )
    assert panel.bubbles == ()
    assert [(c.kind, c.voice, c.text) for c in panel.captions] == [
        (CaptionKind.VOICE_OVER, Voice.PLAIN, "That night the kite stayed up."),
        (CaptionKind.VOICE_OVER, Voice.RADIO, "Strong winds this afternoon."),
        (CaptionKind.VOICE_OVER, Voice.PLAIN, "I know."),  # a caption carries no delivery
    ]


def test_a_voice_over_thought_is_a_bubble_in_the_panel() -> None:
    panel = lettering(say("LERATO", "He never listens.", "V.O.", "thinking"))
    (bubble,) = panel.bubbles
    assert (bubble.kind, bubble.voice, bubble.text) == (
        BubbleKind.SPEECH,
        Voice.THOUGHT,
        "He never listens.",
    )


def test_the_json_carries_the_voice_and_every_word() -> None:
    screenplay, plan, book = panel_of(
        say("LWAZI", "Mrs. Abrahams, the plants!", None, "shouting over the rain"),
        say("RADIO ANNOUNCER", "Strong winds this afternoon.", "V.O."),
    )
    placed = place_lettering(book, screenplay, plan, framed(book))
    data = to_json(placed, {})
    panel = data["pages"][0]["panels"][1]  # type: ignore[index]
    assert panel["bubbles"][0]["voice"] == "shout"  # type: ignore[index]
    assert panel["bubbles"][0]["text"] == "Mrs. Abrahams, the plants!"  # type: ignore[index]
    assert panel["captions"][0]["voice"] == "radio"  # type: ignore[index]


# --- tails by voice -------------------------------------------------------------------------------

BOX = (100, 100, 300, 80)
TIP = (700, 500)


def test_the_thought_trail_is_three_circles_on_the_line_to_the_tip() -> None:
    circles = thought_trail(BOX, TIP)
    assert [r for _, _, r in circles] == [12.0, 8.0, 5.0]
    (x0, y0, _), (x1, y1, _), (x2, y2, _) = circles
    # on one line, toward the tip, each past the box
    assert abs((x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)) < 1e-6
    assert x0 < x1 < x2 < TIP[0] and y0 < y1 < y2 < TIP[1]
    assert x0 > BOX[0] + BOX[2] - 1 or y0 > BOX[1] + BOX[3] - 1
    assert thought_trail(BOX, (150, 120)) == ()


def test_the_radio_zigzag_runs_base_to_tip_with_three_kinks() -> None:
    zigzag = radio_zigzag(BOX, TIP)
    assert len(zigzag) == 5 and zigzag[-1] == (700.0, 500.0)
    triangle = tail_triangle(BOX, TIP)
    assert triangle is not None
    base = ((triangle[0][0] + triangle[2][0]) / 2, (triangle[0][1] + triangle[2][1]) / 2)
    assert math.isclose(zigzag[0][0], base[0]) and math.isclose(zigzag[0][1], base[1])
    assert radio_zigzag(BOX, (150, 120)) == ()


@pytest.mark.parametrize("voice", list(Voice))
def test_the_hull_holds_everything_drawn(voice: Voice) -> None:
    hull = tail_hull(voice, BOX, TIP)
    assert hull is not None
    if voice is Voice.THOUGHT:
        drawn = [
            (cx + q * math.cos(a / 16 * math.tau), cy + q * math.sin(a / 16 * math.tau))
            for cx, cy, r in thought_trail(BOX, TIP)
            for q in (r * 0.999,)  # the octagon touches the circle: float error at the touch
            for a in range(16)
        ]
    elif voice is Voice.RADIO:
        drawn = list(radio_zigzag(BOX, TIP))
    else:
        triangle = tail_triangle(BOX, TIP)
        assert triangle is not None and hull == triangle  # T112's triangle, unchanged
        drawn = list(triangle)
    for point in drawn:  # a point inside a convex shape shares a point with it
        assert tails_cross(hull, ((point[0], point[1]), (point[0] + 0.01, point[1]), point))


def test_a_thought_aims_at_the_heads_centre_not_the_mouth() -> None:
    screenplay, plan, book = panel_of(say("LERATO", "He never listens.", None, "thinking"))
    head = HeadSeen(0, "LERATO", (0.7, 0.3, 0.82, 0.6))
    placed = second(place_lettering(book, screenplay, plan, framed(book, (head,))))
    (bubble,) = placed.bubbles
    from fractions import Fraction

    assert bubble.tail == to_mouth(head, placed.rect, bubble.rect, Fraction(1, 2))
    assert bubble.tail != to_mouth(head, placed.rect, bubble.rect)


# --- drawing: inside the box ----------------------------------------------------------------------


@pytest.mark.parametrize("voice", list(Voice))
def test_every_balloon_is_drawn_inside_its_box_grown_by_the_outline(voice: Voice) -> None:
    rect = (60, 60, 320, 110)
    image = Image.new("RGB", (440, 230), (128, 128, 128))
    item: Bubble | Caption = Bubble(
        BubbleKind.SPEECH, "NANDI", "Hold the light steady.", 0, SPAN, rect, None, 32, voice
    )
    if voice is Voice.RADIO:  # the broadcast box is a caption too
        letter(
            ImageDraw.Draw(image),
            Panel(
                0,
                1,
                (0, 0, 440, 230),
                (),
                (Caption(CaptionKind.VOICE_OVER, "Hold.", 0, SPAN, rect, 32, voice),),
            ),
        )
        drawn = Image.eval(image, lambda v: 0 if v == 128 else 255).convert("L").getbbox()
        assert drawn is not None and drawn[0] >= 60 - 4 and drawn[2] <= 60 + 320 + 4
        image = Image.new("RGB", (440, 230), (128, 128, 128))
    letter(ImageDraw.Draw(image), Panel(0, 1, (0, 0, 440, 230), (item,), ()))
    drawn = Image.eval(image, lambda v: 0 if v == 128 else 255).convert("L").getbbox()
    assert drawn is not None
    x, y, w, h = rect
    grow = 4  # the 3 px outline, and a pixel of antialiasing
    assert x - grow <= drawn[0] and y - grow <= drawn[1]
    assert drawn[2] <= x + w + grow and drawn[3] <= y + h + grow
