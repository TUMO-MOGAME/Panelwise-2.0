"""The shot planner. Design: docs/design/shots.md."""

from app.shots.model import Framing, Movement, PlanReport, Shot, ShotError, ShotPlan
from app.shots.planner import SYSTEM_PROMPT, normalise_ranges, plan_shots, render_scene
from app.shots.schema import ProposedShot, ScenePlan

__all__ = [
    "SYSTEM_PROMPT",
    "Framing",
    "Movement",
    "PlanReport",
    "ProposedShot",
    "ScenePlan",
    "Shot",
    "ShotError",
    "ShotPlan",
    "normalise_ranges",
    "plan_shots",
    "render_scene",
]
