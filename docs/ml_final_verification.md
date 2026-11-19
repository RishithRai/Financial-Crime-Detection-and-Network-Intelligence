# Supervised model final verification

Final verification on 2026-10-14 preserved the selected `history_lr_1.0` model,
all ten model bundles, operating thresholds, and frozen definitions. No classifier
was retrained. No real test/stress labels were accessed or evaluated.

## Execution and integrity

- Docker Desktop started; the existing PostgreSQL Compose container is healthy,
  bound to `127.0.0.1:55432`. Its volume was preserved.
- Complete PostgreSQL-enabled suite: **84 passed in 5.95 seconds**, no skips,
  failures, or warnings. This includes synthetic disposable `mg_test_*` schemas;
  earlier-stage holdout tests use synthetic fixtures, not real holdout labels.
- `uv run --locked ruff check .` and `ruff format --check .` passed.
- All **9,655,240** persisted validation scores exactly reproduced on reload.
  Model/prediction hashes, metadata, source coverage, and alert counts passed.
- All four preprocessors were independently recomputed using only September 1–6
  feature rows. Means, scales, vocabularies, feature names, and training counts
  exactly match every corresponding saved bundle. This check fitted temporary
  preprocessing objects only; nothing was saved over the original bundles.
- The historical feature file checksum and feature implementation/dependency
  fingerprint match the manifest. ML implementation hashes also match the plan.
- Final diagnostics confirmed original artifact bytes unchanged. The prior audit
  was preserved as `verification_before_final.json`. Aggregate diagnostic output
  and its script are retained under ignored `data/ml/supervised-v1/`.

The database suite was run with:

```sh
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
```

## Selected Logistic Regression contributions

Contributions below are coefficient × encoded feature value in the linear score,
before the sigmoid. Numeric inputs are standardized log1p values, so a negative
coefficient can contribute positively when a value is below the training mean.
They are additive model explanations, not causal effects or calibrated risk.
The intercept is -3.637734; float64 reconstruction differs from
the model decision function by at most 8.4e-06,
consistent with its float32 arithmetic. All validation rows were streamed.

| Feature | Coefficient | Mean contribution, all validation | Mean contribution, selected alerts |
| --- | ---: | ---: | ---: |
| payment_format=ACH | +4.6683 | +0.5653 | +4.6161 |
| sender_currency_history_count | -7.3727 | -4.7419 | +4.4708 |
| sender_seconds_since_last | +1.9946 | +0.5777 | +3.2105 |
| sender_history_count | +3.7331 | +2.5247 | -1.4283 |
| sender_sent_count | +2.6258 | +1.6991 | -1.4349 |
| sender_currency_count_24h | +2.3274 | +0.5235 | -1.7357 |
| sender_count_24h | -1.2754 | -0.3209 | +0.9401 |
| sender_unique_counterparties | +1.5964 | +0.5040 | -0.6360 |
| payment_format=Reinvestment | -3.7049 | +0.0000 | +0.0000 |
| payment_format=Wire | -3.0632 | -0.1164 | +0.0000 |
| sender_seconds_since_last__missing | +2.2542 | +0.0021 | +0.0014 |
| sender_history_age_seconds__missing | +2.2542 | +0.0021 | +0.0014 |

ACH, low direction/currency-specific sender history, and longer sender inactivity
provide the strongest average positive contributions among selected alerts.
Sender currency/day count, sent count, and overall history count provide the
strongest average negative contributions there. Over all validation rows,
sender currency history has the largest mean absolute contribution (5.1046).
Reinvestment has a large negative coefficient but is absent in validation, so
it contributes zero there. Coefficient size alone would obscure this distinction.

## Leakage and synthetic-shortcut review

- **No direct target leakage found:** predictive SQL reads core fields only;
  labels and label-bearing hashes, account/entity metadata, IDs, absolute time,
  and split are excluded by the model allowlist. Source-row identity is used
  for alignment and deterministic ranking ties only. Labels enter estimator
  fitting and separate evaluation, never the predictor matrix.
- **Temporal checks:** historical state emits every timestamp peer before
  updates, uses strictly earlier events, and the future/peer invariance tests
  passed. The feature fingerprint confirms the reviewed implementation matches
  the saved version. Availability timestamps are absent from the source:
  immediate arrival and availability of receiving-side fields remain assumptions.
  A pre-settlement application could violate those assumptions.
- **Payment-format shortcut concern:** ACH appears in approximately 98.88% of
  selected alerts versus 12.11% of validation transactions (derived from its
  one-hot contribution). Existing history-LR AP falls from 0.26173 to 0.18537
  without payment format. This is substantial reliance on a possible synthetic
  generator association, not evidence of wrongdoing by payment method.
- **History shortcuts:** opposing sender total/sent/currency-count weights and
  inactivity signals may encode synthetic activity patterns or dataset coverage.
  This is a hypothesis, not a demonstrated generator mechanism. Identical
  history-age and last-activity missingness flags each carry +2.2542, duplicating
  a cold-history signal; only six selected alerts have these sender missing flags.
  Left-censored history makes such signals sensitive to the observation start.
- **Redundant predictors:** total/sent/received counts are related; hourly count
  and hourly frequency are identical. Correlation spreads coefficient weight
  across inputs, so individual coefficients are not independent evidence.
- No new label-based subgroup search, alternative selection, raw-margin ranking
  evaluation, or threshold adjustment was performed. These checks cannot prove
  generalization or rule out every synthetic shortcut.

## LightGBM saturation diagnosis

All five saved models were inspected without fitting. The table reports full
validation raw-margin extrema and exact sigmoid endpoint counts. Each model
contains 120 trees and uses positive-class weight **1283.1585**.

| Model | Raw minimum | Raw maximum | Scores = 0 | Scores = 1 | Largest absolute leaf value |
| --- | ---: | ---: | ---: | ---: | ---: |
| current_lightgbm_15 | -113,692.4 | 41,125.3 | 68,171 | 90,201 | 60,548.0 |
| current_no_format_lightgbm_15 | -335,342.8 | 116,452.6 | 504,629 | 371,120 | 67,947.7 |
| history_lightgbm_15 | -54,229.9 | 93,310.6 | 93,597 | 88,044 | 73,212.8 |
| history_lightgbm_31 | -36,189.8 | 86,638.3 | 105,226 | 88,489 | 84,244.4 |
| history_no_format_lightgbm_15 | -65,847.2 | 60,280.4 | 288,005 | 116,542 | 33,977.8 |

Saturation is present in the reloaded models' **float64** probabilities; it is
not caused by Parquet serialization or converting saved scores to float32.
Applying a stable sigmoid to raw margins reproduces probabilities within
1.12e-16. The margins themselves are extreme, collapsing ranking resolution.

The saved first trees already have maximum absolute leaf values around 50–57;
second-tree values reach 9,511–22,856. Predictions using the first 1, 2, 5, 10,
and 120 existing trees on the first 32,768 training rows show large negative
margins by tree two and large oscillating extremes thereafter. This is a
deterministic diagnostic sample, not a new training evaluation or population
estimate. It establishes that the instability starts early in the saved fits.

The combination of severe imbalance, positive weighting, and very large early
tree updates is consistent with unstable weighted boosting; this is a likely
mechanism, not a causal result from controlled retraining. All top-score ties
exceed the 9,655-alert budget. The existing whole-tier threshold therefore
correctly emits zero alerts; exact-budget ranking selects within that large tie.

## Decisions and frozen validation outcome

The selected model remains **history_lr_1.0**: AP **0.26172877**, ROC-AUC
**0.97426269**, with **607** true alerts among **9,655** alerts: precision
**6.2869%**, recall **58.5907%**. These are the original validation metrics.

Before any later development, decide whether to predeclare a separate LightGBM
stabilization experiment (for example, bounded leaf updates, smaller steps, or
weighting changes) and whether payment-format dependence and attribute-availability
assumptions are acceptable. Raw-margin ranking would change the scoring policy
and also needs a separately declared experiment. None was implemented here.
These checks do not establish operational readiness or replace frozen holdout evaluation.

Existing repository-local Git identity was already configured; no identity
values were changed. The initial local commit includes source, tests, locked
dependencies, configuration templates, and permitted aggregate reports/figures.
Datasets, `.env`, virtual environments, temporary diagnostics, models, and
row-level predictions remain ignored. Nothing was pushed to a remote.

See [validation results](ml_report.md) and [recovery history](ml_verification.md).
