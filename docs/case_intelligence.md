# account summaries and investigation cases

`mulegraph.cases` turns bounded historical graph evidence into deterministic
review cases and account-level summaries. ML maxima remain transaction-score
ranking aids. Network evidence remains descriptive. There is no combined
probability, criminal-account label, predictive graph feature, retraining or UI.

## Case grouping

The service first runs the unchanged network-investigation stage detector. It then groups findings
using either of two explicit relationships:

1. A shared source transaction, identified within the dataset.
2. A shared **non-root** composite account, the same currency at that account's
   transaction endpoint, and evidence time intervals overlapping or separated by
   at most 3,600 seconds. The intervals use that account/currency's supporting
   transaction times, not the whole finding's time range.

The root account alone is deliberately insufficient: every finding in an account
investigation already involves it. Otherwise all findings would automatically
become one case. Different banks with the same account string remain distinct.
No monetary amount matching, cross-currency conversion or score threshold creates
a grouping link. These are organizational rules, not validated incident boundaries.

Grouping uses connected components of the finding-link relationships. Links are
transitive: a chain of supported links can group findings whose endpoints are
farther than one hour apart. This can produce broad cases around busy accounts.
A minimal set of supporting merge links is retained with shared transaction or
account/currency/time evidence; it is not a list of every possible relationship.
Case grouping cannot turn static connectivity into verified money movement.

Every distinct finding retains its complete original network evidence in a
finding catalog; cases refer to finding IDs. Repeated copies of the same finding
ID and content are counted as duplicate input records and stored once. Conflicting
content for one ID is rejected. Distinct findings sharing the same transactions
remain distinct findings. Cases count **distinct supporting source transactions**,
not the sum of all finding references. Duplicate-content transfers at different
source rows remain distinct transactions.

Case counts are organizational review counts, **not independent incident counts**.
Accounts can appear in multiple cases. Within a response, shared transactions
join cases, so a supporting transaction cannot belong to two different cases.
Separate requests can overlap and are not automatically deduplicated across runs.

## Account evidence and historical activity

Every node in the returned graph receives an account summary, including accounts
with no pattern findings. Each summary includes:

- Distinct incident historical transactions, scored/unscored counts, coverage,
  maximum available transaction score and missing-score reason counts.
- A separate score summary restricted to its **incident supporting transactions**.
  Another account's high score elsewhere in a case does not become this account's
  score. Case-wide maxima are separately reported at case level.
- Finding IDs and readable descriptive reason codes.
- Incoming/outgoing counts, self-transfers, unique other counterparties, first/last
  observed timestamps and incident transactions per full requested window hour.

A self-transfer contributes one distinct activity transaction and one to each
incoming/outgoing count. It does not create an extra counterparty. Activity and
score counts use source identity, not content deduplication. Monetary values stay
as exact decimal strings with their original currencies; no pooled amount or
score sum is computed.

Root activity is complete **within the requested window** when built by the
bounded graph service. Other accounts are conservatively marked
`complete_for_account=false`: the case layer does not certify their full histories,
even where graph expansion happened to retrieve them. Counts are local observed
context, not lifetime activity. No additional SQL per account expands coverage.

## Scores and missingness

The unchanged `FrozenScores` reader loads existing selected-LightGBM validation,
test and stress predictions, checking provenance and used-file hashes. No model
is invoked, fitted or modified. For each distinct transaction the registry records
its score or null, and one of:

| Status | Meaning |
| --- | --- |
| `SCORED` | Saved transaction review score available |
| `UNSCORED_TRAINING_PERIOD` | September 1–6 transaction; no in-sample prediction substituted |
| `SAVED_SCORE_UNAVAILABLE` | Within September 7–18 but no score supplied to the aggregator |
| `OUTSIDE_SAVED_SCORE_PERIODS` | Outside the documented saved periods |

The production saved-score reader rejects missing/corrupt records within a loaded
prediction period; errors propagate rather than becoming null. Calling the service
without a score provider yields explicit missing scores and `score_model=null`.
The aggregator rejects supplied training-period scores, out-of-period scores,
unknown transaction IDs and nonfinite/out-of-range values.

Coverage is `scored distinct transactions / all distinct transactions` in that
summary's stated scope. It is null for zero transactions. A maximum is null when
none are scored; a genuine zero score remains zero. Account maxima use all incident
local history, supporting maxima use incident pattern evidence, and case maxima
use the union of case evidence. Maxima do not represent account or case
probabilities. More observed transactions provide more opportunities for a high
maximum; coverage and activity must be read alongside it.

Cases and accounts sort by maximum available score descending, then deterministic
identity, with unscored items last. Scores cannot affect case membership or IDs.
Model selection occurred after these source periods: this is retrospective review
prioritization, not a claim that the model was available then. Existing synthetic
data, non-ACH coverage and calibration limitations remain applicable.

## Determinism and reasons

Case IDs hash dataset fingerprint/ID, root, time window, grouping policy and sorted
finding IDs. They identify cases within this request scope, not persistent real-world
entities across windows. Input ordering and score changes do not change membership
or IDs. Evidence and account ordering are deterministic. JSON-ready responses
contain a transaction registry, full finding catalog, case records, account
summaries, policy, resource counters and completeness metadata.

Representative reason codes include `ORDERED_TRANSFER_CHAIN`,
`ORDERED_RETURN_SEQUENCE`, `MULTIPLE_SENDERS_OBSERVED`,
`MULTIPLE_RECIPIENTS_OBSERVED`, `RAPID_INCOMING_OUTGOING_PAIR`, and
`OVERLAPPING_FINDINGS_GROUPED`. Account summaries separately carry
`FROZEN_TRANSACTION_SCORES_AVAILABLE`, `INCOMPLETE_SCORE_COVERAGE`,
`UNSCORED_TRAINING_TRANSACTIONS`, `ACCOUNT_HISTORY_NOT_CERTIFIED_COMPLETE`,
`LOCAL_GRAPH_SCOPE`, or `NO_NETWORK_PATTERN_WITNESS` where applicable.
No-witness and missing-score codes must not be interpreted as evidence of safety.

## Temporal integrity and bounded execution

The service uses one read-only repeatable-read PostgreSQL session and the existing
`[start, cutoff)` graph contract. Findings are checked against the exact historical
transaction registry, including endpoints and values. Cutoff peers and later events
cannot enter aggregation. An optional focal row at cutoff is returned separately
and excluded from **all** historical case/account score and activity summaries.
Focal-only requests use its sender; an explicit receiver account can be requested.

Graph, pattern-candidate, finding and evidence-reference limits remain unchanged.
The case layer also caps input at 2,000 nodes, 20,000 graph transactions, 5,000 finding
records and 20,000 finding references. Account-link comparisons default to 100,000,
with a hard maximum of 500,000; the gap defaults to one hour with a hard maximum
of one day. Inverted transaction/account-currency indexes avoid unconditional
all-finding pairs, but busy shared-account buckets can still hit the comparison cap.

Any upstream or case-budget failure raises an error without returning partial
cases or low-risk summaries. Successful service responses state
`search_completed_within_limits=true` and `global_evidence_complete=false`.
The standalone `summarize()` helper defaults to `search_complete=false` for
caller-supplied findings; it does not certify a partial imported finding list as
an exhaustive search. It validates references and identities, not the semantic
truth of arbitrary supplied pattern declarations. Use the service for detection.

The neighborhood, fixed pattern definitions, path lengths, chosen window and
missing availability timestamps all constrain completeness. No late-arrival
handling or end-to-end latency guarantee is introduced. Row-level outputs remain
under ignored `data/cases/`; only aggregate documentation is committed.

## Usage

```python
import os
from datetime import datetime
from mulegraph.cases import investigate_cases
from mulegraph.graph import graph_session
from mulegraph.investigation_scores import FrozenScores

scores = FrozenScores.saved()
with graph_session(os.environ["DATABASE_URL"], 1) as reader:
    report = investigate_cases(
        reader,
        datetime(2022, 9, 1),
        datetime(2022, 9, 11),
        account=("1", "EXAMPLE_ACCOUNT"),
        scores=scores,
    )
```

Run the fixed label-free sample into a new local directory:

```sh
uv run --locked --env-file .env python -m mulegraph.case_benchmark \
  --output data/cases/new-run
```

See [actual verification and measured results](case_verification.md),
[network-pattern policy](network_investigation.md), and
[graph scope and availability assumptions](transaction_graph.md).
