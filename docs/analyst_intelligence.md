# analyst intelligence and evidence workflow

The React application now provides a fixed-template investigation summary and a
focused review-group workspace. All statements derive from the existing report;
no language model, new predictions, new grouping or detection logic is involved.
The Python services and Streamlit fallback are unchanged.

## Using the workspace

Follow the [application launch instructions](analyst_application.md). Review a
transfer, then explore connected accounts. The summary separates the frozen,
uncalibrated model score from observed historical activity. It reports incoming
and outgoing root-account transfers, counterparties, distinct supporting source
references, overlapping witnesses and available score coverage. Self-transfers
count in both directions; network observations do not establish movement of the
same funds, intent or wrongdoing.

Choose **Review the groups**, then select one group. Cards show its accounts,
distinct supporting transfers, pattern types, time span and scored denominator.
Only that group's original findings are offered below. Repeated witnesses are
summarized by pattern type; previous/next controls and **Go to witness** retain
access to every original witness. The numbered sequence presents chronological
source-backed evidence. Fan observations can be simultaneous and are not ordered
paths. Original identifiers, evidence fields and group reason codes remain in
expandable details. Existing transaction review retains SHAP technical details.

The group network retains the entire bounded neighborhood and highlights the
selected evidence. Grouped arrows display “N of M selected”: only N of the M
original transfers belong to the selection. No source references or endpoints
are replaced. Other relationships are dimmed, the focal transfer stays dashed
amber, the root retains an amber ring and clicked accounts have a cyan ring.
**Show sequence on network** opens its exact timeline. **Return to full network**
clears the selection without another query or changing scope.

Missing scores are explicitly unknown, not low scores. The summary covers only
the returned neighborhood. Neighbor histories may be incomplete; the focal and
same-cutoff peers remain separate from strictly earlier historical evidence.
Existing query and finding limits still reject oversized requests without partial
results. Review groups are organizational units, not independent incidents.

## Actual verification

Verified October 15, 2026 against saved transaction 2612189, September 1 historical
start, one hop. The report retains **15 historical accounts, 197 transactions,
16 grouped arrows, 5 review groups and 706 overlapping witnesses**. One actual
focal transfer and its focal-only account remain separate. The summary reports
172 distinct supporting transactions and 50/197 historical transactions scored.
These are existing report counts, not a new evaluation of detection quality.

Playwright selected all five groups and compared highlighted accounts and source
references against each original case. Every historical reference remained in
the rendered graph. Each pattern category retained its original witness count,
and direct navigation to its last witness matched its original ID. Group counts
sum to 706. Browser checks also exercised actual canvas node/edge clicks, zoom,
pan, transfer inspection, exact sequence highlighting, full-network reset,
navigation, and existing two-hop failure/recovery. No application page errors
were recorded.

| Check | Actual result |
| --- | --- |
| PostgreSQL-enabled Pytest | 164 passed in 10.01 seconds; no skips or warnings |
| Frontend unit tests | 10 passed |
| Real Chrome/Playwright tests | 3 passed in 34.0 seconds |
| Frontend production build | Passed |
| Frontend formatting | Passed |
| Ruff lint and formatting | Passed; 95 Python files formatted |
| Frozen original artifacts | All 66 hashes match |
| Frozen implementation, feature file and manifest | All saved hashes match |
| Saved prediction files | All used hashes match |
| Dependency files | Unchanged |

The new unit tests cover exact case membership, overlapping source-reference
counts, immutable witness data, zero versus missing scores and evidence-grounded
pattern descriptions. Backend integration tests use disposable synthetic schemas;
real browser investigations use read-only core data and saved scores, with no
real labels or pattern annotations. No model, score, threshold, historical feature,
case logic or database record changed. The preserved lock SHA-256 remains
`1125a6c6883aaf54cfd63e169df5460ea9a81894a0afac5947d65d2e9f0b8384`.

Actual desktop and 390-pixel mobile screenshots were inspected. Evidence and
screenshots are retained under ignored `data/dashboard/6e/`, including
`summary.png`, `case-summary.png`, `sequence.png`, `mobile-cases.png`,
`intelligence-verification.json` and `preservation.json`. Screenshots contain
account/transaction evidence and are not committed. Prior 6D outputs are preserved.
Playwright emits a terminal NO_COLOR/FORCE_COLOR warning; application checks pass.

## Reproduce and remaining limitations

With the local API running on port 8000 and dependencies installed:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
npm test --prefix frontend
npm run check --prefix frontend
npm run build --prefix frontend
npm run test:browser --prefix frontend
```

The wide two-hop request still exceeds the original finding cap. Long groups can
span many days and overlapping witnesses are not independent evidence. The mobile
group list requires scrolling; dense network labels benefit from zoom and a wider
screen. No comprehensive accessibility audit, analyst user study, authentication,
persistent case lifecycle or production load test was performed. Retrospective
availability assumptions, missing training scores, uncalibrated scores and
synthetic-data limitations remain. The templates summarize observations rather
than recommending an investigative conclusion.
