"""Versioned pair-history features; timestamp groups exclude all peer edges."""

import argparse
import json
import resource
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from mulegraph.features import literal, output_lock, sha256_file
from mulegraph.rules_baseline import open_features, write_json

VERSION = "graph-features-v1"
COLUMNS = (
    "pair_prior_count",
    "reverse_prior_count",
    "pair_seconds_since_last",
    "reverse_seconds_since_last",
)
PLAN = Path("docs/graph_prediction_plan_v1.json")
# Structs preserve composite identities without delimiter collisions or normalization.
SQL = """
WITH endpoints AS (
 SELECT source_row,occurred_at,split,
 struct_pack(bank:=from_bank_id, account:=from_account) AS sender,
 struct_pack(bank:=to_bank_id, account:=to_account) AS receiver FROM features
), canonical AS (
 SELECT *,least(sender,receiver) AS lo,greatest(sender,receiver) AS hi,
 CASE WHEN sender<=receiver THEN 0 ELSE 1 END AS direction FROM endpoints
), peers AS (
 SELECT lo,hi,occurred_at,
 count(*) FILTER(WHERE direction=0) AS n0,
 count(*) FILTER(WHERE direction=1) AS n1
 FROM canonical GROUP BY lo,hi,occurred_at
), history AS (
 SELECT *,coalesce(sum(n0) OVER prior,0)::BIGINT AS c0,
 coalesce(sum(n1) OVER prior,0)::BIGINT AS c1,
 max(CASE WHEN n0>0 THEN occurred_at END) OVER prior AS t0,
 max(CASE WHEN n1>0 THEN occurred_at END) OVER prior AS t1
 FROM peers WINDOW prior AS (PARTITION BY lo,hi ORDER BY occurred_at
 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
)
SELECT c.source_row,c.occurred_at,c.split,
 CASE WHEN direction=0 THEN c0 ELSE c1 END AS pair_prior_count,
 CASE WHEN c.lo=c.hi THEN 0 WHEN direction=0 THEN c1 ELSE c0 END AS reverse_prior_count,
 epoch(c.occurred_at - CASE WHEN direction=0 THEN t0 ELSE t1 END)
 AS pair_seconds_since_last,
 CASE WHEN c.lo=c.hi THEN NULL ELSE
 epoch(c.occurred_at - CASE WHEN direction=0 THEN t1 ELSE t0 END) END
 AS reverse_seconds_since_last
FROM canonical c JOIN history h USING(lo,hi,occurred_at)
ORDER BY c.source_row
"""


def peak_rss() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024**2 if sys.platform == "darwin" else 1024
    )


def verify_graph(db: duckdb.DuckDBPyConnection, path: Path) -> dict:
    """Exact source/time/split coverage and basic feature invariants against history."""
    db.read_parquet(str(path)).create_view("graph_features", replace=True)
    check = db.execute("""
    SELECT count(*),count(DISTINCT source_row),count(*) FILTER(WHERE
      pair_prior_count<0 OR reverse_prior_count<0 OR
      (pair_prior_count=0) != (pair_seconds_since_last IS NULL) OR
      (reverse_prior_count=0) != (reverse_seconds_since_last IS NULL) OR
      pair_seconds_since_last<=0 OR reverse_seconds_since_last<=0)
    FROM graph_features
    """).fetchone()
    difference = db.execute("""
    SELECT count(*) FROM features f FULL OUTER JOIN graph_features g USING(source_row)
    WHERE f.source_row IS NULL OR g.source_row IS NULL OR
      f.occurred_at != g.occurred_at OR f.split != g.split
    """).fetchone()[0]
    if not check[0] or check[0] != check[1] or check[2] or difference:
        raise ValueError("Graph coverage or temporal value mismatch")
    return {
        "rows": check[0],
        "splits": db.execute("""
      SELECT split,count(*),count(*) FILTER(WHERE pair_prior_count>0),
      count(*) FILTER(WHERE reverse_prior_count>0),
      count(*) FILTER(WHERE pair_prior_count>0 AND reverse_prior_count>0)
      FROM graph_features GROUP BY split ORDER BY split
    """).fetchall(),
    }


def build(features: Path, output: Path) -> dict:
    started = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output_lock(output.parent):
        if output.exists():
            raise ValueError("Graph version exists; refusing overwrite")
        with tempfile.TemporaryDirectory(prefix=".pair-", dir=output.parent) as temp:
            work = Path(temp)
            published = work / "published"
            published.mkdir()
            with duckdb.connect() as db:
                manifest = open_features(db, features)
                db.execute("SET memory_limit='1GB'")
                db.execute(f"SET temp_directory={literal(str(work / 'spill'))}")
                db.execute(
                    f"COPY ({SQL}) TO {literal(str(published / 'features.parquet'))} "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
                checks = verify_graph(db, published / "features.parquet")
            if sha256_file(features / "features.parquet") != manifest["file_sha256"]:
                raise ValueError("Original history changed")
            result = {
                "version": VERSION,
                "duckdb_version": duckdb.__version__,
                "duckdb_memory_limit": "1GB",
                "lock_sha256": sha256_file(Path("uv.lock")),
                "dataset": manifest["dataset"],
                "historical_sha256": manifest["file_sha256"],
                "plan_sha256": sha256_file(PLAN),
                "implementation_sha256": sha256_file(Path(__file__)),
                "file_sha256": sha256_file(published / "features.parquet"),
                "checks": checks,
                "elapsed_seconds": time.perf_counter() - started,
                "peak_rss_mib": peak_rss(),
                "completed_at": datetime.now(UTC).isoformat(),
            }
            write_json(published / "manifest.json", result)
            shutil.move(published, output)
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/features") / VERSION)
    args = parser.parse_args()
    print(json.dumps(build(args.features_dir, args.output), indent=2))


if __name__ == "__main__":
    main()
