# frozen transaction SHAP explanations

`mulegraph.explanations` explains the selected frozen
`lightgbm-stable-v1/history_none` model with its original training-fitted
preprocessor. It uses **LightGBM's native TreeSHAP implementation** through
`Booster.predict(pred_contrib=True)`. No separate `shap` package or dependency
update is needed. This is SHAP attribution, not split-count/gain importance or
an approximation based on multiplying feature values by coefficients.

LightGBM documents its [native SHAP contribution output](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMModel.html),
including the final expected-value column. The SHAP documentation also demonstrates
[this native LightGBM interface](https://shap.readthedocs.io/en/stable/example_notebooks/api_examples/plots/decision_plot.html).
It is tree-path-dependent TreeSHAP: the background is represented by training
path/leaf counts retained in the model. No new background sample, training labels,
or holdout labels are fetched. Feature-dependence assumptions matter; this is not
an interventional or causal explanation.

## Output space and verification

For each explained transaction:

```text
raw margin = TreeSHAP baseline + sum(all 84 encoded feature contributions)
review score = sigmoid(raw margin)
```

The raw margin is the binary model's log-odds-scale output. The review score is
on [0,1] but is **not validated as a calibrated laundering probability**. Positive
contributions raise the margin relative to the TreeSHAP baseline; negative ones
lower it. Contributions are not additive probability points, and their signs do
not imply that changing a feature would cause the score to move that way.

The service checks finite dimensions/values, raw-margin additivity with absolute
tolerance `1e-8`, sigmoid-to-model score agreement with tolerance `1e-12`, and
recomputed-to-saved prediction agreement with tolerance `1e-12`. It fails rather
than publish an inconsistent explanation. The native baseline is not the empirical
label prevalence, and sigmoid(mean raw margin) need not equal mean review score.

## Frozen inputs and integrity

Initialization verifies the committed holdout freeze, selected model/metadata
hashes, estimator parameters, threshold, feature names/dimensions, relevant frozen
scoring dependency versions and implementation hashes. The trusted local bundle
is deserialized only after artifact checksum checks. Historical feature-file and
manifest hashes plus the feature definition/dependencies are verified. Feature
hashes are rechecked for every request, avoiding a stale feature-cache assumption.
JSON normalization handles tuple/list representation when comparing persisted
feature definitions; it does not change the definition or frozen fingerprint.

The preprocessor applies the original train-only log1p/standardization, zero
imputation with explicit missing flags, and categorical vocabulary. Nothing is
refitted. Only allowlisted feature columns and required source/core metadata are
selected from the historical Parquet file. Dataset identity and unique source-row
alignment are checked; IDs, times, split and endpoints are not predictors.

Saved predictions come from the existing label-free validation/test/stress files,
whose hashes and alignment are checked by `FrozenScores`. The service reproduces
existing scores to validate explanations; it does not publish new scores for
unscored populations or change thresholds, models, features or prior results.
No labels or pattern annotations enter construction, sampling or interpretation.

The dependency lock remains unchanged from graph-foundation stage. The original full ML
audit still intentionally requires its older lock; no guard or frozen manifest
was edited. This service separately checks the scoring dependencies and frozen
inputs it uses, and does not claim to rerun the old environment audit.

## Understandable feature contributions

Every explanation retains all 84 encoded contributions, their exact encoded
input values, source-feature names, readable descriptions and observed original
values. Amounts retain their currencies; historical sender currency fields refer
to outgoing payment-currency activity, while receiver fields refer to incoming
receiving-currency activity. Frequency units are transactions/hour; gap and history
age units are seconds. History age is observed history, not account age.

Categorical descriptions identify the particular one-hot indicator and the observed
category. An absent category indicator can still have a nonzero SHAP attribution;
its contribution must not be read as evidence that the transaction used that
category. Missingness indicators are explicitly named, and missing original values
remain null. Standardized numeric values are not presented as original monetary
units. A narrative says the encoded feature contributes positively/negatively to
the raw margin, not that a behavior is criminal or causally increases risk.

The response includes five largest positive and five largest negative contributions
for quick reading. Those short lists need not reconstruct the output: the complete
contribution list and baseline do. For readability, all one-hot columns of a source
category and each numeric feature's missing flag are also summed into source-feature
groups. These are sums of encoded attributions, not newly computed grouped SHAP
coalitions; cancellation within a group is possible.

Correlated/redundant activity counts and one-hot encodings complicate individual
attribution. Importance describes this model's use of inputs under its explanation
assumptions, not independent evidence, statistical significance or causal effects.

## Bounded service and missing predictions

`ExplanationService.explain(source_ids, cutoff=None)` accepts **1–128 distinct
positive source IDs** per call. Duplicate IDs, invalid bounds and timezone-aware
cutoffs are rejected. With a cutoff, every found transaction must be strictly
before it; a cutoff peer or future row fails the request. Without a cutoff, the
service explains the transaction's saved historical feature row at its own event
time under the existing immediate-availability assumption.

The result distinguishes:

- `EXPLAINED`: saved prediction exists and all consistency checks pass.
- `UNSCORED_TRAINING_PERIOD`: no model inference or SHAP calculation is performed.
- `SAVED_SCORE_UNAVAILABLE` / `OUTSIDE_SAVED_SCORE_PERIODS`: no substitute score.
- `SOURCE_NOT_FOUND`: no historical feature row for the requested ID.

Missing or corrupt predictions inside an expected saved file are errors, as are
missing required input columns or corrupted feature artifacts. Empty scored batches
never invoke the estimator. Requests return in source-ID order for deterministic
output. Known unscored statuses do not imply low risk.

Two CPU threads and a 128 MiB DuckDB memory limit are used. The selected feature
response is capped at 129 rows to detect duplicate identities, while the SHAP
matrix has at most 128 × 85 entries including the baseline. Hashing and Parquet
filtering may scan files even for small requests; the service does not load the
whole feature dataset into Python or explain millions of transactions. These
settings do not constitute an end-to-end timeout or total process-memory limit.

```python
from mulegraph.explanations import ExplanationService

service = ExplanationService()
# Illustrative source IDs; the service reports missing/unscored states explicitly.
explanations = service.explain([1, 2])
```

## Case integration

`annotate_case_report(report, source_ids)` explains an explicitly chosen bounded
subset of the report's historical transaction registry. It checks dataset identity,
cutoff, timestamps, core transaction attributes (including exact amounts/currencies)
and saved scores against the case context. Focal transactions outside the historical
registry are rejected. An already annotated report is not silently overwritten.

The method returns a deep copy with one new `transaction_explanations` field.
Cases, membership, original findings, account summaries, ranking and risk scores
are preserved exactly. Unrequested transactions and explicit missing statuses
remain visible. The service does not automatically explain every transaction in
large cases, add SHAP contributions to case risk, or invent account-level SHAP.
Detailed explanations and annotated cases belong under ignored `data/`.

## Small global summary

The reproducible report selects **256 validation source IDs** with the lowest
SHA-256 of `mulegraph-shap-v1:<source_row>`, using source ID only. There is no label,
score or successful-pattern selection. Two 128-row batches are explained, and
16 fixed rows are replayed for exact explanation equality. Global importance is
mean absolute raw SHAP over this sample; mean signed attribution is reported
separately. Grouped importance is mean absolute value of the per-row grouped sum.

This is a small validation-sample summary, not a population-wide finding or a
comparison of holdout performance. It can miss rare patterns and depends on the
sample, feature representation and baseline. The case demonstration separately
selects four unscored and twelve scored historical transactions by source order
from an existing case report, without examining labels or score magnitude.

```sh
uv run --locked python -m mulegraph.explanation_report --output data/explanations/new-run
```

The command requires a new output directory and preserves prior artifacts.
See [measured explanations, importance and verification](shap_verification.md).
