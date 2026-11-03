"""normalise_ranges: shots.md §4. Whatever the model proposes, the result partitions the scene."""

import random

import pytest

from app.shots import normalise_ranges


@pytest.mark.parametrize(
    ("proposed", "n", "expected", "repairs"),
    [
        ([(0, 1), (2, 3)], 4, [(0, 1), (2, 3)], 0),  # already a partition
        ([(2, 3), (0, 1)], 4, [(0, 1), (2, 3)], 0),  # order alone isn't a repair
        ([(0, 0), (2, 3)], 4, [(0, 0), (1, 3)], 1),  # a gap goes to the shot after it
        ([(0, 2), (1, 3)], 4, [(0, 2), (3, 3)], 1),  # an overlap is trimmed
        ([(3, 1)], 4, [(0, 3)], 1),  # reversed, then the head is covered
        ([(0, 9)], 4, [(0, 3)], 1),  # out of bounds
        ([(-2, 0), (1, 1)], 2, [(0, 0), (1, 1)], 1),  # negative
        ([(0, 3), (0, 3)], 4, [(0, 3)], 1),  # a duplicate is dropped
        ([(0, 0)], 3, [(0, 2)], 1),  # an uncovered tail extends the last shot
        ([], 3, [(0, 2)], 1),  # nothing usable: one shot covers the scene
        ([], 0, [], 0),  # an empty scene has nothing to cover
    ],
)
def test_normalise_ranges(
    proposed: list[tuple[int, int]], n: int, expected: list[tuple[int, int]], repairs: int
) -> None:
    assert normalise_ranges(proposed, n) == (expected, repairs)


def test_any_proposal_becomes_a_partition() -> None:
    rng = random.Random(7)
    for _ in range(500):
        n = rng.randint(1, 12)
        proposed = [
            (rng.randint(-3, n + 3), rng.randint(-3, n + 3)) for _ in range(rng.randint(0, 8))
        ]
        ranges, _ = normalise_ranges(proposed, n)
        covered = [i for first, last in ranges for i in range(first, last + 1)]
        assert covered == list(range(n)), (proposed, n, ranges)
