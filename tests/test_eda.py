"""Pure split-policy and distribution-distance tests."""

from datetime import UTC, datetime, timedelta

import pytest

from mulegraph.eda import SPLITS, split_for
from mulegraph.eda_report import total_variation


@pytest.mark.parametrize("name,start,end", SPLITS)
def test_half_open_split_boundaries(name, start, end):
    assert split_for(start) == name
    assert split_for(end - timedelta(microseconds=1)) == name
    assert split_for(end) != name
    assert split_for(start - timedelta(microseconds=1)) != name


def test_split_policy_contiguous_and_timezone_explicit():
    assert all(a[2] == b[1] for a, b in zip(SPLITS, SPLITS[1:], strict=False))
    assert split_for(datetime(2022, 8, 31, 23, 59)) is None
    assert split_for(datetime(2022, 9, 19)) is None
    with pytest.raises(ValueError, match="timezone"):
        split_for(datetime(2022, 9, 1, tzinfo=UTC))


def test_shift_distance_conditions_on_class_and_handles_empty_groups():
    assert total_variation({"A": 10}, {"A": 1}) == 0
    assert total_variation({"A": 10}, {"B": 1}) == 1
    assert total_variation({"A": 1, "B": 1}, {"B": 2}) == 0.5
    assert total_variation({}, {"B": 2}) is None
