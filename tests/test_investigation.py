"""Hand-worked witnesses, temporal negatives, currency and work bounds."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal

import networkx as nx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from mulegraph.features import sha256_file
from mulegraph.graph import GraphLimitExceeded, Transfer
from mulegraph.investigation import PatternPolicy, detect, investigate
from mulegraph.investigation_scores import FrozenScores, ScoreFile

T = datetime(2022, 9, 9)
A, B, C, D = [("1", x) for x in "ABCD"]


def edge(row, sender, receiver, seconds, currency="USD"):
    return Transfer(
        1,
        row,
        T + timedelta(seconds=seconds),
        *sender,
        *receiver,
        Decimal("1.10"),
        currency,
        Decimal("1.10"),
        currency,
        "ACH",
    )


def graph(rows):
    g = nx.MultiDiGraph(dataset_id=1, start=T, cutoff=T + timedelta(hours=2))
    g.add_node(A)
    for t in rows:
        g.add_edge(t.sender, t.receiver, key=t.key, **asdict(t))
    return g


def kinds(findings):
    return {f["pattern_type"] for f in findings}


def test_ordered_chain_cycle_rapid_and_structured_evidence():
    rows = [edge(1, A, B, 0), edge(2, B, C, 60), edge(3, C, A, 120)]
    findings, _ = detect(graph(rows), A)
    assert {"transaction_chain", "circular_flow", "rapid_movement"} <= kinds(findings)
    cycle = next(f for f in findings if f["pattern_type"] == "circular_flow")
    assert [x["source_row"] for x in cycle["transactions"]] == [1, 2, 3]
    assert cycle["evidence"]["elapsed_seconds"] == 120
    assert cycle["transactions"][0]["amount_paid"] == "1.10"
    assert cycle["accounts"] == [A, B, C]
    assert detect(graph(list(reversed(rows))), A) == detect(graph(rows), A)


@pytest.mark.parametrize("seconds", [0, -1])
def test_equal_or_reverse_time_cannot_establish_flow(seconds):
    # Move the whole fixture into the valid window; only relative ordering changes.
    findings, _ = detect(graph([edge(1, A, B, 10), edge(2, B, C, 10 + seconds)]), A)
    assert not findings


def test_static_cycle_not_chronological_and_currency_mismatch():
    findings, _ = detect(
        graph([edge(1, A, B, 0), edge(2, B, C, 0), edge(3, C, A, 0)]), A
    )
    assert "circular_flow" not in kinds(findings)
    findings, _ = detect(graph([edge(1, A, B, 0), edge(2, B, C, 1, "EUR")]), A)
    assert not findings
    findings, _ = detect(graph([edge(1, A, A, 0), edge(2, A, A, 1)]), A)
    assert not findings
    findings, _ = detect(
        graph([replace(edge(1, A, B, 0), amount_paid=Decimal(0)), edge(2, B, C, 1)]), A
    )
    assert not findings


def test_fan_unique_composites_currency_and_time_window():
    rows = [edge(1, A, B, 0), edge(2, A, B, 1), edge(3, A, C, 2)]
    assert "fan_out" not in kinds(detect(graph(rows), A)[0])
    rows.append(edge(4, A, ("2", "B"), 3600))
    finding = next(
        f for f in detect(graph(rows), A)[0] if f["pattern_type"] == "fan_out"
    )
    assert finding["evidence"]["distinct_counterparties"] == 3
    assert len(finding["transactions"]) == 4
    # Three senders at the same timestamp are a fan, not an ordered chain.
    incoming = [edge(i, n, A, 0) for i, n in enumerate((B, C, D), 1)]
    assert kinds(detect(graph(incoming), A)[0]) == {"fan_in"}
    assert "fan_out" not in kinds(
        detect(graph([edge(1, A, B, 0), edge(2, A, C, 0), edge(3, A, D, 3601)]), A)[0]
    )
    assert "fan_out" not in kinds(
        detect(graph([edge(1, A, B, 0), edge(2, A, C, 0), edge(3, A, D, 1, "EUR")]), A)[
            0
        ]
    )


def test_limits_span_and_future_graph_rejection():
    rows = [edge(1, A, B, 0), edge(2, B, C, 1), edge(3, C, A, 2)]
    for kwargs in ({"max_candidates": 1}, {"max_findings": 1}, {"max_references": 1}):
        with pytest.raises(GraphLimitExceeded):
            detect(graph(rows), A, PatternPolicy(**kwargs))
    assert not detect(
        graph([edge(1, A, B, 0), edge(2, B, C, 11)]), A, PatternPolicy(path_seconds=10)
    )[0]
    with pytest.raises(ValueError, match="historical"):
        detect(graph([edge(1, A, B, 7200)]), A)
    with pytest.raises(ValueError):
        PatternPolicy(max_path_edges=7)
    with pytest.raises(ValueError):
        PatternPolicy(fan_accounts=True)


def test_saved_score_alignment_missing_corruption_and_unknown_period(tmp_path):
    p = tmp_path / "scores.parquet"
    pq.write_table(pa.table({"source_row": [2, 1], "lightgbm": [0.2, 0.8]}), p)
    source = FrozenScores(
        "fingerprint",
        1,
        (ScoreFile(p, sha256_file(p), "lightgbm", T, T + timedelta(days=1)),),
    )
    rows = [edge(1, A, B, 0), edge(2, B, C, 1)]
    assert source.lookup(rows, "fingerprint") == {1: 0.8, 2: 0.2}
    assert (
        source.lookup(
            [replace(rows[0], occurred_at=T - timedelta(days=5))], "fingerprint"
        )
        == {}
    )
    with pytest.raises(ValueError, match="dataset"):
        source.lookup(rows, "wrong")
    with pytest.raises(ValueError, match="Missing"):
        source.lookup([edge(3, A, B, 0)], "fingerprint")
    p.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        source.lookup(rows, "fingerprint")


def test_score_duplicates_and_nonfinite_are_rejected(tmp_path):
    for ids, values in (([1, 1], [0.1, 0.2]), ([1], [float("nan")])):
        p = tmp_path / "scores.parquet"
        pq.write_table(pa.table({"source_row": ids, "score": values}), p)
        source = FrozenScores(
            "x", 1, (ScoreFile(p, sha256_file(p), "score", T, T + timedelta(days=1)),)
        )
        with pytest.raises(ValueError):
            source.lookup([edge(1, A, B, 0)], "x")


def test_service_scores_prioritize_without_changing_findings():
    from mulegraph.graph import Investigation

    rows = [edge(1, A, B, 0), edge(2, B, C, 60)]

    class Reader:
        fingerprint = "x"

        def network(self, *args):
            g = graph(rows)
            g.graph["scope"] = "fixture"
            return Investigation(g, None, 1, 1)

    class Scores:
        def lookup(self, transfers, fingerprint):
            return {1: 0.9}

    plain = investigate(Reader(), T, T + timedelta(hours=2), account=A)
    scored = investigate(
        Reader(), T, T + timedelta(hours=2), account=A, scores=Scores()
    )
    assert {f["id"] for f in plain["findings"]} == {f["id"] for f in scored["findings"]}
    assert all(
        f["priority"]["max_transaction_score"] == 0.9 for f in scored["findings"]
    )
    assert all(f["priority"]["unscored_transactions"] == 1 for f in scored["findings"])


def test_saved_provider_rejects_model_and_freeze_tampering(tmp_path):
    import json

    stable = tmp_path / "data/ml/lightgbm-stable-v1/history_none"
    stable.mkdir(parents=True)
    holdout = tmp_path / "data/ml/supervised-holdout-v1"
    holdout.mkdir(parents=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (stable / "model.joblib").write_bytes(b"opaque-unloaded-model")
    (stable / "metadata.json").write_text("{}")
    (stable / "validation.parquet").write_bytes(b"not-needed-for-constructor")
    frozen = {
        "selected": "lightgbm-stable-v1/history_none",
        "dataset": {"fingerprint": "x", "dataset_id": 1},
        "sources_sha256": {
            "stable": {
                f"history_none/{p.name}": sha256_file(p) for p in stable.iterdir()
            }
        },
        "splits": {
            "test": ["2022-09-09", "2022-09-11"],
            "stress": ["2022-09-11", "2022-09-19"],
        },
    }
    freeze = docs / "ml_holdout_freeze_v1.json"
    freeze.write_text(json.dumps(frozen))
    (holdout / "freeze.json").write_bytes(freeze.read_bytes())
    (holdout / "results.json").write_text(
        json.dumps(
            {
                "selected": frozen["selected"],
                "freeze_sha256": sha256_file(freeze),
                "prediction_sha256": {"test": "unused", "stress": "unused"},
            }
        )
    )
    assert FrozenScores.saved(tmp_path).model == frozen["selected"]
    (stable / "model.joblib").write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact checksum"):
        FrozenScores.saved(tmp_path)
    freeze.write_text("{}")
    with pytest.raises(ValueError, match="provenance"):
        FrozenScores.saved(tmp_path)
