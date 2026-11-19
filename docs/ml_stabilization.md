# controlled LightGBM stabilization

This follow-up preserves `supervised-v1`, historical-v1, frozen rules, and the
selected Logistic Regression bundle. New outputs use `data/ml/lightgbm-stable-v1/`.
Only September 1–6 training and September 7–8 validation are permitted. The
existing input allowlists, training-only preprocessing, availability assumptions,
and grouped AP / deterministic ranking conventions remain unchanged.

## Predeclared design

Exactly six fits: history and history without payment format, each with positive
weight 1, square root of the training negative/positive ratio, or the full ratio.
The ratio uses training labels only. All rows are retained. There is no early
stopping, seed search, validation-based iteration selection, or grid extension.

Common settings are 240 trees, learning rate 0.03, 15 leaves, depth at most 6,
63 bins, minimum 200 observations and Hessian sum 10 per leaf, L1 penalty 1,
L2 penalty 10, and `max_delta_step=2`. Seed 42 and two CPU threads are fixed.
Compared with the unstable original, this lowers the learning rate, increases
regularization and minimum Hessian, limits depth, and caps leaf updates. Only
weighting and the matched payment-format ablation vary within this experiment.

LightGBM documents the effective leaf-output cap as learning rate multiplied by
`max_delta_step`, here 0.06. We check every post-initial tree against this bound;
the first tree contains the initial intercept. No output scores or raw margins
are clipped after fitting. See the [official parameter documentation](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html#max_delta_step).

Before any training or label export, `--phase plan` writes the fixed plan,
implementation hashes, dependencies, feature checksum, and hashes of every
original supervised artifact. The checked-in JSON is the actual predeclared
plan. It is exclusive-create, not silently overwritten. Training verifies these
signatures before access and again before publishing. A durable attempt record
blocks unreviewed reruns after a failure. A failed attempt requires investigation;
it is not a reason to try another configuration against validation.

## Decision criteria

Among stable new candidates, select highest validation AP, ties in plan order.
Recommend it over frozen `history_lr_1.0` only if AP is strictly higher and recall
at the common floor(1% × rows) ranking budget is at least as high. Otherwise
retain Logistic Regression. ROC-AUC and Precision@K / Recall@K at 100, 1,000,
10,000 are secondary reported measures. This is a development selection rule,
not a statistical significance test. The already-reused validation period makes
any winning estimate optimistic. Final evaluation is documented in the separate
[frozen holdout protocol](ml_holdout_evaluation.md).

Stability requires finite training loss and margins, maximum absolute raw margin
at most 30 on train and validation, no exact zero/one scores, at most 0.1% of
scores within 1e-12 of an endpoint, bounded post-initial leaf outputs, and exact
full-validation reload consistency. Record raw quantiles, score cardinality,
largest tie, top tie, full training loss trace, actual tree count, warnings,
training/prediction time, and process peak RSS. A probability-scale score is not
a calibrated probability, even when numerical saturation is absent.

Numeric operating thresholds use the existing whole-tier 1% validation cap;
ranking metrics use the common deterministic identity-hash tie order. Both alert
counts are reported. The frozen LR prediction file is re-evaluated with the same
validation labels and checked against its saved metrics, including threshold.
Its model and threshold are never changed. No raw-margin ranking is selected.

## Execution and artifacts

Install dependencies as described in the README:

```sh
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked python -m mulegraph.ml_stabilization \
  --phase plan --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env python -m mulegraph.ml_stabilization \
  --phase train --features-dir "$FEATURE_DIR"
uv run --locked python -m mulegraph.ml_stabilization_report \
  --verify --features-dir "$FEATURE_DIR"
```

The original models are loaded only from trusted local paths after checksum
checks. Each new bundle contains its estimator, preprocessing, and threshold;
metadata contains parameters, diagnostics, and integrity hashes. Validation
Parquet contains only source row and score. Temporary label exports and memmapped
matrices are removed. Completed outputs publish together by same-filesystem
rename. Training-only preprocessing is independently rebuilt and must exactly
match the original corresponding LR preprocessor. The full dataset matrices are
disk-backed, but LightGBM still uses RAM for internal allocations.

The training loss trace is a diagnostic evaluated on training rows only; it is
not used to change tree count. Prediction/diagnostic time includes raw-margin
and probability scoring on both train and validation. Preprocessing costs are
reported once per feature variant. Model reload checks add to total runtime.
The separate `--verify` audit opens no database connection or labels; it checks
every saved score against inference from freshly transformed validation batches,
source-row coverage, metadata, thresholds, margins, and original-file hashes.
Omit `--verify` to regenerate the aggregate report from completed results only.

See [measured results](ml_stabilization_report.md).
