# Network investigation verification

Executed on October 15, 2026 (Asia/Kolkata), using the locked Python 3.12.15
and NetworkX 3.7 environment and existing PostgreSQL service. No dependency,
model, threshold, feature, real database record or index changed. Graph queries
were read-only. No real laundering labels or pattern annotations were accessed.

## Representative investigations

The preselected sample comprised three fixed source-position senders and the
first primary-test transaction by event time as a focal request. Account requests
used September 1 inclusive through September 11 exclusive. The focal request
used earlier history strictly before its timestamp; all peers and future events
were excluded. Default two-hop graphs and fixed pattern policy were used.
The focal remained separate from findings.

Each of the four requests ran twice. Three completed with byte-identical serialized
findings, evidence and priorities on repetition. Their graphs contained 11–107
nodes and 34–473 transactions. One account exceeded the 1,000-finding limit on
both attempts. This was reported as a resource-limit failure with no partial
result; no thresholds, windows or limits were changed to obtain a success.

Across the three completed requests, counting each request once:

| Pattern | Witnesses |
| --- | ---: |
| Fan-in | 5 |
| Fan-out | 0 |
| Transaction chains | 141 |
| Circular flows | 0 |
| Rapid movement | 1 |

These **147 witnesses** overlap and may reuse transaction edges. They are not
147 independent incidents, verified money flows, or laundering cases. No cycle
or fan-out witness was found in this small successful sample; both are covered
by synthetic positive tests, and no examples were selected using ground truth.
A rejected request has unknown pattern totals, not zero findings.

Saved LightGBM scores prioritized **28 of 147 findings**; the remaining 119 had
no scored constituent transactions. Partial coverage is explicitly counted in
each finding, and the focal transaction had a saved score. Training-period rows
have no saved predictions in this reader and stay unscored. No fresh prediction,
retraining, label retrieval, model evaluation or threshold adjustment occurred.

The observed patterns are descriptive: several counterparties can converge on
an account, and an ordered chain can contain overlapping prefixes and repeated
relationships. The rapid pair establishes a short positive incoming-to-outgoing
gap with compatible handoff currency, not that the received money was forwarded.
Only synthetic tests establish known expected patterns; real-dataset precision
or recall cannot be estimated from this label-free sample.

## Measured costs

The six successful executions took **91.111–368.855 ms**, median **173.481 ms**,
including bounded SQL retrieval, pattern search, saved-score checks/lookup and
JSON serialization, with `tracemalloc` enabled. Initial score-provider setup
(model/metadata provenance checks without model loading) took **1.769 ms**.
Connection setup and seed selection are outside these measurements. The first
successful run also wrote its ignored evidence file within the measured interval.
Repeated requests benefit from cache warming.

Peak traced Python allocation was **4.708 MiB** for successful runs. This is not
process RSS, native DuckDB allocation or PostgreSQL memory. Successful requests
used **113–2,016 candidate checks**. The rejected request took **229.814–242.100 ms**;
the combinatorial expansion of repeated-edge paths reached the output cap despite
a graph small enough for graph-foundation stage. This is an expected investigation limit,
not an execution crash or evidence of suspicious behavior.

Detailed results are retained only under ignored `data/investigation/v1/`:
`case-*.json` contains successful row-level witnesses, and `aggregate.json`
contains timings, counts and failures. The benchmark did not publish failed
partial findings. This is a small local diagnostic sample, not a throughput
benchmark or assurance that all account histories fit the limits.

## Verification and preservation

| Check | Actual result |
| --- | --- |
| Complete PostgreSQL-enabled suite | **124 passed in 5.69 seconds**, no failures, skips or warnings |
| Ruff lint and formatting | Passed after formatting an existing graph-document example |
| New tests | 10 unit cases and 1 PostgreSQL service test |
| Frozen original artifacts | All 66 saved source hashes match |
| Frozen implementation | Every implementation hash in the holdout freeze matches |
| Historical features/manifest | Both saved hashes match |
| Holdout predictions | Both saved hashes match |
| Dependency lock | Unchanged from graph-foundation stage |
| Real-dataset construction | Core-only read-only repeatable-read PostgreSQL snapshot |

Tests cover positive chains, cycles, fans and rapid pairs; simultaneous and
reverse-time negatives; composite identities; repeated-counterparty non-fans;
window boundaries; self/zero-transfer exclusion; currency mismatch; invalid
future graph input; candidate/finding/evidence limits; deterministic ordering;
score corruption, missing/duplicate/nonfinite rows, wrong dataset and model/freeze
tampering; explicit unknown-period scores; and prioritization that leaves pattern
membership unchanged. The PostgreSQL test uses a disposable core-only schema
with no labels table and exercises account and focal service requests, strict
cutoff exclusion and mismatched-currency rejection. Existing temporal graph,
read-only, SQL-timeout and model tests also passed. Existing label-related tests
use synthetic disposable fixtures, never real dataset labels.

Preservation evidence is stored in `data/investigation/v1/preservation.json`.
The old full ML audit still requires its original lockfile; that guard was not
weakened. The direct preservation check compared bytes without opening labels or
rerunning training/evaluation. Historical feature SHA-256 remains
`dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`.

## Commands and remaining limitations

From the repository root, after installing dependencies as described in the README:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked --env-file .env python -m mulegraph.investigation_benchmark \
  --output data/investigation/new-run
```

No execution blockers remain. High-branching requests can legitimately exceed
finding limits. Coverage is local, time-bounded and length-bounded; boundary
neighborhood edges and long paths may be absent. Availability timestamps remain
unknown. Focal-only requests investigate the sender; receiver context requires
an explicit receiver-account request. Saved scores provide retrospective,
uncalibrated ordering with partial temporal coverage and known synthetic-data
limitations. No account labels, criminality claims, UI or predictive graph
features were introduced.

See [policy, architecture and usage](network_investigation.md).
