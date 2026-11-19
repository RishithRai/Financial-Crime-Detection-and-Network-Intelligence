"""Independent pair-history oracle, peer isolation and training-only encoding."""

from datetime import datetime, timedelta

import duckdb
import numpy as np
import pyarrow as pa
import pytest
from test_ml import fixture_table

from mulegraph.graph_features import COLUMNS, SQL, build, verify_graph
from mulegraph.graph_ml import GraphPreprocessor, graph_batches
from mulegraph.ml import Preprocessor


def records() -> list[dict]:
    start = datetime(2022, 9, 1)
    triples = [
        ("1", "A", "2", "A", 0),
        ("1", "A", "2", "A", 0),
        ("2", "A", "1", "A", 0),
        ("1", "A", "2", "A", 10),
        ("2", "A", "1", "A", 20),
        ("1", "A", "1", "A", 0),
        ("1", "A", "1", "A", 20),
        ("1", "A", "3", "A", 30),
    ]
    return [
        dict(
            source_row=i + 1,
            from_bank_id=a,
            from_account=b,
            to_bank_id=c,
            to_account=d,
            occurred_at=start + timedelta(seconds=s),
            split="train",
        )
        for i, (a, b, c, d, s) in enumerate(triples)
    ]


def compute(rows: list[dict]) -> list[dict]:
    with duckdb.connect() as db:
        db.register("features", pa.Table.from_pylist(rows))
        return db.execute(SQL).to_arrow_table().to_pylist()


def oracle(rows: list[dict], target: dict) -> list:
    sender = (target["from_bank_id"], target["from_account"])
    receiver = (target["to_bank_id"], target["to_account"])

    def prior(a, b):
        return [
            r
            for r in rows
            if r["occurred_at"] < target["occurred_at"]
            and (r["from_bank_id"], r["from_account"]) == a
            and (r["to_bank_id"], r["to_account"]) == b
        ]

    f = prior(sender, receiver)
    r = prior(receiver, sender) if sender != receiver else []

    def gap(rs):
        return (
            (target["occurred_at"] - max(x["occurred_at"] for x in rs)).total_seconds()
            if rs
            else None
        )

    return [len(f), len(r), gap(f), gap(r)]


def test_independent_direction_duplicate_self_and_composite_oracle():
    rows = records()
    actual = compute(rows)
    for r, a in zip(rows, actual, strict=True):
        assert [a[n] for n in COLUMNS] == oracle(rows, r)
    assert actual[3]["pair_prior_count"] == 2
    assert actual[3]["reverse_prior_count"] == 1
    assert actual[6]["pair_prior_count"] == 1
    assert actual[6]["reverse_prior_count"] == 0


def test_future_and_same_timestamp_peers_do_not_change_earlier_outputs():
    rows = records()
    before = compute(rows)
    extra = [
        dict(rows[3], source_row=99),
        dict(rows[3], source_row=100, occurred_at=datetime(2022, 9, 19)),
    ]
    after = {r["source_row"]: r for r in compute(rows + extra)}
    for r in before:
        if r["occurred_at"] <= rows[3]["occurred_at"]:
            assert after[r["source_row"]] == r
    assert compute(list(reversed(rows))) == before


def test_random_pairs_match_independent_oracle_and_split_rolls_forward():
    rng = np.random.default_rng(42)
    rows = []
    for i in range(200):
        rows.append(
            dict(
                source_row=i + 1,
                from_bank_id=str(rng.integers(1, 4)),
                from_account="A",
                to_bank_id=str(rng.integers(1, 4)),
                to_account="A",
                occurred_at=datetime(2022, 9, 6)
                + timedelta(hours=int(rng.integers(0, 72))),
                split="validation",
            )
        )
    for a, r in zip(compute(rows), rows, strict=True):
        assert [a[n] for n in COLUMNS] == oracle(rows, r)


def test_duplicate_ids_and_wrong_coverage_rejected(tmp_path):
    rows = records()
    table = pa.Table.from_pylist(compute(rows))
    import pyarrow.parquet as pq

    p = tmp_path / "graph.parquet"
    pq.write_table(pa.concat_tables([table, table.slice(0, 1)]), p)
    with duckdb.connect() as db:
        db.register("features", pa.Table.from_pylist(rows))
        with pytest.raises(ValueError):
            verify_graph(db, p)
    with pytest.raises(ValueError, match="exists"):
        build(tmp_path, tmp_path)


def test_train_only_graph_encoding_missingness_and_holdout_guard():
    table = fixture_table(20)
    base = Preprocessor.fit([table], "history")
    for i, n in enumerate(COLUMNS):
        table = table.append_column(
            n,
            pa.array([None if i > 1 and j % 2 else j for j in range(20)], pa.float64()),
        )
    prep = GraphPreprocessor.fit(base, [table])
    before = prep.mean.copy()
    transformed = prep.transform(table)
    assert transformed.shape == (20, len(base.names) + 6)
    np.testing.assert_array_equal(
        transformed[:, : len(base.names)], base.transform(table)
    )
    assert transformed[1, -1] == 1
    changed = table.set_column(
        table.column_names.index(COLUMNS[0]), COLUMNS[0], pa.array([100000] * 20)
    )
    prep.transform(changed)
    np.testing.assert_array_equal(before, prep.mean)
    validation = table.set_column(
        table.column_names.index("split"),
        "split",
        pa.array(["validation"] * len(table)),
    )
    with pytest.raises(ValueError, match="training"):
        GraphPreprocessor.fit(base, [validation])
    with duckdb.connect() as db:
        for split in ("test", "stress"):
            with pytest.raises(ValueError):
                list(graph_batches(db, split))


def test_label_metadata_isolation_and_original_split_boundaries():
    rows = records()
    decorated = [
        dict(r, is_laundering=i % 2, pattern="not an input", future_balance=999999)
        for i, r in enumerate(rows)
    ]
    assert compute(decorated) == compute(rows)
    boundaries = [
        ("train", datetime(2022, 9, 6, 23, 59, 59)),
        ("validation", datetime(2022, 9, 7)),
        ("test", datetime(2022, 9, 9)),
        ("stress", datetime(2022, 9, 11)),
    ]
    rows = [
        dict(rows[0], source_row=i + 1, split=split, occurred_at=time)
        for i, (split, time) in enumerate(boundaries)
    ]
    result = compute(rows)
    assert [r["split"] for r in result] == [s for s, _ in boundaries]
    assert [r["pair_prior_count"] for r in result] == [0, 1, 2, 3]
    assert result[1]["pair_seconds_since_last"] == 1
