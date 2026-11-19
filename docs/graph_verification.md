# Transaction graph verification

Verified on October 15, 2026 (Asia/Kolkata), with Python 3.12.15, NetworkX 3.7
and the existing local PostgreSQL service. Graph construction uses core
transactions only. No laundering labels or patterns were accessed for graph
construction or benchmarking; no real labels were accessed by this stage.
Existing integration tests use only synthetic labels in disposable schemas.
No model, threshold, historical feature, source record or database index changed.

## Measured graph queries

The actual database contains **5,078,345 transactions**. The benchmark used
September 1 inclusive through September 11 exclusive, caps of 500 nodes and
5,000 edges, and a five-second SQL statement timeout. Three fixed source-position
senders and one busier sender from a bounded 10,000-row prefix were sampled
without labels. Each one/two-hop case ran three times in one read-only snapshot.
Results below aggregate successful requests rather than publish account records.

| Request | Successful cases × repetitions | Nodes | Transactions | Elapsed min / median / max | Max traced Python allocation |
| --- | ---: | ---: | ---: | --- | ---: |
| One hop | 3 × 3 | 3–14 | 3–114 | 1.524 / 5.619 / 23.045 ms | 0.243 MiB |
| Two hops | 3 × 3 | 11–107 | 34–453 | 9.304 / 49.345 / 103.453 ms | 0.972 MiB |

Each successful case reproduced the same complete edge/attribute digest across
all three runs. These timings include construction, statistics and digesting
with `tracemalloc` enabled, but exclude connection setup and seed selection.
Sequential runs benefit from cache warming. Allocation peaks are traced Python
allocations during each run, not total process RSS, native-library memory or
PostgreSQL memory. The small sample is not a production performance guarantee.

The busier account exceeded the edge cap for both hop settings. All six attempts
raised the expected error in **68.000–97.282 ms**, with at most **5.180 MiB** traced
allocation; no partial network was returned. A separate one-edge cap also
rejected the populated history. Oversized requests require a narrower explicit
window or hop count, rather than silently returning misleading statistics.

`EXPLAIN (ANALYZE, BUFFERS)` of all four actual account-history queries used both
`transactions_sender_time_idx` and `transactions_receiver_time_idx`, with
incremental sort and a bounded merge. Server execution times were **0.063–5.642 ms**
after the graph measurements. No full transaction-table scan appeared in these
history plans. The benchmark's independent scalar count scans the dataset on
the server, returning only one count; it does not load it into Python.

The final aggregate measurements are retained under ignored
`data/graph/benchmark-v1-final.json`. The first measurement was preserved as
`benchmark-v1.json`; the final run followed a reporting fix that marks graph
reproducibility as undefined for failed requests instead of vacuously true.
Neither run accessed labels or modified database records.

## Tests and preservation

| Check | Actual result |
| --- | --- |
| `uv sync --locked` | Passed |
| Ruff lint | Passed |
| Ruff formatting | Passed; 61 files already formatted |
| Complete PostgreSQL-enabled suite | **113 passed in 5.44 seconds**; no failures, skips or warnings |
| Graph-specific tests | 4 unit and 4 PostgreSQL tests included above |
| Frozen original artifacts | All 66 source artifact hashes from the ML holdout freeze match |
| Frozen implementation | Every implementation hash in the holdout freeze matches |
| Historical feature and manifest | Both saved hashes match |
| Holdout predictions | Both saved prediction hashes match |
| Existing dependency versions | Unchanged; NetworkX 3.7 added |
| Real database operations | Read-only repeatable-read transaction; no DDL or writes |

Tests cover parallel/duplicate-content transactions, reverse edges, self-loops,
cross-bank account strings, exact Decimal attributes, lower time boundaries,
future/same-time exclusion, focal separation, deterministic replay, hop boundaries,
node/edge caps, empty histories and invalid identifiers/windows/limits. Disposable
`mg_test_*` graph schemas contain **no labels table**, exercising the actual SQL
without label availability. They verify dataset isolation, missing/incomplete
dataset rejection, session isolation/read-only settings, rejection of a write,
and actual PostgreSQL statement-timeout cancellation. Synthetic future/peer
insertions cannot change prior-window output. Only these test schemas are removed.

Historical feature SHA-256 remains
`dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`.
The old lock hash is
`bbbfafc3618c37ddb16fe145bd9604ef5ee8271dee64c25beb65c6d9579d96a0`;
the NetworkX-enabled lock hash is
`241a4fceecba22d249e93974a5c12be086df3f3a39d19946abf87cc287b3d44f`.
The frozen ML validator deliberately rejects the newer lock. Its manifests were
not changed: old audits require the prior source/environment, as explained in
the [architecture document](transaction_graph.md). The artifact preservation
check compared saved hashes directly; it did not rerun model fitting or label
evaluation. Evidence is retained in ignored `data/graph/preservation-v1.json`.

## Commands and limitations

From the repository root, after installing dependencies as described in the README:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked --env-file .env python -m mulegraph.graph_benchmark \
  --output data/graph/benchmark-new.json
```

There are no execution blockers. Availability timestamps remain absent, so this
is event-time replay under an immediate-availability assumption. Neighborhoods
are bounded incident expansions, not induced or whole-network graphs. Static
directed reachability does not establish temporal flow of funds. Row caps bound
Python object counts; statement timeouts are per query rather than end-to-end
request deadlines. Large/high-activity histories can legitimately be rejected.

The frozen ML reports' non-ACH coverage and shifted stress-population concerns
remain unresolved by graph visualization or connectivity. Graph structure does
not confer criminal-account labels. Investigation workflows, time-respecting paths, and predictive graph features
have separate contracts; see [network investigation](network_investigation.md)
and [graph predictors](graph_prediction.md).
