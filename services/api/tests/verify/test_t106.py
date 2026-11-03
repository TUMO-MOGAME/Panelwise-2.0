"""T106 and T107: the describer's setting rule and text rule, worded as verify.md §3 has them
verbatim. The schema is unchanged; only `DESCRIBE_PROMPT` moves."""

from app.grounding import Extraction
from app.script import Screenplay
from app.verify import Check, Verdict, run_checks
from app.verify.prompts import DESCRIBE_PROMPT
from app.verify.schema import FrameDescription
from tests.verify.conftest import described, judged, kitchen_shot

SETTING = (
    "Say whether the scene is interior or exterior: exterior when the place is open to the sky "
    "(a rooftop, a balcony, a yard, a street), even if the sky is left blank; interior only when "
    "walls and a ceiling close it in; unclear when you can't tell."
)
TEXT = (
    "Under text, write out word for word each piece of writing you can read in the scene, as it "
    "is written: signs, labels, screens, paper, clothing, sound effects. Leave out scribbles, "
    "marks that aren't letters, and the artist's signature or initials even when you can read "
    "them: those go under signature, not text."
)


def test_a_place_open_to_the_sky_is_exterior_even_with_the_sky_blank() -> None:
    assert SETTING in DESCRIBE_PROMPT
    assert "interior or exterior, and its light" not in DESCRIBE_PROMPT  # the old run-on sentence
    assert "Give its light: day, night, dawn_or_dusk, or unclear." in DESCRIBE_PROMPT


def test_a_signature_s_letters_never_go_under_text() -> None:
    assert TEXT in DESCRIBE_PROMPT
    assert "a signature you can't read" not in DESCRIBE_PROMPT  # the old rule kept legible ones
    # the signature flag itself is unchanged (T072)
    assert (
        "Set signature to true if a signature, initials or an artist's mark appears anywhere, "
        "readable or not." in DESCRIBE_PROMPT
    )


def test_the_schema_is_unchanged() -> None:
    schema = FrameDescription.model_json_schema()
    assert schema["properties"]["setting"]["$ref"].endswith("Setting") or "enum" in str(
        schema["properties"]["setting"]
    )
    assert set(schema["required"]) >= {"setting", "text", "signature", "has_text"}


# --- T107: the signature's own slot -----------------------------------------------------------


def test_the_signature_and_its_letters_come_before_the_text() -> None:
    fields = list(FrameDescription.model_fields)
    assert fields.index("signature") < fields.index("signature_text") < fields.index("has_text")
    assert fields.index("has_text") < fields.index("text")
    schema = FrameDescription.model_json_schema()
    assert list(schema["properties"]).index("signature_text") < list(schema["properties"]).index(
        "text"
    )


def test_the_model_must_fill_signature_text_but_an_old_row_reads_without_it() -> None:
    schema = FrameDescription.model_json_schema()
    assert "signature_text" in schema["required"]
    assert schema["properties"]["signature_text"]["type"] == "array"
    assert "never the artist's signature" in schema["properties"]["text"]["description"]
    stored = {  # a description written before T107
        "people": [], "setting": "exterior", "light": "day", "shot_size": "wide", "objects": [],
        "has_text": True, "text": ["SNAP."], "signature": True,
    }  # fmt: skip
    assert FrameDescription.model_validate(stored).signature_text == []


def test_a_signature_s_letters_are_no_lettering(
    screenplay: Screenplay, extraction: Extraction
) -> None:
    checks, verdict, _ = run_checks(
        kitchen_shot(),
        screenplay.scenes[0],
        described(signature=True, signature_text=["Muller"], text=[]),
        judged(),
        extraction,
    )
    failed = {c.check for c in checks if not c.ok}
    assert failed == {Check.SIGNATURE}  # signed, but no TEXT_IN_FRAME for its letters
    assert verdict is Verdict.WARN
