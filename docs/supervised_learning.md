# supervised training and validation

This stage fits Logistic Regression and LightGBM on September 1–6, 2022 and
compares them on September 7–8. There is no test/stress prediction or evaluation
command in this module. Earlier EDA and rules work inspected those development
holdouts; evaluation belongs to the separate frozen holdout stage.

## Inputs and point-in-time contract

The only predictive inputs are the explicitly enumerated fields in `ml.py`:

- Current: amount paid, amount received, payment and receiving currencies,
  payment format, self-transfer, and cross-currency indicators.
- History: each endpoint's total/sent/received counts, 1-hour/24-hour counts,
  unique counterparties, currency-specific lifetime/hour/day counts and sums,
  time since last activity, history age, mean gap, and hour/day frequencies.

The four feature variants are current, current without payment format, current
plus history, and current plus history without payment format. Every variant
contains both currencies. Identifiers, source rows, absolute timestamps, splits,
labels, fingerprints, endpoint identities, last-activity timestamps, names,
pattern annotations, and unavailable account metadata are excluded from models.
Source row and dataset fingerprint are retained only for alignment/provenance
and a label-free ranking tie order.

No new historical features are computed. The historical-v1 contract remains:
composite account identities, strictly earlier transactions only, all
same-timestamp peers excluded, and rolling unlabeled history across splits.
Immediate arrival and availability of both receiving-side and payment-side
attributes are assumptions inherited from historical-feature stage. These are retrospective
scores under that contract, not a verified pre-settlement deployment design.

## Training-only preprocessing

All training rows are used; there is no negative downsampling. Numeric values
are transformed by log1p, then standardized using training means and standard
deviations. Nullable durations use zero imputation plus fixed missingness flags;
zero counts/sums retain their original empty-history meaning. Currency and
payment-format vocabularies are learned only from training rows, sorted, and
one-hot encoded with an explicit unknown bucket. Validation neither changes
vocabularies nor refits scaling. Constant numeric columns use unit scale.

Monetary values are converted to floating point for modeling only. Raw NUMERIC
and Parquet DECIMAL values remain unchanged. This is approximate numerical
representation, not currency conversion. Including currency indicators does not
make different currency amounts economically comparable; linear models have no
explicit currency-by-amount interactions. Short/cold histories remain usable
observations with missingness indicators rather than being discarded.

## Fixed experiment plan

Ten experiments are declared before either label export:

1. Four feature variants × two model families (eight fits).
2. On the full history variant only, one alternative setting per family.

Logistic Regression uses balanced class weights, L-BFGS, C=1 (alternative 0.1),
200 maximum iterations, tolerance 1e-4, and seed 42. LightGBM uses 120 trees,
learning rate 0.05, 15 leaves (alternative 31), maximum 63 bins, minimum 200
observations per leaf, L2 penalty 1, and training negative/positive class ratio
as positive weight. There is no early stopping or additional parameter search.
Full estimator parameters, coefficients or gain importance, fit warnings, and
iteration counts where available are saved per experiment.

Two CPU threads are used. Arrow batches feed disk-backed float32 matrices, with
only one variant's matrices retained at a time. DuckDB is restricted to one
thread and 256 MB, spilling into disposable scratch space. L-BFGS and LightGBM
still allocate their own working arrays: memory maps are not a hard RAM limit.
Matrices and temporary labels are removed on success or failure.

The recommendation is the highest validation AP, with experiment order breaking
exact ties. This is a development selection estimate, not an unbiased final
performance estimate. Class weighting changes score calibration; these scores
must not be described as calibrated probabilities or proof of laundering.

## Evaluation and operating policy

AP groups score ties using sklearn's non-interpolated average precision. ROC-AUC
uses the standard tied-rank convention. Both are undefined when their requisite
classes are absent, reported as null rather than fabricated values. Prevalence
is the constant-score AP baseline.

Precision@K and Recall@K use K=100, 1,000, and 10,000 (capped to population).
A comparable ranking budget selects floor(1% × validation rows) observations.
All methods use descending score, then the same SHA-256 identity tie order as
the frozen rules baseline. Arbitrary ordering within large ACH/rules ties is
explicitly part of these budget metrics; AP itself never uses this tie order.

Separately, each model receives a numeric threshold that includes the largest
complete score tiers within the validation 1% alert cap. Tied tiers crossing the
cap are excluded. Thus threshold alerts may be fewer than the exact ranking
budget. The threshold is saved with the model; it must not be adjusted using
future test/stress outcomes. A validation alert cap is not a guarantee about
future alert volume. Frozen rules retain their original score≥2 policy; only
their existing validation predictions are reused for comparable ranking metrics.
ACH-only and prevalence are sanity checks, not causal explanations.

## Artifacts and reproducibility

```sh
# Install dependencies as described in the README first.
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked --env-file .env python -m mulegraph.ml_training \
  --features-dir "$FEATURE_DIR"
uv run --locked python -m mulegraph.ml_report
```

Outputs live under ignored `data/ml/supervised-v1/`: a predeclared `plan.json`,
aggregate `results.json`, and one directory per experiment containing
`model.joblib` (estimator, preprocessing, threshold), `metadata.json`, and
label-free `validation.parquet` (source row and score). Plan provenance supplies
dataset identity and validation period. Scores are not joined to labels in
persisted prediction files. Temporary training/validation labels are obtained
from read-only PostgreSQL snapshots with hardcoded approved date bounds.

The feature checksum is verified before and after the run. Model and prediction
hashes, implementation hashes, dependency versions, and label-export hashes and
times are recorded. Completed versions cannot be silently overwritten; an
explicit new `--output` directory is required for a deliberate reproduction.
Reproducing the same plan is distinct from expanding the parameter search.
Only load trusted local joblib files: their format can execute Python code.
`load_artifact` checks file integrity and feature-name alignment before use.
Small seeded repeated fits and real model reloads test reproducibility; a full
second ten-model training run is not implied by those checks.

See [measured results](ml_report.md) and [execution verification](ml_verification.md).

A separate artifact audit does not query PostgreSQL or load labels:

```sh
uv run --locked python -m mulegraph.ml_verify --features-dir "$FEATURE_DIR"
```

It checks every saved validation score against a reloaded model and train-fitted
preprocessor, source-row coverage, checksums, and threshold alert counts. Use
`ml_inference.score_batch` for trusted bundle inference. It uses the fixed two
thread setting and float64 comparisons against stored thresholds; casting a
threshold back to float32 could accidentally include an excluded score tie.
Exact reproducibility checks use the same 32,768-row prediction batches;
different BLAS batch shapes can introduce tiny floating-point differences.
