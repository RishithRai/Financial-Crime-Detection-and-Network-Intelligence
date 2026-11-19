"""Bounded dashboard adapters. No labels, fitting, or changed investigation logic."""

import json
import math
import threading
from datetime import datetime
from pathlib import Path

import duckdb

from mulegraph.cases import investigate_cases
from mulegraph.features import sha256_file
from mulegraph.graph import COLUMNS, Limits, graph_session
from mulegraph.investigation_scores import FrozenScores

ORDERS = {
    "Highest score": "score DESC, source_row",
    "Newest": "occurred_at DESC, source_row",
    "Source ID": "source_row",
}


class DashboardData:
    def __init__(self, root: Path = Path(".")) -> None:
        self.root = root
        self.scores = FrozenScores.saved(root)
        self.freeze = json.loads((root / "docs/ml_holdout_freeze_v1.json").read_text())
        self.features = (
            root
            / "data/features/historical-v1"
            / self.scores.fingerprint
            / "features.parquet"
        )

    def queue(
        self,
        split: str = "test",
        *,
        page: int = 0,
        size: int = 25,
        order: str = "Highest score",
        source: int | None = None,
        bank: str = "",
        account: str = "",
        payment_format: str = "",
        alerts_only: bool = False,
    ) -> tuple[list[dict], bool]:
        """At most 100 rows plus one sentinel; 10s query deadline, no disk spill."""
        if split not in ("validation", "test", "stress") or order not in ORDERS:
            raise ValueError("Invalid queue selection")
        if type(page) is not int or not 0 <= page <= 1000 or not 1 <= size <= 100:
            raise ValueError("Queue pagination limit exceeded; narrow the filters")
        if source is not None and (type(source) is not int or source < 1):
            raise ValueError("Source ID must be positive")
        if bool(bank) != bool(account):
            raise ValueError("Supply both bank and account for composite identity")
        artifact = self.scores.files[("validation", "test", "stress").index(split)]
        if (
            sha256_file(artifact.path) != artifact.sha256
            or sha256_file(self.features) != self.freeze["feature_sha256"]
        ):
            raise ValueError("Frozen queue artifact checksum mismatch")
        clauses = ["f.occurred_at >= ?", "f.occurred_at < ?"]
        args = [str(self.features), str(artifact.path), artifact.start, artifact.end]
        for condition, values in (
            ("f.source_row = ?", [source] if source else []),
            (
                "((from_bank_id=? AND from_account=?) OR (to_bank_id=? AND to_account=?))",  # noqa: E501
                [bank, account, bank, account] if bank else [],
            ),
            ("payment_format=?", [payment_format] if payment_format else []),
            (
                f'p."{artifact.column}" >= ?',
                [self.freeze["thresholds"]["lightgbm"]] if alerts_only else [],
            ),
        ):
            if values:
                clauses.append(condition)
                args.extend(values)
        columns = ",".join("f." + c.strip() for c in COLUMNS.split(","))
        query = (
            f'SELECT {columns}, p."{artifact.column}" AS score FROM read_parquet(?) f JOIN read_parquet(?) p USING(source_row) WHERE '  # noqa: E501
            + " AND ".join(clauses)
        )
        with duckdb.connect(
            config={
                "threads": 2,
                "memory_limit": "256MB",
                "max_temp_directory_size": "0B",
            }
        ) as db:
            timer = threading.Timer(10, db.interrupt)
            timer.start()
            try:
                rows = (
                    db.execute(
                        query + f" ORDER BY {ORDERS[order]} LIMIT ? OFFSET ?",
                        [*args, size + 1, page * size],
                    )
                    .to_arrow_table()
                    .to_pylist()
                )
            finally:
                timer.cancel()
                timer.join()
        if len({r["source_row"] for r in rows}) != len(rows) or any(
            not math.isfinite(r["score"]) or not 0 <= r["score"] <= 1 for r in rows
        ):
            raise ValueError("Invalid saved queue scores")
        # Decimal strings preserve monetary precision in the presentation layer.
        for row in rows:
            for field in ("amount_paid", "amount_received"):
                row[field] = str(row[field])
        return rows[:size], len(rows) > size

    def overview(self) -> dict:
        return json.loads(
            (self.root / "data/ml/supervised-holdout-v1/results.json").read_text()
        )

    def investigate(
        self,
        dsn: str,
        start: datetime,
        cutoff: datetime,
        *,
        account: tuple[str, str] | None = None,
        focal: int | None = None,
        hops: int = 2,
        nodes: int = 150,
        edges: int = 1000,
        schema: str = "mulegraph",
    ) -> dict:
        if not 1 <= nodes <= 500 or not 1 <= edges <= 5000 or not 1 <= hops <= 2:
            raise ValueError("Dashboard resource limits exceeded")
        with graph_session(
            dsn,
            self.scores.dataset_id,
            schema=schema,
            limits=Limits(max_nodes=nodes, max_edges=edges, max_hops=2),
        ) as reader:
            return investigate_cases(
                reader,
                start,
                cutoff,
                account=account,
                focal_source_row=focal,
                hops=hops,
                scores=self.scores,
            )
