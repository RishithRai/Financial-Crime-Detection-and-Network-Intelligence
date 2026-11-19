# execution and leakage verification

Executed October 15, 2026 (Asia/Kolkata). Four pair-history predictors were declared
before implementation in `graph_prediction_plan_v1.json`. Declaration SHA-256:
`3720b9127f36acaa58ff62c8cff1bae91e14a6aafe0fd5490a8a19cf02cd1fa4`.
The saved declaration record is timestamped `2026-10-14T21:37:28.977554+00:00`.
The successful execution freeze is `2026-10-14T21:42:50.908782+00:00`, before its
train/validation exports. No feature, configuration or objective was changed
in response to validation results.

## Feature and temporal checks

- All **5,078,345** graph feature rows have unique source references matching
  historical-v1 timestamps and splits. Coverage was checked with a full outer join,
  not inferred from equal row counts alone.
- Prior counts are nonnegative; recencies are positive when present and null
  exactly when the corresponding count is zero. Self-transfers retain forward
  history and have zero reverse count/null reverse recency.
- Independent hand-worked and randomized Python oracles match the SQL output.
  Future and same-timestamp insertions cannot change earlier outputs. Composite
  identities, reversed direction, duplicate rows, self-transfers, metadata/label
  exclusion and split-boundary roll-forward are tested.
- A PostgreSQL test uses a disposable core-only schema with no labels table,
  including another dataset that must not affect counts. Correlated SQL count/max
  queries independently match the pipeline values.
- The graph artifact remains separate from historical-v1. The original historical
  SHA-256 is unchanged:
  `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`.
- Event-time correctness is tested; actual availability times are absent from
  the source. Immediate availability remains an assumption, not a verified fact.

## Experiment safeguards

Exactly two real fits are permitted: the matched historical control and the
history-plus-graph configuration. The execution plan protects 73 original files
and both graph artifact files, along with implementation/dependency hashes.
The original four-feature declaration remains unchanged. No new test/stress labels
or predictions are requested by the training or verification modules.

The control reproduced all 965,524 original validation scores and all original
metrics exactly before the augmented fit proceeded. Both preprocessors are fitted
on training only; graph values use log1p/scaling and explicit missingness flags.
Validation/test/stress inputs cannot enter the preprocessing fit path. No IDs,
absolute times, labels, pattern annotations or split indicators are predictors.

The synthetic complete pipeline test covers both configurations, exact control
comparison, persistence, label-free replay, report rendering, input corruption,
failed-run cleanup, durable attempt records and completed/failed rerun rejection.
Earlier ML tests also cover model stability, metric ties, preprocessing isolation
and label guards. Synthetic fits do not add real-data experiments.

## Resource failures and recovery

The first full feature-build attempt exceeded the initial 256 MB DuckDB memory
budget. It failed before publication; its scratch directory was cleaned. The
build-only budget was increased to 1 GB, with one thread and external spill; no
feature semantics changed. The completed build took **23.651 seconds** with
**1,056.22 MiB** process peak RSS. This is a local measurement; engine memory
settings do not cap all native/Python/process memory.

The first training-runner attempt failed **before label export or fitting**:
full-data coverage verification had already used DuckDB's temporary directory
before the runner tried to change it. The setup order was corrected, the synthetic
pipeline retested, and the execution plan refrozen before the real fits. Failed
plan/attempt/error evidence is preserved under ignored
`data/graph-prediction/recovery-before-training/`. This was a setup recovery, not
another model configuration or a validation-driven retry.

A later report-rendering test failed because its synthetic label-export mock lacked
completion time/row metadata. The fixture was corrected to match the real export
contract. The final full suite passed. Initial lint line-length issues were fixed.
The reused frozen training helper records LightGBM's `eval_set` deprecation warning
in model metadata; this is not a reason to change frozen training code or refit.
Restricted Arrow cache-discovery diagnostics in isolated test processes did not
prevent verification. Final Pytest emitted no warnings.

## Final checks

- PostgreSQL-enabled Pytest: **184 passed in 12.47 seconds**, no skips, failures
  or warnings.
- Ruff lint and format: passed; formatting checked 112 Python files.
- The UI and investigation services were not changed; no browser rerun is needed
  for this backend-only feature/experiment addition.

The independent, label-free audit completed in **85.176 seconds**:

| Check | Actual result |
| --- | --- |
| Persisted validation scores reproduced | **1,931,048**, exact equality across both models |
| Preprocessing recomputed from training only | Exact means, scales, names, vocabularies and row counts |
| Source coverage, model parameters and threshold alert counts | Matched saved artifacts |
| Independent real PostgreSQL graph sample | **22 source rows × 4 values = 88 matches** |
| Original artifact preservation | All **66** source hashes from the original freeze match |
| Additional experiment snapshot | All **73** original file hashes match |
| Original implementation, historical file/manifest and predictions | Unchanged |
| Original train/validation label-export hashes | Match this run exactly |
| Declaration/implementation freeze before label exports | Passed |
| New prediction files | Two validation files only, source row and score; no labels |
| Temporary labels, matrices and training scratch | Removed |
| Dependencies and investigator/application sources | Unchanged |

The real SQL sample used twelve fixed source positions, the first five rows with
reverse history and the first five self-transfers with history. Selection used
no labels. Queries ran in a read-only repeatable-read core snapshot after checking
the dataset fingerprint. Full feature coverage was checked independently of this
sample; the 88 comparisons are not a claim of independently recomputing all
20 million feature values with PostgreSQL.

Saved aggregate evidence is under ignored `data/graph-prediction/`:
`verification.json`, `preservation.json` and `access_audit.json`. The successful
attempt record remains next to the versioned model output to prevent refitting.
The augmented fit produced 90 encoded inputs, no exact probability endpoints and
bounded leaf updates. Its saved whole-tier validation threshold emits 9,654 alerts;
reported ranking metrics use the common 9,655-alert budget. No original threshold
was changed to accommodate this difference.

The complete two-fit run took **480.230 seconds** with **987.86 MiB** process peak
RSS. Some small verification tests ran concurrently; timings include local cache
and scheduling effects and are not controlled benchmarks. Each fit's measured
cost is in the report. No new test/stress model evaluation occurred.

See [measured comparison](graph_prediction_report.md) for AP, ROC-AUC, ranking
metrics, numerical diagnostics and the unchanged selection policy. The observed
AP gain of **0.06758809** and **36 additional positives** at the fixed ranking
budget support a promising group-level graph contribution on reused validation.
Retain the original selected model; any frozen candidate holdout comparison needs
separate authorization. No significance, generalization or calibration claim is made.
