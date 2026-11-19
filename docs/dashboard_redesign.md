# investigator experience

Start the local application from the repository root:

```sh
uv run --locked --env-file .env streamlit run streamlit_app.py
```

Open http://127.0.0.1:8501. Home now displays the five highest-scoring saved
primary-test transactions above the unchanged validation-selected threshold.
These are historical review priorities, not live alerts or laundering probabilities.
Use **Investigate** on any card: the app carries both composite account identities,
source reference, timestamp, amounts, currencies and frozen score into the workspace.
It immediately queries the sender's preceding 24 hours, with one hop, 150 accounts
and 1,000 transfers maximum. The lower bound never precedes September 1, 2022.
The focal transfer and its timestamp peers are excluded from historical evidence.

The network view offers directed local relationships, account selection through
the selector or graph nodes, individual transfer evidence, chronological pattern
witnesses and a prominent **Review grouped cases** action. Focal details and SHAP
are available separately from historical evidence. No-pattern results explicitly
mean no witnesses within this scope, not low risk. Advanced settings allow a
broader window, up to two hops, and the existing capped resource budgets. There
is no automatic retry with changed scope after resource failures.

Transaction Queue shows ten readable cards per page. Each has an exact paid amount
and currency, composite endpoints, timestamp, score and Investigate action. Filters
and sorting remain bounded and parameterized. The selected transaction and completed
investigation survive page changes; rerunning navigation does not requery the graph.
Selecting another transaction clears prior reports and explanations before querying.
Home's five rows and the latest queue page are session-local snapshots; Home offers
an explicit refresh. Frozen-file checks still run when requests reach the adapter.

Cases display score coverage and account-specific activity as readable metrics,
with original reason codes translated by replacing underscores. Exact underlying
case IDs, evidence, memberships and scores remain unchanged. Evidence tables show
source, time, endpoints, exact paid/received amounts, saved score and missing-score
status. Supporting technical evidence remains available in an expander. Training
scores remain missing; no substitute predictions are produced.

Model evaluation has a separate navigation destination. The navy theme uses native
Streamlit configuration for spacing, borders and rounded controls; the previous
private CSS selectors were removed. No dependencies or backend contracts changed.

## Verification

The automated PostgreSQL interaction test starts on Home, clicks Investigate,
verifies a single bounded query, checks focal/peer exclusion, then navigates among
Home, queue, network and cases while asserting unchanged context and no extra query.
Unit tests cover source input validation, queue filters/pagination, rejected limits,
corruption, navigation, sanitized failures, stale-result removal and plot direction.

Real-data AppTest checks covered:

- First prioritized saved transaction: one click opened 22 historical transfers
  in 0.346 seconds, with zero pattern findings/cases in that bounded window.
- Its focal SHAP action passed saved-score and additivity checks.
- Navigation across all five sections preserved transaction and report context.
- The earlier fixed case example, explicitly expanded through Advanced settings
  to its original window and two hops, reproduced the prior 473-transfer,
  16-case report exactly. Its case explanation action also passed.
- All 66 frozen source artifact hashes, frozen implementation, historical feature
  file/manifest and used prediction hashes matched. Dependencies are unchanged.

These are small local checks, not production performance claims. No real labels,
patterns or evaluation runs were used to select examples. Local verification
scripts and aggregate evidence remain under ignored `data/dashboard/6c/`.

Browser screenshots and pixel-level/accessibility review were unavailable for this
verification run. Actual application health
and Streamlit rendering/interaction checks are reported in the completion record.
This remains a local single-user application without authentication, persistent
case statuses, annotations, or cross-request case reconciliation. Retrospective
attribute availability, synthetic-data generalization and score calibration remain
unresolved. Static connectivity and chronological witnesses are not verified money
movement or proof of wrongdoing.

### Final completion record

Verified October 15, 2026 (Asia/Kolkata): **158 PostgreSQL-enabled tests passed in
7.49 seconds**, without failures, skips or warnings. Ruff lint and format checks
passed (90 Python files checked by formatting). The existing application server
on 127.0.0.1:8501 served the changed code and its HTTP health endpoint returned `ok`.
The standalone AppTest harness emitted benign missing ScriptRunContext diagnostics;
there were no application errors. A probe selector initially encountered a button
without a key; the probe was corrected and the full case action then passed.
No frozen backend file, dependency file, threshold, score or case logic changed.
