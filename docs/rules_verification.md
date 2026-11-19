# Rules baseline verification

Executed on 2026-10-14 with Python 3.12.15 and the existing locked environment.
The real calibration and holdout evaluation commands both completed successfully.
No historical features or source records were modified, and no ML model was trained.

| Check | Actual result |
| --- | --- |
| Training reference population | 3,248,921 historical-v1 rows; training labels not fetched |
| Calibration | Exit 0; 18.681 seconds; validation labels only |
| Finalized operating policy | Score ≥2, selected using validation F2 under a 1% alert-rate cap |
| Frozen test/stress evaluation | Exit 0; 15.011 seconds; no parameter changes |
| Persisted predictions | 1,829,424 rows across validation, primary test, and stress |
| Per-split source uniqueness | Passed: 965,524 validation; 862,792 test; 1,108 stress |
| Stored score/trigger/reason/alert consistency | All 1,829,424 rows checked; zero invalid predictions |
| Prediction and rule-file SHA-256 hashes | Matched saved calibration/evaluation hashes |
| Historical feature checksum | Unchanged: `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89` |
| Frozen implementation/split/dependency fingerprint | Matches the executed implementation |
| Row-level labels in prediction files | None; verified all three Parquet schemas |
| Temporary evaluation-label exports | Removed after evaluation |
| Combined prediction file size | 3,634,988 bytes |
| Complete Pytest suite with PostgreSQL integration | **70 passed in 3.28 seconds**, no failures, warnings, or skips |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Git exclusions | Rule artifacts and prediction files under `data/rules/` confirmed ignored |

The operating alert-rate cap applies to validation selection. The unchanged
threshold produced a 1.1343% test alert rate and a 1.8953% stress alert rate;
neither was corrected using holdout observations. Weak performance is reported
as measured, rather than prompting another rule/threshold search.

## Finalization and label-access evidence

Rules were finalized at `2026-10-14T05:29:09.231358+00:00`, with SHA-256
`fce28168d66d3a47bea0b2d63a681d4e97b4b333c02f75b34becef5f724f8b28`.
The holdout stage verified that digest and the implementation fingerprint before
opening test or stress labels. Both holdout prediction files carry the same hash.

| Label export | Export completed (UTC) |
| --- | --- |
| Validation | 2026-10-14T05:29:03.384756+00:00 |
| Primary test | 2026-10-14T05:31:07.256408+00:00 |
| Stress | 2026-10-14T05:31:15.551708+00:00 |

No rules-baseline stage test/stress labels were fetched during calibration. Prior EDA
already inspected aggregate holdout labels, so the reports retain the
**development-holdout** qualification. The saved access hashes/timestamps are
reproducibility evidence, not an adversarial audit system.

## Commands executed

After installing dependencies as described in the README:

```sh
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked --env-file .env python -m mulegraph.rules_baseline \
  --phase calibrate --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env python -m mulegraph.rules_baseline \
  --phase evaluate --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m mulegraph.rules_report
```

Completed calibration/evaluation directories are protected against reruns that
would refit the policy or reopen holdouts. Regenerating the aggregate report is
safe and does not access PostgreSQL labels. Execution durations above are local
stage timings, not performance benchmarks; process startup is excluded.

## Test coverage and limitations

New tests cover exact monetary and frequency boundaries, cold/short history,
unseen or unsupported currency, direction changes, deterministic scoring,
ignored label/identity/future metadata, SQL/Python rule equivalence, and unchanged
training references when validation/test distributions are modified. Hand-worked
metric tests cover grouped-score AP, constant prevalence, Precision@K/Recall@K,
capped K, no-positive/no-alert cases, and budgeted F2 selection.

The staged PostgreSQL integration test uses synthetic disposable schemas. It
checks that validation is the only label access during calibration, holdouts
require finalized rules, repeated evaluation/refitting is rejected, prediction
schemas have no labels, and feature checksums remain unchanged. Existing
historical future-event and same-timestamp-peer invariance tests also passed.

A supplementary persisted-output audit rehashed all artifacts and checked every
saved score against its weighted triggers, every reason list against its Boolean
triggers, and every alert decision against the finalized threshold. This audit
read existing prediction files; it did not rerun holdout label evaluation. The
aggregate audit is saved in ignored `data/rules/rules-v1/verification.json`.

There were no failed full-data runs or skipped final checks. An early isolated
unit run emitted an Arrow API deprecation warning; the test was updated to the
supported API before the final suite. A report-renderer line-length lint issue
was corrected; final Ruff checks passed without changing frozen scoring code.

There are no execution blockers. The primary limitation is scientific and
operational: the main score barely exceeds prevalence AP and misses most positive
labels. Review the illustrative alert budget, F2 objective, heuristic weights,
input-availability assumptions, and future untouched evaluation data before
operational use. Suspicious alerts are review suggestions, not proof of wrongdoing.

See [the measured report](rules_report.md), [implementation contract](rules_baseline.md),
and [frozen aggregate definition](rules_definition_v1.json).
