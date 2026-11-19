"""Label-free graph/control reload verification and independent SQL spot checks."""

import argparse
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

from mulegraph.features import sha256_file
from mulegraph.graph import graph_session
from mulegraph.graph_features import COLUMNS
from mulegraph.graph_inputs import GraphPreprocessor
from mulegraph.graph_ml import connect_graph, graph_batches, validate
from mulegraph.ml import Preprocessor
from mulegraph.ml_training import batches, load_artifact
from mulegraph.schema import statement


def sql_sample(
    db: duckdb.DuckDBPyConnection, dsn: str, dataset_id: int, fingerprint: str
) -> dict:
    """Source-position sample plus first reverse-history and self-history rows."""
    sample = (
        db.execute("""
      SELECT * FROM joined WHERE source_row IN (1,500000,1000000,1500000,
        2000000,2500000,3000000,3500000,4000000,4500000,5000000,5078345)
      OR source_row IN (SELECT source_row FROM joined
        WHERE reverse_prior_count>0 ORDER BY source_row LIMIT 5)
      OR source_row IN (SELECT source_row FROM joined
        WHERE from_bank_id=to_bank_id AND from_account=to_account
          AND pair_prior_count>0 ORDER BY source_row LIMIT 5)
      ORDER BY source_row
    """)
        .to_arrow_table()
        .to_pylist()
    )
    checked = 0
    with graph_session(dsn, dataset_id) as reader:
        if reader.fingerprint != fingerprint:
            raise ValueError("Database fingerprint differs from feature source")
        for t in sample:
            sender = (t["from_bank_id"], t["from_account"])
            receiver = (t["to_bank_id"], t["to_account"])
            expected = []
            for a, b in ((sender, receiver), (receiver, sender)):
                row = reader.connection.execute(
                    statement(
                        """
                 SELECT count(*) AS n,max(occurred_at) AS last
                 FROM {core}.transactions WHERE dataset_id=%s
                 AND from_bank_id=%s AND from_account=%s
                 AND to_bank_id=%s AND to_account=%s AND occurred_at<%s
                """,
                        reader.schema,
                    ),
                    (dataset_id, *a, *b, t["occurred_at"]),
                ).fetchone()
                expected.append(
                    (
                        row["n"],
                        (t["occurred_at"] - row["last"]).total_seconds()
                        if row["last"]
                        else None,
                    )
                )
            if sender == receiver:
                expected[1] = (0, None)
            assert [t[n] for n in COLUMNS] == [
                expected[0][0],
                expected[1][0],
                expected[0][1],
                expected[1][1],
            ]
            checked += 1
    return {"source_rows": checked, "values": checked * 4, "matched": True}


def verify(
    features: Path, graph: Path, models: Path, output: Path, dsn: str | None = None
) -> dict:
    started = time.perf_counter()
    plan = json.loads((models / "plan.json").read_text())
    validate(plan)
    results = json.loads((models / "results.json").read_text())
    checked = 0
    with duckdb.connect() as db:
        manifest = connect_graph(db, features, graph)
        ids = (
            db.execute(
                "SELECT source_row FROM features WHERE split='validation' "
                "ORDER BY source_row"
            )
            .to_arrow_table()["source_row"]
            .to_numpy()
        )
        base = Preprocessor.fit(batches(db, "history", "train"), "history")
        added = GraphPreprocessor.fit(base, graph_batches(db, "train"))
        for result in results["experiments"]:
            path = models / result["name"]
            for name, key in [
                ("model.joblib", "model_sha256"),
                ("validation.parquet", "predictions_sha256"),
            ]:
                if sha256_file(path / name) != result[key]:
                    raise ValueError("Published artifact changed")
            loaded = load_artifact(path)
            prep = loaded["preprocessor"]
            expected = added if result["name"] == "history_plus_graph" else base
            np.testing.assert_array_equal(prep.mean, expected.mean)
            np.testing.assert_array_equal(prep.scale, expected.scale)
            assert (
                prep.names == expected.names
                and prep.training_rows == expected.training_rows
            )
            if isinstance(prep, GraphPreprocessor):
                np.testing.assert_array_equal(prep.base.mean, base.mean)
                np.testing.assert_array_equal(prep.base.scale, base.scale)
                assert prep.base.categories == base.categories
            else:
                assert prep.categories == base.categories
            saved = pq.read_table(path / "validation.parquet")
            assert saved.column_names == ["source_row", "score"]
            np.testing.assert_array_equal(ids, saved["source_row"].to_numpy())
            scores = saved["score"].to_numpy()
            offset = 0
            with threadpool_limits(limits=2):
                for batch in graph_batches(db, "validation"):
                    predicted = loaded["model"].predict_proba(prep.transform(batch))[
                        :, 1
                    ]
                    np.testing.assert_array_equal(
                        predicted, scores[offset : offset + len(batch)]
                    )
                    offset += len(batch)
            assert offset == len(ids)
            assert loaded["model"].get_params() == result["model_parameters"]
            assert loaded["threshold"] == result["metrics"]["threshold"]
            assert (
                int((scores >= loaded["threshold"]).sum())
                == result["metrics"]["alerts"]
            )
            checked += offset
        sample = (
            sql_sample(
                db,
                dsn,
                manifest["dataset"]["dataset_id"],
                manifest["dataset"]["fingerprint"],
            )
            if dsn
            else None
        )
    validate(plan)
    report = {
        "reproduced_validation_scores": checked,
        "training_preprocessing_exact": True,
        "originals_unchanged": True,
        "postgresql_sample": sample,
        "seconds": time.perf_counter() - started,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, indent=2)
    return report


def main() -> None:
    import os

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--features-dir", type=Path, required=True)
    p.add_argument(
        "--graph-dir", type=Path, default=Path("data/features/graph-features-v1")
    )
    p.add_argument("--models", type=Path, default=Path("data/ml/graph-prediction-v1"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--postgresql-sample", action="store_true")
    args = p.parse_args()
    print(
        json.dumps(
            verify(
                args.features_dir,
                args.graph_dir,
                args.models,
                args.output,
                os.environ["DATABASE_URL"] if args.postgresql_sample else None,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
