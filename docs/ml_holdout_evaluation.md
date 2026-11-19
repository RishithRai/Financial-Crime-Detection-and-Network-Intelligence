# frozen supervised development-holdout evaluation

The selected model is `lightgbm-stable-v1/history_none`. Comparators are
`supervised-v1/history_lr_1.0`, frozen `rules-v1`, ACH-only, and constant-score
prevalence. This choice is made before holdout labels; the evaluation code has
no training, selection, early stopping, or threshold-search path.

Test is [2022-09-09, 2022-09-11); stress is [2022-09-11, 2022-09-19).
Report them separately. These are **development holdouts**, not untouched data:
earlier EDA and rules evaluation inspected them, and model development reused
validation. Supervised models have not previously been evaluated on these periods.

## Freeze and label-access order

`--phase freeze` verifies the historical-v1 file and definition fingerprint,
training/stabilization implementation signatures, dependency lock, original
artifact checksums, estimator parameters, feature-name alignment, and saved
thresholds. Both model preprocessors must exactly agree on training statistics,
vocabularies, population and feature names. No preprocessing is fitted again.
Every saved validation score for both models is reproduced using the unchanged
preprocessor and estimator, without retrieving labels.

The exclusive-create freeze JSON records the selected model, comparison model,
thresholds, source artifact hashes, dataset identity, feature hash, implementation
hashes, dependencies, boundaries, and fixed reporting policy. It is checked again
before each holdout label export. Both splits are scored and saved before either
label export. Frozen rules are recomputed from their saved training references;
no reference distribution is fitted. Labels are fetched in read-only snapshots,
aligned by unique source row, and deleted after separate aggregate evaluation.

Outputs publish atomically under ignored `data/ml/supervised-holdout-v1/`.
Completed evaluations refuse reruns; a durable attempt record also prevents silent
reopening after a failure. Hashes and timestamps demonstrate reproducibility,
not adversarial tamper-proof auditing. Original artifacts are never overwritten.

## Metrics and policies

AP uses grouped scores with sklearn's non-interpolated convention. ROC-AUC uses
tied ranks and is undefined with only one class. AP is undefined without positives;
with all positives it is one. Nulls are retained in reports. The constant score's
AP equals each split's prevalence. Report AP/prevalence alongside AP; that lift
provides context but is not a complete prevalence adjustment or proof that two
populations have equal difficulty. Never pool test and stress.

Precision@100 and Precision@1,000 cap K at the split population. The 1% ranking
budget is floor(N/100), which can be zero for very small populations. Ranking is
descending score followed by the same label-free SHA-256 identity tie order as
previous stages. Ties can be split at K; no tie-breaking uses labels. Report
effective K and the corresponding true-positive count, precision and recall.

Confusion counts are explicitly TN, FP, FN, TP. Alert decisions apply the saved
numeric thresholds with ≥ in float64, even if alert rate exceeds 1%. LightGBM
uses `0.011489041059356882`, LR `0.9535042643547059`, and rules `2`.
The inherited ACH sanity policy alerts score≥1. The inherited constant-score
policy is score 0 with threshold 1 (no alerts); its ranking is arbitrary within
a complete tie. These sanity policies were not selected against holdout labels.
No holdout-specific operating threshold is computed.

## Descriptive investigation

Predeclared label-free summaries cover payment format, payment and receiving
currency distributions, sender/receiver cold history, median sender total and
currency-specific activity, inactivity, history age, and payment-amount median
and p99 **within each currency**. Training and validation summaries provide
context; neither model is refitted. Fixed labeled breakdowns are day and payment
format, reporting population, positives and frozen-threshold outcomes for the
two supervised models. They are descriptive, not subgroup-specific thresholds.

Scores remain uncalibrated review priorities. Synthetic patterns, left-censored
history, immediate-arrival assumptions, availability of receiving-side fields,
and a small shifted stress population constrain interpretation. A suspicious
performance pattern is reported rather than prompting another model search.

## Commands

Install dependencies as described in the README:

```sh
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked python -m mulegraph.ml_holdout --phase freeze --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env python -m mulegraph.ml_holdout \
  --phase evaluate --features-dir "$FEATURE_DIR"
uv run --locked python -m mulegraph.ml_holdout_report --verify --features-dir "$FEATURE_DIR"
```

Report regeneration and the independent artifact audit do not retrieve labels.
See [versioned measured results](ml_holdout_report_v1.md) and
[verification](ml_holdout_verification.md).
