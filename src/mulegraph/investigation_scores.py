"""Read saved label-free scores; no model loading, fitting, or label evaluation."""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa

from mulegraph.features import sha256_file
from mulegraph.graph import Transfer


@dataclass(frozen=True)
class ScoreFile:
    path: Path
    sha256: str
    column: str
    start: datetime
    end: datetime


@dataclass
class FrozenScores:
    fingerprint: str
    dataset_id: int
    files: tuple[ScoreFile, ...]
    model: str = "lightgbm-stable-v1/history_none"

    @classmethod
    def saved(cls, root: Path = Path(".")) -> "FrozenScores":
        freeze_path = root / "docs/ml_holdout_freeze_v1.json"
        frozen = json.loads(freeze_path.read_text())
        holdout = root / "data/ml/supervised-holdout-v1"
        results = json.loads((holdout / "results.json").read_text())
        if (
            results["freeze_sha256"] != sha256_file(freeze_path)
            or sha256_file(holdout / "freeze.json") != sha256_file(freeze_path)
            or frozen["selected"] != "lightgbm-stable-v1/history_none"
            or results["selected"] != frozen["selected"]
        ):
            raise ValueError("Frozen score provenance mismatch")
        stable = root / "data/ml/lightgbm-stable-v1"
        hashes = frozen["sources_sha256"]["stable"]
        for name in ("history_none/model.joblib", "history_none/metadata.json"):
            if sha256_file(stable / name) != hashes[name]:
                raise ValueError("Selected model artifact checksum mismatch")
        files = [
            ScoreFile(
                stable / "history_none/validation.parquet",
                hashes["history_none/validation.parquet"],
                "score",
                datetime(2022, 9, 7),
                datetime(2022, 9, 9),
            )
        ]
        for split in ("test", "stress"):
            files.append(
                ScoreFile(
                    holdout / f"{split}.parquet",
                    results["prediction_sha256"][split],
                    "lightgbm",
                    *(datetime.fromisoformat(x) for x in frozen["splits"][split]),
                )
            )
        return cls(
            frozen["dataset"]["fingerprint"],
            frozen["dataset"]["dataset_id"],
            tuple(files),
        )

    def lookup(self, transfers: list[Transfer], fingerprint: str) -> dict[int, float]:
        if fingerprint != self.fingerprint or any(
            t.dataset_id != self.dataset_id for t in transfers
        ):
            raise ValueError("Score dataset mismatch")
        if len(transfers) > 20001:
            raise ValueError("Score request exceeds graph limit")
        result = {}
        with duckdb.connect(config={"threads": 2, "memory_limit": "128MB"}) as db:
            for artifact in self.files:
                requested = [
                    t.source_row
                    for t in transfers
                    if artifact.start <= t.occurred_at < artifact.end
                ]
                if not requested:
                    continue
                if artifact.column not in ("score", "lightgbm"):
                    raise ValueError("Unknown frozen score column")
                if sha256_file(artifact.path) != artifact.sha256:
                    raise ValueError("Frozen prediction checksum mismatch")
                db.register(
                    "requested", pa.table({"source_row": sorted(set(requested))})
                )
                rows = db.execute(
                    f'SELECT p.source_row,p."{artifact.column}" '
                    "FROM read_parquet(?) p JOIN requested r USING(source_row) "
                    "ORDER BY p.source_row LIMIT 20002",
                    [str(artifact.path)],
                ).fetchall()
                if len(rows) != len(set(requested)) or len({r[0] for r in rows}) != len(
                    rows
                ):
                    raise ValueError("Missing or duplicate saved scores")
                for row, value in rows:
                    if row in result or not math.isfinite(value) or not 0 <= value <= 1:
                        raise ValueError("Invalid or overlapping saved scores")
                    result[row] = value
        return result
