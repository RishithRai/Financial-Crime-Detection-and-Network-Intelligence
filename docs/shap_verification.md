# TreeSHAP verification

Executed on October 15, 2026 (Asia/Kolkata), using the frozen
`lightgbm-stable-v1/history_none` bundle and original training-fitted preprocessing.
LightGBM 4.7.0 native TreeSHAP supplies the SHAP contributions; no separate SHAP
package or environment change was needed. No real labels or pattern annotations
were accessed. No estimator was retrained, and no threshold or historical feature
was modified. The unit tests fit disposable synthetic models only.

## Actual explanation checks

| Check | Measured result |
| --- | --- |
| Fixed label-free validation sample | 256 source IDs, selected by seeded SHA-256 ordering |
| Encoded inputs | 84, in the saved preprocessing order |
| TreeSHAP raw baseline | -9.932533138309482 |
| Baseline variation across sample | 0 |
| Maximum raw-margin additivity error | **2.7964 × 10⁻¹⁴**; required ≤1e-8 |
| Saved versus recomputed review scores | **Exact equality on all 256 sample rows** |
| Sigmoid(raw) versus classifier score | Passed absolute tolerance 1e-12 for every explained row |
| Fixed replay | 16 explanations reproduced exactly |
| Case annotation demonstration | 12 explained transactions; 4 explicitly unscored training transactions |
| Case preservation | All original case fields, memberships and scores unchanged |
| Missing-input probes | Training period explicitly unscored; nonexistent source explicitly not found |

A preliminary real-data probe also verified a saved transaction explanation and
the unscored/missing paths before the fixed sample run. An initial constructor
check exposed JSON tuple/list representation differences in the unchanged feature
definition; canonical JSON comparison corrected the check without modifying any
artifact. All final checks completed successfully.

The selected model SHA-256 is
`5d02b0704e164acdd7961eb459bf3cee2270eefd02becd8b4ba5a56dc3689605`.
The sample source-ID order digest is
`7d3ef381af29a3f76e53b7aae554a69b761883ac9756cbb41e2c0aa0ac2388c7`.
The global summary contains no transaction records or labels. Detailed sample
explanations and the annotated case remain in ignored `data/explanations/v1/`.

## Sample feature importance

These are the leading **mean absolute raw-margin contributions** among encoded
features over the fixed 256-row validation sample. They are not probabilities,
percentages, independent evidence weights or causal effects.

| Encoded feature | Mean absolute SHAP | Mean signed SHAP |
| --- | ---: | ---: |
| Sender currency-specific prior outgoing count | 0.605790 | -0.596478 |
| Payment format = ACH indicator | 0.596892 | -0.013489 |
| Sender prior outgoing count | 0.335072 | +0.335072 |
| Sender preceding-hour activity count | 0.316149 | +0.026282 |
| Sender distinct prior counterparties | 0.209138 | +0.023340 |
| Self-transfer indicator | 0.162804 | +0.121990 |
| Receiver currency-specific historical incoming sum | 0.147870 | -0.047771 |
| Sender seconds since preceding activity | 0.146931 | -0.012150 |
| Sender observed history age | 0.099916 | +0.099910 |
| Amount received | 0.091992 | +0.002108 |

After summing encoded columns by source feature per row, payment format's mean
absolute grouped contribution is **0.597601**. This is a display aggregation,
not a newly estimated grouped coalition value. Sender currency-specific count
remains the largest grouped value at **0.605790**.

The model relies strongly on sender activity and payment format in this sample,
consistent with prior validation ablations and coverage concerns. That does not
establish a synthetic generator mechanism, explain every positive label, or make
ACH evidence of wrongdoing. A small mean signed contribution can hide large
opposing contributions across rows; mean absolute magnitude is not a direction
of effect. Correlated history features can share attribution, and individual
feature values cannot be treated as independent causal levers.

## Measured costs

Verified service initialization took **0.841 seconds**. Explaining the 256-row
sample in two bounded batches took **2.590 seconds**, including repeated feature
hash checks, Parquet retrieval, saved-score lookup, preprocessing, TreeSHAP and
consistency checks. The 16-transaction case annotation took **0.860 seconds**.
These are local wall times, not performance guarantees; only 12 of those case
transactions ran SHAP because four had no saved training-period prediction.

Peak traced Python allocation during the sample was **16.555 MiB**. It excludes
native LightGBM/DuckDB allocation and PostgreSQL memory and is not process RSS.
The sample timing excludes service initialization, source-ID selection, replay
and final JSON writes. File verification and scanning can dominate small requests.
No full-dataset SHAP pass or label evaluation was performed.

## Tests and preservation

| Check | Actual result |
| --- | --- |
| Full PostgreSQL-enabled suite | **141 passed in 6.90 seconds**, no failures, skips or warnings |
| Ruff lint and formatting | Passed |
| New tests | 7 unit tests and 1 PostgreSQL case-annotation integration test |
| Frozen original artifacts | All 66 saved source hashes match |
| Frozen scoring implementation | All holdout-freeze hashes match |
| Historical feature file and manifest | Both saved hashes match |
| Holdout predictions | Both saved hashes match |
| Dependency files | Unchanged |

Tests cover native additivity and sigmoid agreement, nonfinite/bad outputs,
saved-score agreement, repeatability, all feature descriptions, grouped sums,
request limits, missing source/input, temporal cutoff boundaries, invalid cutoffs,
feature corruption, altered preprocessing, and training requests that must never
invoke the estimator. Case tests verify unchanged original fields and reject
mismatched scores/transaction attributes. PostgreSQL integration uses disposable
synthetic core transactions and a synthetic model; existing label fixtures remain
synthetic. The representative real-data explanations read immutable local artifacts
and do not need PostgreSQL or labels.

Preservation evidence is in `data/explanations/v1/preservation.json`. Historical
feature SHA-256 remains
`dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`.
The unchanged graph-era lock hash is
`241a4fceecba22d249e93974a5c12be086df3f3a39d19946abf87cc287b3d44f`.
The older full ML lockfile audit still requires its original environment; its
checks were not bypassed or weakened.

## Commands and limitations

From the repository root, after installing dependencies as described in the README:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked python -m mulegraph.explanation_report --output data/explanations/new-run
```

No execution blockers remain. Explanations are relative to the frozen model's
training-path background and feature encoding. They are not causal evidence or
additive probability changes. Review scores remain uncalibrated, source
availability assumptions remain unresolved, and saved-score coverage is partial.
No in-sample scores fill training gaps. The small global summary is validation-
sample-specific; no claim of statistical stability, calibration or generalization
is made. There is no account/case probability explanation or UI.

See [SHAP architecture, semantics and service usage](shap_explanations.md).
