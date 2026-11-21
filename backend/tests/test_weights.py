"""Unit tests for the pure weight distribution (plan §10.1)."""
from types import SimpleNamespace

import pytest

from app.weights import WeightError, distribute_shares


def make(offer_id, *, state="active", is_deleted=False, is_pinned=False, pinned_share=None):
    return SimpleNamespace(
        id=offer_id,
        state=state,
        is_deleted=is_deleted,
        is_pinned=is_pinned,
        pinned_share=pinned_share,
    )


def shares(*offers):
    return distribute_shares(list(offers))


def test_single_unpinned():
    assert shares(make(1)) == {1: 100}


def test_two_unpinned():
    assert shares(make(1), make(2)) == {1: 50, 2: 50}


def test_three_unpinned_remainder_goes_last():
    assert shares(make(1), make(2), make(3)) == {1: 33, 2: 33, 3: 34}


def test_four_unpinned():
    assert shares(make(1), make(2), make(3), make(4)) == {1: 25, 2: 25, 3: 25, 4: 25}


def test_seven_unpinned():
    result = shares(*[make(i) for i in range(1, 8)])
    assert result == {1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 15, 7: 15}
    assert sum(result.values()) == 100


def test_pinned_50_plus_one():
    assert shares(make(1, is_pinned=True, pinned_share=50), make(2)) == {1: 50, 2: 50}


def test_pinned_30_plus_one():
    assert shares(make(1, is_pinned=True, pinned_share=30), make(2)) == {1: 30, 2: 70}


def test_add_third_after_pin_50():
    assert shares(
        make(1, is_pinned=True, pinned_share=50), make(2), make(3)
    ) == {1: 50, 2: 25, 3: 25}


def test_add_third_after_pin_30():
    assert shares(
        make(1, is_pinned=True, pinned_share=30), make(2), make(3)
    ) == {1: 30, 2: 35, 3: 35}


def test_two_pins():
    assert shares(
        make(1, is_pinned=True, pinned_share=20),
        make(2, is_pinned=True, pinned_share=30),
        make(3),
    ) == {1: 20, 2: 30, 3: 50}


def test_pinned_overflow():
    with pytest.raises(WeightError) as exc:
        shares(
            make(1, is_pinned=True, pinned_share=60),
            make(2, is_pinned=True, pinned_share=50),
        )
    assert exc.value.code == "PINNED_SHARE_OVERFLOW"


def test_all_pinned_sum_mismatch():
    with pytest.raises(WeightError) as exc:
        shares(
            make(1, is_pinned=True, pinned_share=40),
            make(2, is_pinned=True, pinned_share=50),
        )
    assert exc.value.code == "ALL_PINNED_SUM_MISMATCH"


def test_all_pinned_sum_100():
    assert shares(
        make(1, is_pinned=True, pinned_share=40),
        make(2, is_pinned=True, pinned_share=60),
    ) == {1: 40, 2: 60}


def test_no_remaining_weight():
    with pytest.raises(WeightError) as exc:
        shares(make(1, is_pinned=True, pinned_share=100), make(2))
    assert exc.value.code == "NO_REMAINING_WEIGHT"


def test_insufficient_remaining_weight():
    with pytest.raises(WeightError) as exc:
        shares(
            make(1, is_pinned=True, pinned_share=98),
            make(2),
            make(3),
            make(4),
        )
    assert exc.value.code == "INSUFFICIENT_REMAINING_WEIGHT"


def test_pin_zero_is_allowed():
    assert shares(make(1, is_pinned=True, pinned_share=0), make(2)) == {1: 0, 2: 100}


def test_deleted_offer_excluded():
    assert shares(make(1, is_deleted=True), make(2)) == {2: 100}


def test_all_deleted_is_empty():
    assert shares(make(1, is_deleted=True), make(2, state="disabled")) == {}


def test_disabled_offer_excluded():
    assert shares(make(1, state="disabled"), make(2)) == {2: 100}


@pytest.mark.parametrize("value", [-1, 101])
def test_pinned_share_out_of_range(value):
    with pytest.raises(WeightError) as exc:
        shares(make(1, is_pinned=True, pinned_share=value), make(2))
    assert exc.value.code == "PINNED_SHARE_OUT_OF_RANGE"


def test_pinned_without_share():
    with pytest.raises(WeightError) as exc:
        shares(make(1, is_pinned=True, pinned_share=None), make(2))
    assert exc.value.code == "PINNED_SHARE_MISSING"


def test_deterministic():
    offers = [make(3), make(1), make(2)]
    assert distribute_shares(list(offers)) == distribute_shares(list(offers))


def test_sum_is_always_total():
    for count in range(1, 11):
        result = shares(*[make(i) for i in range(1, count + 1)])
        assert sum(result.values()) == 100
