"""Jobs: work that outlives a request, stored so it survives a restart. docs/design/deploy.md §3."""

from app.jobs.model import RESTARTED, JobKind, JobRow, JobState
from app.jobs.repo import fail_interrupted, fail_interrupted_frames

__all__ = [
    "RESTARTED",
    "JobKind",
    "JobRow",
    "JobState",
    "fail_interrupted",
    "fail_interrupted_frames",
]
