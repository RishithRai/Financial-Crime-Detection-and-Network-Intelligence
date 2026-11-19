"""Behavioral leakage, boundary, currency, and composite-identity tests."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from mulegraph.feature_state import Event, account_features, money

T = datetime(2022, 9, 3)


def event(
    row,
    at,
    *,
    bank="1",
    account="000A",
    other_bank="2",
    other="000A",
    role="sender",
    currency="USD",
    amount="1.10",
):
    return Event(
        bank,
        account,
        at,
        row,
        role,
        other_bank,
        other,
        Decimal(amount),
        currency,
        Decimal(amount),
        Decimal(amount),
        currency,
        currency,
        "ACH",
    )


def compute(events):
    ordered = sorted(
        events, key=lambda e: (e.bank, e.account, e.timestamp, e.source_row, e.role)
    )
    return {(role, row["source_row"]): row for role, row in account_features(ordered)}


def test_windows_exact_lower_boundary_and_ties():
    events = [
        event(1, T - timedelta(days=1, microseconds=1)),
        event(2, T - timedelta(days=1)),
        event(3, T - timedelta(hours=1, microseconds=1)),
        event(4, T - timedelta(hours=1)),
        event(5, T),
        event(6, T),
    ]
    rows = compute(events)
    for source in (5, 6):
        target = rows[("sender", source)]
        assert target["history_count"] == 4
        assert target["count_1h"] == 1
        assert target["count_24h"] == 3
        assert target["currency_sum_1h"] == Decimal("1.10")
        assert target["currency_sum_24h"] == Decimal("3.30")
        assert target["seconds_since_last"] == 3600
        assert target["unique_counterparties"] == 1
    assert rows[("sender", 1)]["last_activity_at"] is None


def test_future_and_peer_mutations_cannot_change_prior_features():
    original = [event(1, T), event(2, T + timedelta(minutes=5))]
    baseline = compute(original)
    expanded = compute(
        [
            *original,
            event(3, T + timedelta(minutes=5), amount="999999", other="NEW"),
            event(4, T + timedelta(days=1), amount="50000000", other="FUTURE"),
        ]
    )
    assert all(expanded[key] == row for key, row in baseline.items())
    assert expanded[("sender", 4)]["history_count"] == 3
    assert expanded[("sender", 4)]["unique_counterparties"] == 2
    # Reordering tied records cannot change any row's history.
    assert compute(list(reversed(original))) == baseline


def test_both_directions_currency_isolation_and_self_transfer_once():
    rows = compute(
        [
            event(1, T, other_bank="1", other="000A"),
            event(1, T, role="receiver", other_bank="1", other="000A", amount="2.2"),
            event(2, T + timedelta(minutes=1), currency="EUR", amount="100"),
            event(3, T + timedelta(minutes=2), role="receiver", amount="3.3"),
            event(4, T + timedelta(minutes=3)),
        ]
    )
    row = rows[("sender", 4)]
    assert row["history_count"] == 3
    assert row["sent_count"] == row["received_count"] == 2
    assert row["unique_counterparties"] == 1  # Self excluded; bank 2 is distinct.
    assert row["currency_history_count"] == 1
    assert row["currency_history_sum"] == Decimal("1.1")
    receiver = rows[("receiver", 3)]
    assert receiver["currency_history_sum"] == Decimal("2.2")
    assert row["mean_gap_seconds"] == 60
    assert row["frequency_24h"] == 3 / 24


def test_account_strings_and_bank_identity_are_not_coalesced():
    rows = compute(
        [
            event(1, T),
            event(2, T + timedelta(minutes=1), bank="2"),
            event(3, T + timedelta(minutes=2), account="A"),
        ]
    )
    assert all(row["history_count"] == 0 for row in rows.values())


@pytest.mark.parametrize("value", ["0.0000000001", "1e29", "-1", "NaN", "Infinity"])
def test_money_contract_rejects_rounding_or_overflow(value):
    with pytest.raises(ValueError):
        money(Decimal(value))


def test_unsorted_input_and_unapproved_dates_are_rejected():
    with pytest.raises(ValueError, match="timestamps"):
        list(account_features([event(1, T), event(2, T - timedelta(hours=1))]))
    with pytest.raises(ValueError, match="outside approved"):
        compute([event(1, datetime(2022, 9, 19))])


def test_histories_match_independent_brute_force_reference():
    from random import Random

    random = Random(31)
    identities = [
        (bank, account) for bank in ("1", "2", "3") for account in ("000A", "000B")
    ]
    events = []
    for source in range(1, 61):
        sender = random.choice(identities)
        receiver = sender if source % 5 == 0 else random.choice(identities)
        at = T + timedelta(minutes=random.choice([0, 30, 60, 61, 1440, 1441, 2880]))
        for role, own, other in (
            ("sender", sender, receiver),
            ("receiver", receiver, sender),
        ):
            events.append(
                event(
                    source,
                    at,
                    bank=own[0],
                    account=own[1],
                    other_bank=other[0],
                    other=other[1],
                    role=role,
                    currency=random.choice(["USD", "EUR"]),
                    amount=str(source / 10),
                )
            )
    observed = compute(events)
    for current in events:
        identity = (current.bank, current.account)
        prior = [
            e
            for e in events
            if (e.bank, e.account) == identity and e.timestamp < current.timestamp
        ]
        result = observed[(current.role, current.source_row)]
        assert result["history_count"] == len({e.source_row for e in prior})
        assert result["sent_count"] == sum(e.role == "sender" for e in prior)
        assert result["received_count"] == sum(e.role == "receiver" for e in prior)
        assert result["unique_counterparties"] == len(
            {
                (e.other_bank, e.other_account)
                for e in prior
                if (e.other_bank, e.other_account) != identity
            }
        )
        for hours in (1, 24):
            window = [
                e
                for e in prior
                if e.timestamp >= current.timestamp - timedelta(hours=hours)
            ]
            assert result[f"count_{hours}h"] == len({e.source_row for e in window})
            matching = [
                e
                for e in window
                if e.role == current.role and e.currency == current.currency
            ]
            assert result[f"currency_count_{hours}h"] == len(matching)
            assert result[f"currency_sum_{hours}h"] == sum(
                (e.amount for e in matching), Decimal(0)
            )
        matching = [
            e
            for e in prior
            if e.role == current.role and e.currency == current.currency
        ]
        assert result["currency_history_sum"] == sum(
            (e.amount for e in matching), Decimal(0)
        )
