"""The two model calls, as strict json_schema. docs/design/verify.md §3, §6.

The describer's schema has no field for a name: it can only say what it sees. The judge's has
nothing but index calls and verbatim support, which code checks (verify.md §8).
"""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.verify.model import Light, ObjectCategory, ObjectKind, Position, Setting, ShotSize


class SeenPerson(BaseModel):
    position: Position = Field(description="Where the person stands in the frame")
    appearance: str = Field(description="A short phrase: what the person looks like")


class SeenObject(BaseModel):
    name: str = Field(description="What the object is, in a word or two")
    category: ObjectCategory
    held: bool = Field(description="Whether someone in the frame holds it")


def _require_signature_text(schema: dict[str, Any]) -> None:
    """T107: the model must always fill signature_text ([] when there's none to read), though a
    description stored before T107 validates without it."""
    schema["required"] = [*schema.get("required", []), "signature_text"]


class FrameDescription(BaseModel):
    people: list[SeenPerson]
    setting: Setting
    light: Light
    shot_size: ShotSize
    objects: list[SeenObject]
    # T107: the signature and its letters come before the text: the model writes in this order,
    # and with text first it put a legible signature there before calling it a signature
    signature: bool = Field(
        description="Whether a signature, initials or an artist's mark appears, readable or not"
    )
    signature_text: list[str] = Field(
        default_factory=list,  # a description stored before T107 has none
        description="The letters of the artist's signature or initials, if you can read them",
    )
    has_text: bool = Field(description="Whether any text, letters or numbers appear in the image")
    text: list[str] = Field(
        description=(
            "The scene's lettering, word for word: signs, labels, screens, paper, clothing, sound "
            "effects; never the artist's signature or initials; none for marks you can't read"
        )
    )

    model_config = ConfigDict(json_schema_extra=_require_signature_text)


@dataclass(frozen=True)
class DescriptionLimits:
    """T109: how long the describer's lists and strings may run (verify.md § T109 contracts)."""

    people: int
    objects: int
    text: int
    text_chars: int
    appearance_chars: int
    object_name_chars: int
    signature: int
    signature_chars: int


# Above every honest answer stored (DeepSeek: 21 people, 32 objects; Super VL: 33 text entries).
# A loop now stops at a limit: the measured ones ended at 351-1,597 tokens of the 4,096.
# A signature is a name or initials, never a paragraph: 5 entries of 60 (Katlego, #212).
DESCRIPTION_LIMITS = DescriptionLimits(
    people=24,
    objects=40,
    text=40,
    text_chars=100,
    appearance_chars=200,
    object_name_chars=60,
    signature=5,
    signature_chars=60,
)


def description_grammar(limits: DescriptionLimits = DESCRIPTION_LIMITS) -> dict[str, Any]:
    """T109: FrameDescription's schema with length limits, for the decoder only. Super VL can loop
    at temperature 0 until max_tokens cuts the JSON; with these a looping list or string stops at
    its limit. The model's own schema (the prompt's text, the validation) is left as it is."""
    grammar = FrameDescription.model_json_schema()  # a new dict on every call
    props, defs = grammar["properties"], grammar["$defs"]
    props["people"]["maxItems"] = limits.people
    props["objects"]["maxItems"] = limits.objects
    props["text"]["maxItems"] = limits.text
    props["text"]["items"]["maxLength"] = limits.text_chars
    props["signature_text"]["maxItems"] = limits.signature  # T107's slot (§3)
    props["signature_text"]["items"]["maxLength"] = limits.signature_chars
    defs["SeenPerson"]["properties"]["appearance"]["maxLength"] = limits.appearance_chars
    defs["SeenObject"]["properties"]["name"]["maxLength"] = limits.object_name_chars
    return grammar


class PersonCall(BaseModel):
    person: int = Field(description="0-based index into the description's people")
    character: str | None = Field(description="The shot character this person is, or null")
    support: str | None = Field(
        description="Only for a person who is no character: a verbatim quote that puts them there"
    )


class ObjectCall(BaseModel):
    object: int = Field(description="0-based index into the description's objects")
    kind: ObjectKind
    support: str | None = Field(
        description="A verbatim quote: the text or an entity quote for a scripted prop, the "
        "scene heading's words for set dressing"
    )


class Judgement(BaseModel):
    people: list[PersonCall]
    objects: list[ObjectCall]


class PersonCheck(BaseModel):
    """The sex agent's answer (T095): how one person is drawn, from the drawing alone."""

    sex: Literal["male", "female", "unclear"]


class Layout(BaseModel):
    """The layout agent's answer (T104): the frame's panels, the [a, b] pairs of numbered people
    who are one person drawn twice, and a short reason."""

    panels: int
    copies: list[list[int]]
    reason: str


class Presence(BaseModel):
    """The presence agent's answer (T099): which numbered described person is the character,
    or None, and a short reason."""

    person: int | None
    reason: str


class HeadAnswer(BaseModel):
    """One numbered person's head (T097): whether it is in view, and its box as fractions of the
    image's width and height from its top-left."""

    person: int
    visible: bool
    x0: float
    y0: float
    x1: float
    y1: float


class HeadCheck(BaseModel):
    """The head agent's answer (T097): a head for each numbered person."""

    heads: list[HeadAnswer]
