"""Exact, strictly-prior account history, bounded to one account at a time."""

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from itertools import groupby
from typing import NamedTuple

from mulegraph.eda import split_for

SCALE = Decimal("0.000000001")


class Event(NamedTuple):
    bank: str
    account: str
    timestamp: datetime
    source_row: int
    role: str
    other_bank: str
    other_account: str
    amount: Decimal
    currency: str
    amount_paid: Decimal | None = None
    amount_received: Decimal | None = None
    payment_currency: str | None = None
    receiving_currency: str | None = None
    payment_format: str | None = None


def money(value: Decimal) -> Decimal:
    """Fail rather than round values outside the versioned Decimal128 contract."""
    with localcontext() as context:
        context.prec = 60
        if not value.is_finite() or value < 0 or value >= Decimal("1e29"):
            raise ValueError("Money outside nonnegative DECIMAL(38,9) range")
        rounded = value.quantize(SCALE)
        if rounded != value:
            raise ValueError("Money would lose precision in DECIMAL(38,9)")
        return rounded


def adjust(target: dict, changes: dict, sign: int) -> None:
    for key, (count, amount) in changes.items():
        target[key][0] += sign * count
        target[key][1] += sign * amount
        if target[key][0] == 0:
            del target[key]


def amounts() -> defaultdict:
    return defaultdict(lambda: [0, Decimal(0)])


class Window:
    def __init__(self, hours: int) -> None:
        self.duration = timedelta(hours=hours)
        self.groups: deque = deque()
        self.count = 0
        self.money = amounts()

    def expire(self, timestamp: datetime) -> None:
        # Lower boundary is inclusive: [T-window, T).
        while self.groups and self.groups[0][0] < timestamp - self.duration:
            _, count, values = self.groups.popleft()
            self.count -= count
            adjust(self.money, values, -1)

    def add(self, timestamp: datetime, count: int, values: dict) -> None:
        self.groups.append((timestamp, count, values))
        self.count += count
        adjust(self.money, values, 1)


def account_features(events: Iterable[Event]) -> Iterator[tuple[str, dict]]:
    """Input sorted by composite account then time; peers always see pre-T state."""
    previous = None
    with localcontext() as context:
        context.prec = 60
        for identity, account_events in groupby(
            events, key=lambda e: (e.bank, e.account)
        ):
            if previous is not None and identity <= previous:
                raise ValueError("Account input must be strictly sorted")
            previous = identity
            total = sent = received = 0
            first = last = None
            counterparties: set[tuple[str, str]] = set()
            lifetime = amounts()
            windows = [Window(1), Window(24)]
            for timestamp, peers in groupby(account_events, key=lambda e: e.timestamp):
                if last is not None and timestamp <= last:
                    raise ValueError("Account timestamps must be strictly grouped")
                group = list(peers)
                split = split_for(timestamp)
                if split is None:
                    raise ValueError("Transaction outside approved splits")
                for window in windows:
                    window.expire(timestamp)
                # Emit EVERY peer before updating any historical state.
                for event in group:
                    money(event.amount)
                    key = (event.role, event.currency)
                    old = lifetime.get(key, (0, Decimal(0)))
                    hour = windows[0].money.get(key, (0, Decimal(0)))
                    day = windows[1].money.get(key, (0, Decimal(0)))
                    row = {
                        "source_row": event.source_row,
                        "occurred_at": timestamp,
                        "split": split,
                        "history_count": total,
                        "sent_count": sent,
                        "received_count": received,
                        "count_1h": windows[0].count,
                        "count_24h": windows[1].count,
                        "unique_counterparties": len(counterparties),
                        "last_activity_at": last,
                        "seconds_since_last": (timestamp - last).total_seconds()
                        if last is not None
                        else None,
                        "history_age_seconds": (timestamp - first).total_seconds()
                        if first is not None
                        else None,
                        "mean_gap_seconds": (last - first).total_seconds() / (total - 1)
                        if total > 1
                        else None,
                        "frequency_1h": float(windows[0].count),
                        "frequency_24h": windows[1].count / 24,
                        "currency_history_count": old[0],
                        "currency_history_sum": money(old[1]),
                        "currency_count_1h": hour[0],
                        "currency_sum_1h": money(hour[1]),
                        "currency_count_24h": day[0],
                        "currency_sum_24h": money(day[1]),
                    }
                    if event.role == "sender":
                        row.update(
                            {
                                "from_bank_id": event.bank,
                                "from_account": event.account,
                                "to_bank_id": event.other_bank,
                                "to_account": event.other_account,
                                "amount_paid": money(event.amount_paid),
                                "amount_received": money(event.amount_received),
                                "payment_currency": event.payment_currency,
                                "receiving_currency": event.receiving_currency,
                                "payment_format": event.payment_format,
                                "self_transfer": identity
                                == (event.other_bank, event.other_account),
                                "cross_currency": event.payment_currency
                                != event.receiving_currency,
                            }
                        )
                    yield event.role, row
                changes = amounts()
                source_rows = set()
                for event in group:
                    source_rows.add(event.source_row)
                    sent += event.role == "sender"
                    received += event.role == "receiver"
                    counterparty = (event.other_bank, event.other_account)
                    if counterparty != identity:
                        counterparties.add(counterparty)
                    key = (event.role, event.currency)
                    changes[key][0] += 1
                    changes[key][1] += event.amount
                total += len(
                    source_rows
                )  # Self-transfers have two endpoints, one event.
                adjust(lifetime, changes, 1)
                for window in windows:
                    window.add(timestamp, len(source_rows), changes)
                first = first or timestamp
                last = timestamp
