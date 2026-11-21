"""Pure offer weight distribution. No database, HTTP or Pydantic here.

Rules (see docs/implementation-plans/campaign-editor.md §6):

- only active offers participate: ``not is_deleted`` and ``state == "active"``;
- pinned offers keep their ``pinned_share`` unchanged;
- the remaining weight is split between unpinned offers as evenly as possible,
  integer only, remainder given one percent to the last offers by ``id``;
- the result always sums to exactly ``total`` for a non-empty active list.
"""
from __future__ import annotations


class WeightError(ValueError):
    """An impossible pin/weight combination. ``code`` is part of the API contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def is_active(offer) -> bool:
    return not offer.is_deleted and (offer.state or "active") == "active"


def distribute_shares(offers, total: int = 100) -> dict[int, int]:
    """Return ``{offer_id: share}`` for active offers only.

    Does not mutate the input objects. Raises :class:`WeightError` when the
    combination cannot be satisfied without changing pinned weights.
    """
    active = [offer for offer in offers if is_active(offer)]
    active.sort(key=lambda offer: offer.id)

    if not active:
        return {}

    pinned = [offer for offer in active if offer.is_pinned]
    unpinned = [offer for offer in active if not offer.is_pinned]

    for offer in pinned:
        if offer.pinned_share is None:
            raise WeightError("PINNED_SHARE_MISSING", "У закреплённого оффера не задан вес")
        if not (0 <= offer.pinned_share <= total):
            raise WeightError(
                "PINNED_SHARE_OUT_OF_RANGE",
                f"Вес закреплённого оффера {offer.pinned_share}% вне допустимого диапазона 0..{total}",
            )

    pinned_total = sum(offer.pinned_share for offer in pinned)
    if pinned_total > total:
        raise WeightError(
            "PINNED_SHARE_OVERFLOW",
            f"Сумма закреплённых весов {pinned_total}% превышает {total}%",
        )

    result = {offer.id: offer.pinned_share for offer in pinned}

    if not unpinned:
        if pinned_total != total:
            raise WeightError(
                "ALL_PINNED_SUM_MISMATCH",
                f"Все офферы закреплены, но сумма {pinned_total}% ≠ {total}%",
            )
        return result

    remaining = total - pinned_total
    if remaining <= 0:
        raise WeightError(
            "NO_REMAINING_WEIGHT",
            "Не осталось веса для незакреплённых офферов",
        )
    if remaining < len(unpinned):
        raise WeightError(
            "INSUFFICIENT_REMAINING_WEIGHT",
            f"Остаток {remaining}% нельзя распределить на {len(unpinned)} офферов",
        )

    base, extra = divmod(remaining, len(unpinned))
    for offer in unpinned:
        result[offer.id] = base
    # Deterministic: the remainder goes to the last offers in ``Offer.id`` order.
    for offer in unpinned[len(unpinned) - extra:]:
        result[offer.id] += 1

    return result
