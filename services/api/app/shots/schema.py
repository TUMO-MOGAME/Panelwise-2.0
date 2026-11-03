"""What the model is asked for, as a strict json_schema: element ranges, a camera vocabulary and
names only. No free-text frame description: that is where FrameFlow's shots invented lighting
and detail the script never gave (shots.md §8)."""

from pydantic import BaseModel, Field

from app.shots.model import Framing, Movement


class ProposedShot(BaseModel):
    first: int = Field(description="Index of the first element this shot covers")
    last: int = Field(description="Index of the last element this shot covers")
    framing: Framing
    movement: Movement
    characters: list[str] = Field(description="Names from 'Characters in this scene' in frame")
    props: list[str] = Field(description="Names from 'Props in this scene' in frame")
    rationale: str = Field(description="One short sentence: why this framing for these lines")


class ScenePlan(BaseModel):
    shots: list[ProposedShot]
