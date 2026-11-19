# network investigation engine

The engine produces structured transaction-pattern **witnesses for review** from
graph-foundation stage's bounded PostgreSQL/NetworkX historical graphs. It does not classify
accounts as criminal, prove laundering, establish movement of the same money,
or create predictive graph features. Core transactions and saved label-free ML
predictions are its only data inputs; no laundering labels or pattern annotations
are queried. Database records and frozen artifacts remain unchanged.

## Fixed descriptive policy

Defaults were implemented before the representative run, without consulting
labels. They are illustrative investigation settings, not calibrated detection
thresholds or learned typologies. Each response records the entire policy.

| Pattern | Required evidence |
| --- | --- |
| Fan-in | At least 3 distinct composite senders to one receiver within 3,600 seconds, grouped by receiving currency |
| Fan-out | One sender to at least 3 distinct composite receivers within 3,600 seconds, grouped by payment currency |
| Transaction chain | 2–4 directed transactions through distinct accounts, strictly increasing times, total span at most 86,400 seconds |
| Circular flow | 2–4 strictly ordered directed transactions returning to the starting account; no other repeated accounts |
| Rapid movement | An incoming and outgoing pair at an intermediary with a strictly positive gap of at most 300 seconds, also within the path span |

Self-transfers and transactions with zero paid or received amount remain in the
source graph but cannot establish these patterns. Repeated source records remain
individual edges and may create distinct path witnesses. Repeated transfers to
one counterparty do not satisfy fan diversity. Composite bank/account identities
are used throughout. Fan events may be simultaneous: a fan is a concentration
pattern, never an ordered-flow assertion.

Every ordered handoff requires the preceding edge's **receiving currency** to
equal the following edge's **payment currency**. Both original amounts/currencies
are retained as evidence. No amount equality, conservation, allocation, exchange
rate or conversion is inferred. A transaction explicitly carrying different paid
and received currencies retains those fields; local currency continuity between
transactions still does not prove the same funds were forwarded.

## Temporal search and completeness

The graph window is `[start, cutoff)` and all same-cutoff peers and later events
are excluded. Path extension uses strictly greater timestamps; source-row order
only makes output deterministic and never establishes sequence between peers.
Path discovery follows actual directed transaction edges, not static NetworkX
reachability or strongly connected components. Every supplied graph edge is
checked for dataset/source identity, endpoints and temporal bounds.

The detector returns witnesses involving the requested account, which may be a
fan center, counterparty or any account in a path. It emits one earliest qualifying
fan witness per center/currency/direction involving that account. It emits chain
prefixes and individual cycles within the path-length bound, including overlapping
witnesses. A return to the starting account terminates that path. A rapid pair
may also be a chain or two-edge cycle: finding counts are not independent events.
These conventions intentionally do not enumerate every fan window or arbitrarily
long path. No finding is not evidence that no suspicious activity exists.

The existing graph is an incident neighborhood, not induced at its boundary.
Missing boundary edges, the chosen time window and left-censored data limit
pattern coverage. The source has no availability times: event time is assumed
to equal availability. The result is an offline replay, not a verified production
as-of reconstruction.

## Service and output

`investigate(reader, start, cutoff, account=..., ...)` accepts a `GraphReader`
from `graph_session()`. Supplying only `focal_source_row` investigates the focal
transaction's **sender**. To investigate the receiver, pass that composite account
explicitly along with the focal source row. The focal row must occur exactly at
cutoff and touch the chosen account. It is returned as separate context, with
its saved score if available; it never enters historical findings or expansion.
No peer transaction is admitted as a surrogate for the focal event.

A response contains version, dataset fingerprint, root account, window, policy,
graph scope/size, query/work counts, optional focal context, and findings. Each
finding has a deterministic dataset-local ID, type, composite accounts, first/last
timestamps, full source transaction references, exact decimal amounts serialized
as strings, and supporting evidence such as elapsed time or distinct-counterparty
count. Scores and missing-score counts are separate from pattern evidence.
Store row-level responses only under ignored `data/`; public documentation contains
aggregate results only. Source-row references are scoped by dataset identity.

```python
import os
from datetime import datetime
from mulegraph.graph import graph_session
from mulegraph.investigation import investigate, PatternPolicy
from mulegraph.investigation_scores import FrozenScores

scores = FrozenScores.saved()
with graph_session(os.environ["DATABASE_URL"], dataset_id=1) as reader:
    result = investigate(
        reader,
        datetime(2022, 9, 7),
        datetime(2022, 9, 9),
        account=("1", "EXAMPLE_ACCOUNT"),  # illustrative, not a real record
        hops=2,
        policy=PatternPolicy(),
        scores=scores,
    )
```

## Frozen score integration

`FrozenScores.saved()` verifies the selected `lightgbm-stable-v1/history_none`
model/metadata hashes against the committed holdout freeze, and verifies the
holdout freeze copy and saved results' selection. It never deserializes or invokes
the estimator. Each used prediction file is rehashed before lookup. A bounded
DuckDB join retrieves only requested source IDs and the selected score, with
unique alignment, finite [0,1] values and matching dataset provenance required.
Missing or duplicate rows **inside** a saved period are errors, not silently ignored.

Saved validation, test and stress scores are supported. Transactions outside
those saved periods (including training) remain explicitly unscored. No score is
manufactured, and no labels, new predictions, metrics or model fitting are needed.
The separate feature/artifact preservation audit also passed for this stage.
These local hashes provide reproducibility checks, not independent tamper-proof
attestation of jointly editable files.

Findings are sorted by maximum available constituent transaction score, then
stable finding ID; unscored findings sort last. The maximum is a review-ordering
heuristic, not an account probability or calibrated pattern risk. Partial score
coverage is reported. Scores cannot change eligibility, search traversal, window,
policy or finding counts. The focal score is separate. The frozen threshold is
not adjusted or used as a new pattern threshold.

Scores reflect a model selected after these historical periods: this is explicitly
**retrospective prioritization**, not a claim that this model was available at
the source transaction time. Prior reports' non-ACH coverage and synthetic-data
limitations still apply. The graph environment's changed lockfile remains
incompatible with the older full ML audit; its guard is untouched. This new
saved-score reader does not claim to rerun that original environment audit.

## Resource bounds

The original graph node/edge/hop/SQL-time limits still apply. Pattern search adds:

| Resource | Default | Hard ceiling |
| --- | ---: | ---: |
| Path edges | 4 | 6 |
| Candidate checks | 50,000 | 200,000 |
| Findings | 1,000 | 5,000 |
| Transaction references across findings | 10,000 | 20,000 |

Any overflow raises `GraphLimitExceeded`; partial findings are not returned.
Node/edge overflow and SQL timeout likewise propagate. Users may explicitly
narrow the investigation window; the service never silently samples or loosens
limits. Sliding fan windows and time-indexed outgoing adjacency avoid unrestricted
all-path or all-cycle algorithms. Branching still grows with repeated edges;
work and output caps are essential. Recursion depth is at most six edges.

Saved-score lookup is capped at 20,001 references (graph edges plus focal), two
DuckDB threads and a 128 MiB DuckDB memory limit. Parquet scans/hash verification
add latency even for small requests; there is no unbounded in-memory score map.
The full dataset is never loaded into NetworkX. Memory caps bound objects and
references, not arbitrary text lengths or total process/server memory. Timeouts
remain per SQL statement; no total wall-clock SLA is claimed.

## Reproducible representative run

```sh
uv run --locked --env-file .env python -m mulegraph.investigation_benchmark \
  --output data/investigation/new-run
```

The fixed sample uses three existing source positions and the first primary-test
transaction by event time as a focal request. No labels, annotations, high-score
search or successful-pattern search select examples. Each request is repeated
twice. New output directories are required; original evidence is never overwritten.
Detailed findings stay ignored; [verification](investigation_verification.md)
reports aggregate counts, measured timings, failures and limitations.
