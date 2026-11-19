"""Rules, training-only profiling, metric arithmetic, and sealed-stage tests."""

from copy import deepcopy
from decimal import Decimal

import duckdb
import pyarrow as pa
import pytest

from mulegraph.rule_metrics import select_threshold, summarize
from mulegraph.rules import (
    REASONS,
    profile_training,
    register_profile,
    score_row,
    scoring_sql,
)
from mulegraph.rules_baseline import export_labels, frozen_definition


def row():
    result = {
        "amount_paid": Decimal("100.00"),
        "amount_received": Decimal("100.00"),
        "payment_currency": "USD",
        "receiving_currency": "USD",
        "payment_format": "ACH",
        "source_row": 1,
        "occurred_at": "2022-09-07",
        "split": "validation",
        "dataset_id": 1,
        "dataset_fingerprint": "fixture",
    }
    for role in ("sender", "receiver"):
        result.update(
            {
                f"{role}_currency_history_count": 5,
                f"{role}_currency_history_sum": Decimal("50.00"),
                f"{role}_history_age_seconds": 86400,
                f"{role}_count_1h": 4,
                f"{role}_count_24h": 20,
                f"{role}_sent_count": 5,
                f"{role}_received_count": 5,
            }
        )
    return result


def profile():
    return {
        "currencies": [
            {
                "role": role,
                "currency": "USD",
                "observations": 1000,
                "p95": "90.00",
                "p995": "1000.00",
                "supported": True,
            }
            for role in ("sender", "receiver")
        ],
        "activity": {
            r: {"cutoff": 20, "eligible_training_rows": 1000}
            for r in ("sender", "receiver")
        },
    }


def test_amount_boundary_exact_and_limited_history_suppressed():
    values = row()
    assert score_row(values, profile())["risk_score"] == 0  # Exactly ten times mean.
    values["amount_paid"] = Decimal("100.000000001")
    observed = score_row(values, profile())
    assert observed["risk_score"] == 2
    assert observed["reason_codes"] == ["SENDER_AMOUNT_SPIKE"]
    values["sender_currency_history_count"] = 4
    assert score_row(values, profile())["risk_score"] == 0
    values["sender_currency_history_count"] = 5
    values["payment_currency"] = "UNKNOWN"
    assert score_row(values, profile())["risk_score"] == 0


def test_activity_warmup_and_direction_changes():
    values = row()
    values.update(
        sender_count_1h=5,
        sender_count_24h=28,
        sender_sent_count=1,
        sender_received_count=10,
    )
    result = score_row(values, profile())
    assert result["SENDER_FREQUENCY_SURGE"] is False  # Exact 5x boundary.
    assert result["SENDER_HIGH_ACTIVITY"] is True
    assert result["SENDER_DIRECTION_CHANGE"] is True
    values["sender_count_1h"] = 6
    assert score_row(values, profile())["SENDER_FREQUENCY_SURGE"] is True
    values["sender_history_age_seconds"] = None
    assert score_row(values, profile())["risk_score"] == 0


def test_labels_identities_future_rows_and_peer_order_cannot_affect_fixed_scores():
    values = row()
    expected = score_row(values, profile())
    altered = {
        **values,
        "is_laundering": 1,
        "source_row": 99999,
        "split": "stress",
        "occurred_at": "2099-01-01",
        "from_account": "different",
        "pattern": "annotation",
    }
    assert score_row(altered, profile()) == expected
    assert [score_row(x, profile()) for x in [values, altered]][0] == expected
    assert [score_row(x, profile()) for x in [altered, values]][1] == expected


def test_sql_and_python_rule_implementations_agree():
    rows = []
    for index in range(10):
        values = row()
        values.update(
            source_row=index + 1,
            amount_paid=Decimal(index * 30),
            sender_count_1h=index,
            sender_count_24h=index + 20,
            receiver_currency_history_count=index,
        )
        if index == 2:
            values["payment_currency"] = "UNKNOWN"
        if index == 3:
            values["receiver_history_age_seconds"] = None
        rows.append(values)
    with duckdb.connect() as connection:
        connection.register("features", pa.Table.from_pylist(rows))
        register_profile(connection, profile())
        results = connection.execute(
            scoring_sql(profile()), ["validation"]
        ).to_arrow_table()
    for actual in results.to_pylist():
        expected = score_row(rows[actual["source_row"] - 1], profile())
        assert {key: actual[key] for key in expected} == expected
        assert set(actual["reason_codes"]) <= set(REASONS)


def test_training_profile_cannot_use_validation_or_future_distributions():
    train = [{**row(), "split": "train", "source_row": i} for i in range(1000)]
    with duckdb.connect() as connection:
        connection.register("features", pa.Table.from_pylist(train))
        expected = profile_training(connection)
        future = {
            **row(),
            "amount_paid": Decimal("9999999999.00"),
            "sender_count_24h": 999999,
            "split": "test",
        }
        connection.register("features", pa.Table.from_pylist([*train, future]))
        assert profile_training(connection) == expected
        connection.register(
            "features",
            pa.Table.from_pylist([*train, {**future, "split": "validation"}]),
        )
        assert profile_training(connection) == expected
    unsupported = deepcopy(expected)
    for item in unsupported["currencies"]:
        item["supported"] = False
    values = {**row(), "amount_paid": Decimal("99999999")}
    assert not score_row(values, unsupported)["SENDER_AMOUNT_SPIKE"]


def test_average_precision_grouped_ties_and_precision_at_k():
    metrics = summarize(
        [(2, 2, 1), (1, 2, 1), (0, 1, 0)], [1, 0, 0, 1, 0], 2, ks=(1, 3, 100)
    )
    assert metrics["average_precision"] == 0.5
    assert metrics["prevalence"] == 0.4
    assert metrics["precision"] == metrics["recall"] == 0.5
    assert metrics["at_k"][1]["precision"] == 1 / 3
    assert metrics["at_k"][2]["effective_k"] == 5
    assert metrics["at_k"][2]["recall"] == 1
    assert summarize([(0, 5, 2)], [0, 1, 0, 1, 0], 1, (5,))["average_precision"] == 0.4
    no_positive = summarize([(0, 2, 0)], [0, 0], 1, (2,))
    assert no_positive["average_precision"] is None
    assert no_positive["precision"] is None


def test_budgeted_threshold_selection_and_ties():
    threshold, candidates = select_threshold([(2, 1, 1), (1, 9, 2), (0, 990, 7)], 2)
    assert threshold == 1
    assert all(row["alerts"] <= 10 for row in candidates if row["eligible"])
    assert select_threshold([(0, 100, 1)], 2)[0] == 3  # No-alert policy allowed.
    with pytest.raises(ValueError, match="positive"):
        select_threshold([(0, 100, 0)], 2)


def test_holdout_label_guard_fails_before_any_connection(tmp_path):
    with pytest.raises(ValueError, match="sealed"):
        export_labels("not-a-dsn", {}, "test", tmp_path / "labels", frozen=False)
    with pytest.raises(ValueError, match="Finalize"):
        frozen_definition(tmp_path)
