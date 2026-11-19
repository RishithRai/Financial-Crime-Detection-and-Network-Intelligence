"""Fixed label-free sample investigations; row-level evidence stays in ignored data/."""

import argparse
import hashlib
import json
import os
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from mulegraph.graph import GraphLimitExceeded, graph_session
from mulegraph.investigation import PatternPolicy, investigate
from mulegraph.investigation_scores import FrozenScores
from mulegraph.schema import statement


def run(database_url: str, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    scores = FrozenScores.saved()
    report = {
        "policy": asdict(PatternPolicy()),
        "score_setup_seconds": time.perf_counter() - began,
        "cases": [],
        "selection": "Three fixed source positions plus first test "
        "transaction by event time; no labels or pattern outcomes used",
    }
    with graph_session(database_url, 1) as reader:
        seeds = reader.connection.execute(
            statement(
                """
            SELECT source_row,from_bank_id,from_account,occurred_at
            FROM {core}.transactions WHERE dataset_id=%s
            AND source_row IN (1,2500000,5000000) ORDER BY source_row
        """,
                reader.schema,
            ),
            (reader.dataset_id,),
        ).fetchall()
        focal = reader.connection.execute(
            statement(
                """
            SELECT source_row,from_bank_id,from_account,occurred_at
            FROM {core}.transactions WHERE dataset_id=%s
            AND occurred_at >= %s AND occurred_at < %s
            ORDER BY occurred_at,source_row LIMIT 1
        """,
                reader.schema,
            ),
            (reader.dataset_id, datetime(2022, 9, 9), datetime(2022, 9, 10)),
        ).fetchone()
        if focal:
            seeds.append(focal)
        for i, seed in enumerate(seeds):
            is_focal = i == 3
            cutoff = seed["occurred_at"] if is_focal else datetime(2022, 9, 11)
            start = max(datetime(2022, 9, 1), cutoff - timedelta(days=10))
            item = {
                "case": i + 1,
                "mode": "focal" if is_focal else "account",
                "runs": [],
            }
            digests = []
            for repetition in range(2):
                tracemalloc.start()
                began = time.perf_counter()
                try:
                    result = investigate(
                        reader,
                        start,
                        cutoff,
                        account=None
                        if is_focal
                        else (seed["from_bank_id"], seed["from_account"]),
                        focal_source_row=seed["source_row"] if is_focal else None,
                        scores=scores,
                    )
                    encoded = json.dumps(result, sort_keys=True, indent=2)
                    digest = hashlib.sha256(encoded.encode()).hexdigest()
                    digests.append(digest)
                    if repetition == 0:
                        (output / f"case-{i + 1}.json").write_text(encoded + "\n")
                    item.update(
                        outcome="complete",
                        nodes=result["nodes"],
                        edges=result["edges"],
                        findings=dict(
                            Counter(f["pattern_type"] for f in result["findings"])
                        ),
                        candidates=result["candidate_checks"],
                        scored_findings=sum(
                            f["priority"]["max_transaction_score"] is not None
                            for f in result["findings"]
                        ),
                        focal_scored=result["focal_score"] is not None,
                    )
                except GraphLimitExceeded as error:
                    item.update(outcome=str(error))
                finally:
                    item["runs"].append(
                        {
                            "seconds": time.perf_counter() - began,
                            "python_peak_bytes": tracemalloc.get_traced_memory()[1],
                        }
                    )
                    tracemalloc.stop()
            item["reproduced"] = len(set(digests)) == 1 if digests else None
            report["cases"].append(item)
    (output / "aggregate.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is required")
    report = run(os.environ["DATABASE_URL"], args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
