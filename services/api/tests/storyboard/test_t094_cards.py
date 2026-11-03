"""T094: a warned frame's card names every check it failed, hard ones too (a hard check off the
rule ladder warns); a strict-mode card is unchanged (verify.md §3, §9)."""

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.llm import Usage
from app.storyboard.build import frame_of
from app.storyboard.document import _noted  # pyright: ignore[reportPrivateUsage]
from app.verify.model import Audit, Check, CheckResult, FrameOutcome, FrameState, Severity, Verdict


def audit(*checks: CheckResult, verdict: Verdict = Verdict.WARN) -> Audit:
    return Audit((0, 1), 1, 7, None, None, checks, verdict, {}, ("m",), Usage(0, 0, 0))


HARD = CheckResult(Check.UNSCRIPTED_PERSON, Severity.HARD, False, "person 1")
SOFT = CheckResult(Check.LIGHT, Severity.SOFT, False, "day light")
OK = CheckResult(Check.SETTING, Severity.HARD, True, "")


def test_a_warned_frame_names_hard_and_soft_failures() -> None:
    outcome = FrameOutcome((0, 1), FrameState.WARNED, None, (audit(HARD, SOFT, OK),))
    assert frame_of(outcome, None).noted_checks == (Check.UNSCRIPTED_PERSON, Check.LIGHT)


def test_a_withheld_frame_names_its_hard_failures_only() -> None:
    outcome = FrameOutcome(
        (0, 1), FrameState.WITHHELD, None, (audit(HARD, SOFT, verdict=Verdict.FAIL),)
    )
    assert frame_of(outcome, None).noted_checks == (Check.UNSCRIPTED_PERSON,)


def test_the_document_reads_a_stored_row_the_same_way() -> None:
    row = SimpleNamespace(
        checks=[
            {"check": "unscripted_person", "severity": "hard", "ok": False, "detail": "x"},
            {"check": "light", "severity": "soft", "ok": False, "detail": "y"},
            {"check": "setting", "severity": "hard", "ok": True, "detail": ""},
        ]
    )
    assert _noted(FrameState.WARNED, row) == (Check.UNSCRIPTED_PERSON, Check.LIGHT)  # type: ignore[arg-type]
    assert _noted(FrameState.WITHHELD, row) == (Check.UNSCRIPTED_PERSON,)  # type: ignore[arg-type]


def test_a_misspelt_rule_stops_the_settings_loading() -> None:
    with pytest.raises(ValueError, match="no_charcter"):
        Settings(audit_withhold_checks="no_charcter")
