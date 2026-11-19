# investigation evidence quality

The read-only API now returns a separate `evidence_quality` annotation catalog,
keyed by original finding ID. The original `report` is unchanged. No detector,
case membership, score, threshold, model, feature or real database record changes.
No real labels or pattern annotations are accessed. This is a descriptive aid,
not another risk model or an evidential strength rating.

## What analysts can assess

In a review group, choose a pattern type and an original witness. The new
**How much does this observation tell us?** section separates:

- What the records support: an ordered account connection or a fan concentration.
- Exact incoming received and subsequent outgoing paid amounts at each intermediary.
- Signed outgoing-minus-incoming difference, only for matching endpoint currencies.
- Elapsed time, in readable units with exact seconds, and the number of other local
  transactions at that account strictly between the two times.
- Missing saved scores, incomplete account histories and time-window limitations.
- Remaining uncertainty and useful independent records: statements/balances,
  payment references/purpose, counterparty relationships, fees/conversion records
  and actual arrival/availability times.

The same annotation follows a selected witness into the network explorer. Existing
pattern-type summaries and direct witness navigation avoid hundreds of repeated
cards while preserving every witness. Group membership and network references
remain unchanged; the original chronological sequence remains inspectable.

An amount mismatch means **numerical inequality**, not a suspiciousness threshold.
Equal recorded amounts are explicitly not proof of the same funds. No tolerance,
ratio cutoff, allocation, balance reconstruction, currency conversion or combined
probability is introduced. Timing is reported without new “fast/slow” thresholds.
Possible explanations for differences are questions for follow-up, not inferred
fees, splitting, pooling or established purposes. Fan observations are not ordered
paths; their amounts are not compared as handoffs.

## Implementation and safeguards

`evidence_quality.assess_evidence()` is a pure bounded report consumer. It verifies
supporting references against historical rows, rejects duplicate source IDs,
checks `[start, cutoff)` and strictly increasing connected handoffs, and never
queries a database or estimator. Decimal subtraction uses sufficient precision
and serializes fixed-point strings, preserving small differences and large values.
Paid/received strings and source timestamps remain untouched. Different handoff
currencies produce “not comparable” rather than a converted difference.

Sorted incident-time indexes and binary search count intervening local activity;
self-transfers count once, timestamp-boundary peers do not count as intervening,
and the count is not certified complete outside the returned neighborhood. Scores
are counted from distinct supporting transactions; zero is a score, missing is
unknown. Training missingness is retained. The layer accepts at most 5,000 history
rows, 1,000 findings and 100,000 reference visits; the existing detector's stricter
default 10,000-reference cap still applies to API investigations. Saved-report
assessment limits each input to 32 MiB and ten examples and refuses output overwrite.

## Reproducible label-independent examples

Selection was fixed before inspecting new annotations: the three completed saved
case-intelligence stage examples (fixed source positions and first test-time focal request),
plus user-requested transaction 2612189 in default and wider one-hop scopes. The
previous high-branching sample remains a failure, not a zero-finding example.
No search was conducted to force a desired amount relationship or pattern.

| Existing example | History rows | Witnesses / groups | Observed patterns | Evidence limitation |
| --- | ---: | ---: | --- | --- |
| `data/cases/v1/case-1.json` | 195 | 5 / 4 | 3 chains, 2 fan-in | All 5 witnesses have missing scores; all 3 handoffs differ in amount |
| `data/cases/v1/case-3.json` | 34 | 3 / 1 | 1 chain, 2 fan-in | Supporting scores present; account histories still incomplete |
| `data/cases/v1/case-4.json` | 473 | 139 / 16 | 137 chains, 1 fan-in, 1 rapid pair | 118 witnesses have missing scores; 179 handoff observations reuse 104 distinct pairs |
| Requested focal, preceding 24 hours | 22 | 0 / 0 | None within scope | Absence of findings does not establish safety |
| Requested focal, September 1 start | 197 | 706 / 5 | 704 chains, 1 fan-out, 1 rapid pair | 528 witnesses have missing scores; all account histories include incomplete coverage |

The wider focal report has 705 handoff observations over 704 distinct source
pairs; every comparable amount differs. Gaps range from 240 to 86,100 seconds.
The older focal example includes a 120-second rapid pair. All examples preserve
currency continuity at observed handoffs. These results neither prove nor disprove
related fund movement. No real circular-flow or equal-amount example occurs in
this fixed sample; synthetic tests exercise those paths and cross-currency refusal.
Requests can overlap, so totals across examples are not independent incident counts.

The five saved reports reproduced identical annotation results, with original
reports unchanged. Annotation-only times ranged from 0.027 to 8.688 milliseconds
on the final local run, excluding file reading, SQL, SHAP, serialization and UI.
This small diagnostic sample is not a load benchmark or an accuracy estimate.
Hashes, counts and timings are retained in ignored
`data/dashboard/7a/examples-final.json`; earlier measurement output is preserved.

To replay the saved evidence assessment (choose a new output filename):

```sh
uv run --locked python -m mulegraph.evidence_quality_report \
  data/cases/v1/case-1.json data/cases/v1/case-3.json data/cases/v1/case-4.json \
  data/dashboard/7a/day.json data/dashboard/7a/wide.json \
  --output data/dashboard/7a/examples-new.json
```

The last two files are the original `report` objects from the existing local API
for `/api/transactions/2612189/investigation?scope=day` and `?scope=wide`.
For an independent database replay of the earlier fixed sample, the unchanged
`mulegraph.case_benchmark --output data/cases/new-example-run` command documented
in [case verification](case_verification.md) recreates the requests and records
resource failures. These files contain row-level evidence and remain ignored.

## Verification and portfolio readiness

Final verification: **176 PostgreSQL-enabled tests passed in 8.26 seconds**, without
failures, skips or warnings. Twelve new backend tests cover exact Decimal values,
zero/missing scores, incomplete history, handoff context, equality, different
currencies, ordered types, peer/future rejection, corrupted references, duplicate
IDs, limits, empty findings, replay and overwrite prevention. The PostgreSQL HTTP
test verifies the separate annotation catalog alongside the unchanged historical
report. All database fixtures are disposable synthetic schemas.

Frontend: **11 unit tests**, production build and formatting passed. All **3 real
Chrome/Playwright workflows passed in 33.6 seconds**. Browser
verification exercises all five real groups and all 706 retained witness IDs via
membership/count checks, each category's last-witness navigation, evidence support
text, handoff-card counts, exact graph references, node/edge clicks, timeline and
navigation. The two-hop resource failure and explicit recovery remain covered.
Ruff lint and format checks passed (99 Python files). All 66 original frozen
artifact hashes, frozen implementation, features/manifest and saved predictions
match. Dependency files and existing Python service implementations are unchanged
apart from the thin API's new annotation call. No integrity guard was weakened.

Desktop and mobile browser screenshots remain in ignored `data/dashboard/7a/`.
The new panel exposes uncertainties beside the actual monetary comparison; a
single witness is rendered at a time. This is an engineering walkthrough, not a
study with financial crime analysts. Dense mobile graphs require zoom, pages remain
long, and additional-evidence prompts are generic because customer purpose,
statements and availability records are absent. No inference accuracy, investigator
agreement or time-to-decision improvement is claimed. Early lint issues were fixed;
Playwright's terminal color-environment warning is unrelated to app behavior.

**Ready for a scoped final portfolio review and guided demonstration**, with these
limitations prominently disclosed. It is not ready for operational deployment or
for claims of verified money tracing. Before such use, independent analyst review,
representative untouched data, actual availability validation, calibration and
review-policy work, security/access controls and production capacity testing remain
necessary. Existing synthetic-data dependence, development-holdout qualifications,
missing training scores, local scope and non-independent witnesses remain material.

Use the unchanged [application launch command](analyst_application.md), open
http://127.0.0.1:8000, search 2612189, explore **Use wider history**, and review any
group's original witnesses. Streamlit remains available as the fallback.
