# Case intelligence verification

Executed on October 15, 2026 (Asia/Kolkata), using the existing locked Python
3.12.15 environment and PostgreSQL service. No dependencies, frozen models,
thresholds, historical features or real database records changed. No real
laundering labels or pattern annotations were accessed, and no new predictions
were generated. Existing ML scores are used only for retrospective prioritization.

## Representative results

The same fixed, label-free sample as network-investigation stage was used: three source-position
senders and the first primary-test transaction by event time as a focal request.
Windows, pattern defaults and graph caps were unchanged. Each request ran twice.
Three completed with exactly identical serialized case/account summaries on repeat;
one hit the existing 1,000-finding cap on both runs. The failed request returned
no partial cases and has unknown evidence totals, not zero risk.

Across the three successful requests, counted once:

| Measurement | Actual result |
| --- | ---: |
| Preserved individual findings | 147 |
| Review cases | 21 |
| Distinct supporting transactions | 127 |
| Distinct historical graph transactions | 702 |
| Historical transactions with saved scores | 204 |
| Explicitly unscored training transactions | 498 |
| Cases with at least one scored supporting transaction | 5 |
| Cases without scored supporting transactions | 16 |

The three requests grouped 5 findings into 4 cases, 3 into 1, and 139 into 16.
Their 147 findings retain the prior composition: 141 chain witnesses, five fan-in
witnesses and one rapid pair. No witnesses were discarded to reduce case counts.
Distinct source IDs were also deduplicated across the successful sample when
checking the 127 supporting and 702 historical transaction totals above; these
particular requests did not share historical transactions.

The overall historical score coverage in this sample is **204/702 (29.06%)**.
This is not case-level or account-level coverage: each output reports its own
correct denominator. Some cases are entirely unscored even though other local
historical transactions have scores. No in-sample training predictions were used
to fill the gap. Network witnesses remain visible without ML scores.

These are 21 organizational review groups, **not 21 verified independent incidents**.
Transitive shared-evidence links can create broad groups; different cases can
share accounts. Repeated transaction content at distinct source rows remains
separate evidence. A case-wide high transaction score is not assigned to every
account in the case. Each account's maximum uses only its own incident transactions.

## Measured costs

Successful executions took **103.608–470.538 ms**, median **355.583 ms**, including
bounded SQL retrieval, detection, saved-score lookup, aggregation and JSON
serialization with `tracemalloc` enabled. First executions also wrote their ignored
response files. Initial score-provider setup took **2.789 ms** separately.
Connection setup and fixed-seed selection are outside these timings; cache warming
and tracing overhead apply. These small local measurements are not a throughput
or production latency guarantee.

Peak traced Python allocation was **4.708 MiB** for successful runs; this excludes
native DuckDB/PostgreSQL memory and is not process RSS. The completed requests
used **1–2,637 case-link comparisons**. The high-branching request failed upstream
in **248.871–384.119 ms**. No grouping limit, pattern threshold, score policy or
window was tuned in response to these outcomes.

Local detailed outputs and aggregate timing evidence are retained in ignored
`data/cases/v1/`. The case reports include transaction references, findings,
account summaries and missingness; none of these row-level files is committed.

## Verification and preservation

| Check | Actual result |
| --- | --- |
| Complete PostgreSQL-enabled suite | **133 passed in 5.99 seconds**, no failures, skips or warnings |
| Ruff lint and formatting | Passed |
| New tests | 8 unit cases and 1 PostgreSQL case-service test |
| Original frozen artifacts | All 66 saved source hashes match |
| Frozen implementation | All holdout-freeze implementation hashes match |
| Historical features and manifest | Both saved hashes match |
| Holdout prediction files | Both saved hashes match |
| Dependency lock | Unchanged from graph-foundation stage |
| Real SQL operations | Read-only repeatable-read graph queries |

Tests cover overlapping and transitive cases, root-only non-merging, distinct-bank
identities, currency/time separation, preserved individual findings, duplicate
finding records, conflicting evidence, distinct duplicate-content transfers,
self-transfers, account versus case score scope, missing and zero scores, training
score rejection, empty history, temporal boundaries, nonfinite scores, resource
limits and deterministic membership/order. Changing scores changes ranking but
not case membership/IDs. Imported findings default to incomplete search status.
The PostgreSQL service test verifies focal exclusion, training missingness,
historical activity and reproducibility in a disposable core-only `mg_test_*`
schema. Existing graph, pattern, ML and ingestion tests also passed; any label
fixtures in the suite are synthetic, not real dataset labels.

Artifact preservation evidence is in ignored `data/cases/v1/preservation.json`.
Historical feature SHA-256 remains
`dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`.
The pre-graph ML lockfile guard remains unchanged; a full original ML audit still
requires its original source/environment. This milestone directly checked saved
hashes without retraining, re-evaluating labels or weakening that guard.

## Commands and remaining gaps

From the repository root, after installing dependencies as described in the README:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked --env-file .env python -m mulegraph.case_benchmark \
  --output data/cases/new-run
```

No execution blockers remain. High-branching searches can exceed caps. Case
boundaries are heuristic and not investigator-validated; links can chain across
longer spans. Neighbor-account histories are conservatively uncertified outside
the returned local context. Global search coverage, actual attribute availability,
probability calibration and synthetic-data generalization remain unresolved.
Case IDs are request-scoped, with no cross-request case reconciliation or persistent
case lifecycle. ML maxima favor accounts with more scored opportunities and need
coverage/activity context. No UI, combined probability or criminal-account labels
were introduced.

See [architecture, aggregation semantics and usage](case_intelligence.md).
