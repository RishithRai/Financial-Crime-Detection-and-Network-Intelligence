# investigation dashboard

Run from the repository root after installing dependencies as described in the README:

```sh
uv sync --locked
uv run --locked --env-file .env streamlit run streamlit_app.py
```

Open http://127.0.0.1:8501. PostgreSQL is required for investigations. Immutable
features, predictions, model and reports from previous stages must be present.
This is a single-user local application without authentication or persistent case
management. Do not expose its port publicly. Credentials are not rendered.

## Workflow

- **Overview** displays saved development-holdout aggregates. Test and stress
  remain separate. Evaluation statistics are not investigator evidence.
- **Transaction Queue** filters saved validation, test or stress scores by source
  ID, exact composite bank/account, payment format and frozen threshold. Sort by
  score, time or source ID; change the page in the form to paginate. Select a
  transfer for details, SHAP or preceding sender history.
- **Network Explorer** accepts a composite account or selected focal transfer.
  Set inclusive start, exclusive cutoff, hops and budgets. Selecting an account
  focuses the directed relationship plot and transfer inspector. Parallel transfers
  share an arrow; self-transfers remain in the table. Static relationships are
  not chronological flows. Pattern selectors show original evidence and ordered
  transfer sequences. Result scope stays visible when form inputs are edited.
- **Investigation Cases** shares the unchanged investigation result. Select a case,
  inspect account-specific coverage/history and readable reason codes, then explain
  supporting transactions. Groups are not independent incidents or account labels.

SHAP shows ten largest absolute encoded contributions, with all values available
below. Contributions affect raw margin relative to the training-path baseline,
not probability addends or causal effects. The existing service verifies additivity
and saved-score equality. Training transactions explicitly remain unscored. No
in-sample predictions fill gaps. Focal transfers stay separate from case evidence.

## Architecture and bounds

`dashboard_data.py` adapts `FrozenScores`, `graph_session` and `investigate_cases`.
`dashboard.py` renders them using Streamlit and Plotly. SHAP uses the unchanged
`ExplanationService`, including case annotation consistency checks. There is no
label SQL, fitting, new predictive feature or threshold selection in the UI.

Queue SQL uses parameterized filters and allowlisted sorting over label-free
Parquet. Each request verifies used feature/prediction hashes. DuckDB uses two
threads, 256 MiB memory, disabled disk spill and a ten-second query interrupt;
hashing is outside that timeout. At most 100 plus one sentinel rows enter Python
(UI pages contain 25). Pagination stops at 1,001 pages; narrow filters beyond that.
Sorting may scan large files on disk without loading all rows into Python. Exact
money strings retain their currencies and are never converted or pooled.

Investigations use read-only repeatable-read PostgreSQL, five-second per-query
timeouts, at most two hops, 500 accounts and 5,000 transfers (defaults 150/1,000).
Existing candidate/finding/evidence caps remain enforced. Failed requests clear
previous results and return no partial evidence. Empty results do not imply safety.
The graph plot focuses on the selected account's neighborhood; the complete
returned evidence remains in the report. Evidence tables paginate 25 rows; SHAP
explains one transaction per action. No whole-dataset SHAP pass runs.

Session state contains bounded results, without shared global account caches.
Errors suppress internal paths, SQL and credentials. Existing request-scoped case
IDs and point-in-time semantics are unchanged. Event-time replay assumes immediate
attribute availability; saved scores are retrospective and uncalibrated.

## Environment and limitations

Streamlit 1.66.0 and Plotly 6.9.0 were added via uv. All pre-existing package versions
remain unchanged. The frozen SHAP dependency checks pass. The lockfile changed;
earlier exact-lock ML audits still require their original environment and were
not weakened. Previous dependency files are retained in ignored
`data/dashboard/environment-before-6b/`.

The browser surface was unavailable, preventing screenshot review. Streamlit
AppTest verifies UI logic and Plotly construction, not pixel-level usability or
accessibility. There is no authentication, export/annotation workflow, persistent
case lifecycle, cross-request reconciliation or multi-user management. Synthetic
shortcuts, partial score coverage and generalization concerns remain unresolved.

API references: [Streamlit Plotly charts](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart)
and [Plotly network graphs](https://plotly.com/python/network-graphs/).
See [verification](dashboard_verification.md), [case architecture](case_intelligence.md)
and [SHAP semantics](shap_explanations.md).

## Network investigation interface

The current entry point is **Home**, with prioritized transaction cards and a
one-click investigation action. **Model Evaluation** now contains the former
Overview. Queue pages contain ten cards. Automatic investigations start with one
hop and the preceding 24 hours; advanced manual scope can expand within the existing
bounds. See [redesign workflow and verification](dashboard_redesign.md).
