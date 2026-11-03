"""T111's measurement tool: the scoring against the eye labels (docs/design/limb-agent.md §8, §9).
Pure: no Storage, no model."""

from tools.measure_limbs import Ask, Drawing, Label, score


def label(asset: str, verdict: str, source: str = "labelled-109", framing: str | None = "wide",
          faults: tuple[str, ...] = ()) -> Label:  # fmt: skip
    return Label(asset, source, verdict, faults, framing)


def named(defect: bool, hands: bool = False) -> Ask:
    return Ask(ok=True, named=defect, hands=hands)


FAILED = Ask(ok=False, named=False, hands=False)


def test_recall_and_false_alarms_count_each_ask() -> None:
    labels = [label("a", "defect", faults=("extra_arm",)), label("b", "normal")]
    answers = {
        "a": Drawing(people=2, asks=(named(True), named(True))),
        "b": Drawing(people=1, asks=(named(True), named(False))),
    }
    got = score(labels, answers, repeat=2)["base"]
    assert (got.caught, got.defect_asks) == (2, 2)
    assert (got.alarms, got.normal_asks) == (1, 2)
    assert (got.agreed, got.compared) == (1, 2)  # a agrees with itself, b doesn't


def test_unclear_labels_are_left_out() -> None:
    labels = [label("a", "unclear")]
    got = score(labels, {"a": Drawing(people=1, asks=(named(True), named(True)))}, repeat=2)["base"]
    assert got.defect_asks == got.normal_asks == got.compared == 0


def test_a_failed_ask_is_an_error_and_counts_in_no_rate() -> None:
    labels = [label("a", "defect", faults=("two_heads",))]
    got = score(labels, {"a": Drawing(people=1, asks=(FAILED, named(True)))}, repeat=2)["base"]
    assert (got.errors, got.asks) == (1, 2)
    assert (got.caught, got.defect_asks) == (1, 1)
    assert got.compared == 0  # one good ask: nothing to compare


def test_a_drawing_with_no_described_people_is_never_asked_and_a_defect_there_is_missed() -> None:
    labels = [label("a", "defect", faults=("fused_bodies",)), label("b", "normal")]
    answers = {"a": Drawing(people=0, asks=()), "b": Drawing(people=0, asks=())}
    got = score(labels, answers, repeat=2)["base"]
    assert (got.caught, got.defect_asks) == (0, 2)  # missed on both asks it never got
    assert (got.alarms, got.normal_asks) == (0, 0)  # nothing asked, nothing raised
    assert got.not_asked == 2


def test_hunted_drawings_are_scored_apart_and_by_framing() -> None:
    labels = [
        label("a", "defect", faults=("extra_leg",), framing="wide"),
        label("b", "defect", faults=("extra_leg",), framing="close_up"),
        label("h", "defect", source="hunt", framing=None, faults=("two_heads",)),
    ]
    answers = {
        "a": Drawing(people=1, asks=(named(False), named(False))),
        "b": Drawing(people=1, asks=(named(True), named(True))),
        "h": Drawing(people=1, asks=(named(True), named(True))),
    }
    got = score(labels, answers, repeat=2)
    assert (got["base"].caught, got["base"].defect_asks) == (2, 4)
    assert (got["hunt"].caught, got["hunt"].defect_asks) == (2, 2)
    assert (got["framing:wide"].caught, got["framing:close_up"].caught) == (0, 2)
    assert "framing:None" not in got  # a hunted drawing has no framing and joins no framing row


def test_hands_are_scored_apart_from_the_body() -> None:
    labels = [label("a", "defect", faults=("deformed_hands",)), label("b", "normal")]
    answers = {
        "a": Drawing(people=1, asks=(named(False, hands=True), named(False, hands=True))),
        "b": Drawing(people=1, asks=(named(False, hands=True), named(False))),
    }
    got = score(labels, answers, repeat=2)["base"]
    assert (got.hands_caught, got.hands_asks) == (2, 2)
    assert (got.hands_alarms, got.hands_normal_asks) == (1, 2)
    # a drawing whose only fault is a hand is not a body defect
    assert got.defect_asks == 0 and (got.alarms, got.normal_asks) == (0, 2)
