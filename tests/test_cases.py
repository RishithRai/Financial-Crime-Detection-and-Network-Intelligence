"""Distinct evidence counts and transparent, deterministic review grouping."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_investigation import A, B, C, D, T, edge, graph

from mulegraph.cases import CasePolicy, summarize
from mulegraph.graph import GraphLimitExceeded
from mulegraph.investigation import detect, reference


def finding(name, rows, kind="transaction_chain"):
    return {
        "id": name,
        "pattern_type": kind,
        "accounts": sorted({a for t in rows for a in (t.sender, t.receiver)}),
        "transactions": [reference(t) for t in rows],
        "evidence": {"test_fixture": True},
    }


def test_shared_transaction_preserves_findings_deduplicates_support():
    rows = [edge(1, A, B, 0), edge(2, B, C, 60), edge(3, C, D, 120)]
    f = [
        finding("one", rows[:2]),
        finding("two", rows),
        finding("rapid", rows[:2], "rapid_movement"),
    ]
    result = summarize(graph(rows), A, f, {1: 0.8, 2: 0.2})
    assert len(result["cases"]) == 1 and len(result["findings"]) == 3
    c = result["cases"][0]
    assert c["transaction_ids"] == [1, 2, 3]
    assert c["ml_summary"] == {
        "distinct_transactions": 3,
        "scored_transactions": 2,
        "unscored_transactions": 1,
        "score_coverage": 2 / 3,
        "max_transaction_score": 0.8,
        "unscored_reasons": {"SAVED_SCORE_UNAVAILABLE": 1},
    }
    assert c["finding_count"] == 3 and len(c["grouping_evidence"]) == 2
    assert c["reason_codes"][-1] == "OVERLAPPING_FINDINGS_GROUPED"
    assert result["counts"]["distinct_supporting_transactions"] == 3
    assert not result["completeness"]["search_completed_within_limits"]


def test_root_only_does_not_merge_but_nonroot_currency_time_does():
    rows = [
        edge(1, A, B, 0),
        edge(2, A, C, 60),
        edge(3, D, B, 120),
        edge(4, D, B, 7199),
        edge(5, D, B, 120, "EUR"),
    ]
    fs = [finding(str(t.source_row), [t], "fan_in") for t in rows]
    r = summarize(graph(rows), A, fs, {})
    assert sorted(sorted(c["finding_ids"]) for c in r["cases"]) == [
        ["1", "3"],
        ["2"],
        ["4"],
        ["5"],
    ]
    link = next(c for c in r["cases"] if len(c["finding_ids"]) == 2)[
        "grouping_evidence"
    ][0]
    assert link["reason"] == "SHARED_ACCOUNT_CURRENCY_NEAR_TIME"
    assert link["account"] == B


def test_duplicate_content_self_transfer_and_account_incident_counts():
    rows = [edge(1, A, B, 0), edge(2, A, B, 0), edge(3, A, A, 1), edge(4, C, D, 2)]
    r = summarize(
        graph(rows),
        A,
        [finding("one", rows[:2], "fan_out")],
        {1: 0.1, 2: 0.9, 3: 0, 4: 1},
    )
    a = next(x for x in r["accounts"] if x["account"] == A)
    assert a["ml_summary"]["distinct_transactions"] == 3
    assert a["ml_summary"]["max_transaction_score"] == 0.9  # D's score is not A's score
    assert a["supporting_ml_summary"]["distinct_transactions"] == 2
    assert a["history"]["incoming"] == 1 and a["history"]["outgoing"] == 3
    assert (
        a["history"]["self_transfers"] == 1
        and a["history"]["unique_counterparties"] == 1
    )
    assert a["history"]["transactions_per_hour"] == 1.5


def test_missing_training_and_empty_history_never_impute():
    rows = [
        replace(edge(1, A, B, 0), occurred_at=T - timedelta(days=5)),
        edge(2, B, C, 0),
    ]
    g = graph(rows)
    g.graph["start"] = T - timedelta(days=8)
    r = summarize(g, A, [finding("one", rows)], {2: 0.4})
    a = next(x for x in r["accounts"] if x["account"] == A)
    assert a["ml_summary"]["max_transaction_score"] is None
    assert a["ml_summary"]["unscored_reasons"] == {"UNSCORED_TRAINING_PERIOD": 1}
    assert r["transactions"][0]["score_status"] == "UNSCORED_TRAINING_PERIOD"
    with pytest.raises(ValueError, match="Training"):
        summarize(g, A, [], {1: 0.1})
    empty = summarize(graph([]), A, [], {})
    assert empty["accounts"][0]["ml_summary"]["score_coverage"] is None
    assert empty["cases"] == []


def test_ordering_duplicate_finding_and_conflicting_evidence():
    rows = [edge(1, A, B, 0), edge(2, B, C, 60)]
    f = detect(graph(rows), A)[0]
    a = summarize(graph(rows), A, f, {1: 0.5})
    b = summarize(graph(list(reversed(rows))), A, list(reversed(f)), {1: 0.5})
    assert a == b
    c = summarize(graph(rows), A, f + [f[0]], {1: 0.5})
    assert c["cases"] == a["cases"] and c["counts"]["duplicate_finding_records"] == 1
    bad = {**f[0], "pattern_type": "fan_out"}
    with pytest.raises(ValueError, match="Conflicting"):
        summarize(graph(rows), A, [f[0], bad], {})
    with pytest.raises(ValueError, match="evidence"):
        summarize(graph(rows[:1]), A, f, {})


def test_temporal_integrity_score_integrity_and_budgets():
    with pytest.raises(ValueError, match="temporal"):
        summarize(graph([edge(1, A, B, 7200)]), A, [], {})
    with pytest.raises(ValueError, match="invalid score"):
        summarize(graph([edge(1, A, B, 0)]), A, [], {1: float("nan")})
    rows = [edge(i, A, B, i) for i in range(1, 5)]
    fs = [finding(str(t.source_row), [t], "fan_in") for t in rows]
    with pytest.raises(GraphLimitExceeded, match="linkage"):
        summarize(graph(rows), A, fs, {}, policy=CasePolicy(max_link_checks=1))
    with pytest.raises(ValueError):
        CasePolicy(account_link_seconds=True)
    with pytest.raises(GraphLimitExceeded, match="evidence"):
        summarize(graph(rows), A, [fs[0]] * 5001, {})


def test_transitive_cases_and_cross_bank_identities():
    other = ("2", "B")
    rows = [
        edge(1, A, B, 0),
        edge(2, B, C, 60),
        edge(3, C, D, 120),
        edge(4, A, other, 10),
    ]
    fs = [finding(str(t.source_row), [t], "fan_in") for t in rows]
    r = summarize(graph(rows), A, fs, {})
    assert sorted(sorted(c["finding_ids"]) for c in r["cases"]) == [
        ["1", "2", "3"],
        ["4"],
    ]
    assert all("ml_summary" in c for c in r["cases"])


def test_score_changes_do_not_change_case_membership_and_window_is_validated():
    rows = [edge(1, A, B, 0), edge(2, A, C, 60)]
    fs = [finding(str(t.source_row), [t], "fan_in") for t in rows]
    one = summarize(graph(rows), A, fs, {1: 0.9, 2: 0.1})
    two = summarize(graph(rows), A, fs, {1: 0.1, 2: 0.9})
    assert {c["id"] for c in one["cases"]} == {c["id"] for c in two["cases"]}
    assert one["cases"][0]["id"] != two["cases"][0]["id"]
    g = graph(rows)
    g.graph["cutoff"] = g.graph["start"]
    with pytest.raises(ValueError, match="start < cutoff"):
        summarize(g, A, fs, {})
