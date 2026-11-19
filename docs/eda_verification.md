# Exploratory analysis verification

Executed locally on 2026-10-14 (Asia/Kolkata), Python 3.12.15, with the existing
PostgreSQL database and locked uv environment. No raw files, production schema,
transaction records, or labels were changed. Analysis explicitly enforced
`REPEATABLE READ READ ONLY`; server settings confirmed `read_only=on` and
`isolation=repeatable read`. Integration tests used disposable `mg_test_*` schemas.

| Verification | Actual result |
| --- | --- |
| Full SQL aggregation, first run | Completed in 162.908 seconds; saved `data/eda/hi-small.json` |
| Initial report rendering | Failed with a local `NameError`; corrected the report variable and regenerated successfully from saved aggregates |
| Final full EDA CLI run | Exit 0; aggregation took 153.085 seconds; saved `data/eda/verified-run.json` and generated the report and all three charts |
| Reproducibility comparison | Both full-run JSON results exactly equal after excluding only generation time and elapsed seconds |
| Dataset coverage | 5,078,345 transactions and 5,078,345 labels; zero rows outside the four proposed splits |
| Pytest with PostgreSQL integration | **47 passed in 1.90 seconds**, no failures or skips |
| Ruff check | Passed |
| Ruff format check | Passed |
| Chart review | All three PNG figures visually inspected; labels/layout readable |
| Git exclusions | Both EDA JSON output paths confirmed ignored |

Commands used for the recorded run (after dependency installation):

```sh
uv run --locked --env-file .env python -m mulegraph.eda
uv run --locked --env-file .env python -m mulegraph.eda \
  --output data/eda/verified-run.json
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Durations above measure database aggregation for these local executions, not
performance benchmarks or total chart-rendering time. No verification remains
blocked. Test coverage includes exact NUMERIC quantiles, source-row duplicate
preservation in aggregates, composite account identities, self-transfer counting,
class/category counts, timestamp ties, every split's half-open boundaries,
missing-label rejection, out-of-range rejection, and unchanged fixture ingestion
reconciliation after analysis. Future feature cutoff invariance is documented as
a requirement; it cannot be tested yet because no predictive features exist.

The subsequent feature design adopted the September 1–6 / 7–8 / 9–10 calendar split,
separate September 11–18 stress evaluation, development-holdout status after EDA,
and the immediate-arrival assumption required by absent availability timestamps.
The cause of the post–September 10 generation/selection shift remains unproven.
Read [the measured report](eda_report.md) for findings and temporal rules.
