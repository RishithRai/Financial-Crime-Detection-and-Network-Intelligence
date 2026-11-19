"""Read-only local graph measurements; writes aggregates, never account records."""

import argparse
import hashlib
import json
import os
import time
import tracemalloc
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import networkx as nx

from mulegraph.graph import (
    HISTORY_SQL,
    GraphLimitExceeded,
    Limits,
    graph_session,
    statistics,
)
from mulegraph.schema import statement


def plan_nodes(node: dict) -> list[dict]:
    result = [{k: node[k] for k in ("Node Type", "Index Name") if k in node}]
    for child in node.get("Plans", []):
        result.extend(plan_nodes(child))
    return result


def measure(database_url: str, dataset_id: int) -> dict:
    start, cutoff = datetime(2022, 9, 1), datetime(2022, 9, 11)
    limits = Limits(max_nodes=500, max_edges=5000, max_hops=2)
    report = {
        "version": "graph-v1",
        "networkx": nx.__version__,
        "window": [start.isoformat(), cutoff.isoformat()],
        "limits": asdict(limits),
        "timing": "Three sequential runs with tracemalloc; connection setup excluded",
        "cases": [],
    }
    with graph_session(database_url, dataset_id, limits=limits) as reader:
        c = reader.connection
        report["dataset_fingerprint"] = reader.fingerprint
        report["source_rows"] = c.execute(
            statement(
                "SELECT count(*) AS n FROM {core}.transactions WHERE dataset_id=%s",
                reader.schema,
            ),
            (dataset_id,),
        ).fetchone()["n"]
        # A bounded, deterministic core-only sample. No activity/label global search.
        seeds = c.execute(
            statement(
                """
            SELECT from_bank_id,from_account FROM {core}.transactions
            WHERE dataset_id=%s AND source_row IN (1,2500000,5000000)
            ORDER BY source_row
        """,
                reader.schema,
            ),
            (dataset_id,),
        ).fetchall()
        busy = c.execute(
            statement(
                """
            SELECT from_bank_id,from_account FROM (
                SELECT from_bank_id,from_account FROM {core}.transactions
                WHERE dataset_id=%s ORDER BY source_row LIMIT 10000
            ) sample GROUP BY from_bank_id,from_account
            ORDER BY count(*) DESC,from_bank_id,from_account LIMIT 1
        """,
                reader.schema,
            ),
            (dataset_id,),
        ).fetchone()
        if busy:
            seeds.append(busy)
        for case, seed in enumerate(seeds, 1):
            account = (seed["from_bank_id"], seed["from_account"])
            for hops in (1, 2):
                timings, peaks, digests = [], [], []
                item = {"case": case, "hops": hops}
                for _ in range(3):
                    tracemalloc.start()
                    began = time.perf_counter()
                    try:
                        result = reader.network(account, start, cutoff, hops)
                        item["statistics"] = statistics(result.graph, account)
                        item["history_queries"] = result.history_queries
                        item["outcome"] = "complete"
                        digests.append(
                            hashlib.sha256(
                                repr(
                                    list(result.graph.edges(keys=True, data=True))
                                ).encode()
                            ).hexdigest()
                        )
                    except GraphLimitExceeded as error:
                        item["outcome"] = str(error)
                    finally:
                        timings.append(time.perf_counter() - began)
                        peaks.append(tracemalloc.get_traced_memory()[1])
                        tracemalloc.stop()
                item.update(
                    seconds=timings,
                    python_peak_bytes=peaks,
                    repeated_graphs_equal=(len(set(digests)) == 1 if digests else None),
                )
                report["cases"].append(item)
            # Explain the actual bounded query; retain only plan/index names.
            plan = c.execute(
                statement(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + HISTORY_SQL,
                    reader.schema,
                ),
                {
                    "dataset": dataset_id,
                    "bank": account[0],
                    "account": account[1],
                    "start": start,
                    "cutoff": cutoff,
                    "limit": 5001,
                },
            ).fetchone()["QUERY PLAN"][0]
            report.setdefault("query_plans", []).append(
                {
                    "case": case,
                    "execution_ms": plan["Execution Time"],
                    "nodes": plan_nodes(plan["Plan"]),
                }
            )
        # Deliberately tiny cap must reject a populated sample, not silently sample.
        if busy:
            reader.limits = Limits(max_edges=1)
            try:
                reader.history(
                    (busy["from_bank_id"], busy["from_account"]), start, cutoff
                )
            except GraphLimitExceeded:
                report["tiny_budget_rejected"] = True
            else:
                report["tiny_budget_rejected"] = False
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is required")
    if args.output.exists():
        parser.error("Choose a new aggregate output path; existing report preserved")
    report = measure(os.environ["DATABASE_URL"], args.dataset_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(
        f"Measured {len(report['cases'])} bounded graph cases; aggregate report saved"
    )


if __name__ == "__main__":
    main()
