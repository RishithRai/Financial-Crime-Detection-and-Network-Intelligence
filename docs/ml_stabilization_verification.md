# LightGBM stabilization verification

The six predeclared fits completed successfully under `data/ml/lightgbm-stable-v1/`.
No extra configurations or seeds were tried after examining validation. The
original Logistic Regression, all original LightGBM models, predictions,
thresholds, and results were preserved byte-for-byte. Raw data and historical
features were not modified. No real test/stress labels were accessed.

## Checks and actual results

| Check | Result |
| --- | --- |
| Locked environment | `uv sync --locked` passed; dependency files unchanged |
| Ruff lint | Passed |
| Ruff format check | Passed |
| Full PostgreSQL-enabled suite | **90 passed in 5.03 seconds**, no failures, skips, or warnings |
| Predeclaration | Plan timestamp precedes both label exports; six configurations match the saved plan |
| Training-only preprocessing | Both rebuilt variants exactly match frozen training means, scales, vocabularies and names |
| Label export integrity | Train and validation export hashes exactly match the original run |
| Frozen LR comparison | Re-evaluated saved validation predictions; all metrics including threshold exactly match originals |
| Original artifacts | All original supervised file hashes match the predeclared snapshot |
| Historical features | File SHA-256 unchanged |
| Persistence | Labels excluded from prediction schemas; hashes and source-row coverage verified |
| Independent label-free reload audit | **5,793,144** scores exactly match; margins and alert counts match |
| Independent audit runtime | 97.372 seconds |
| Scratch cleanup | No `.stable-*` directory, label exports, or temporary matrices remain |

PostgreSQL tests use disposable synthetic `mg_test_*` schemas and preserve the
real dataset. Earlier-milestone test/stress fixtures are synthetic, not accesses
to the real holdout labels. The production training module imports the existing
train/validation-only label export guard and never requests any other split.

New tests cover approved weight policies and invalid class counts, saturation
and score ties, nonfinite output rejection, fixed recommendation criteria,
bounded leaf updates under severe imbalance, repeated seeded fits, a complete
synthetic six-fit pipeline, label-free reload auditing, report rendering,
prediction corruption, original preservation, failed-run cleanup, and refusal
to overwrite plans or rerun a completed/failed attempt. Existing point-in-time
and train-only isolation tests also passed.

The immutable training plan and implementation hashes were verified before
label access and again before publishing the complete output directory. An
attempt record remains intentionally alongside the output to prevent accidental
refitting. The artifact audit did not query PostgreSQL. Any Arrow CPU-cache
discovery diagnostics in the restricted audit process did not affect its result.

Each real fit captured a LightGBM API deprecation warning for `eval_set`
(`eval_X` / `eval_y` are the suggested replacement). Training completed
successfully and the warning is retained in each model metadata record and
the measured report. The executed implementation stays frozen to its plan;
adopting the new API is future compatibility maintenance, not a reason to refit
or change the selected model. Pytest itself emitted no warnings.

## Numerical outcome and recommendation

- `history_none`: stable=True; validation raw margins [-11.8851, 3.6581], exact endpoints 0, near endpoints 0, top-score tie 1 rows.
- `history_sqrt`: stable=True; validation raw margins [-11.0583, 3.7427], exact endpoints 0, near endpoints 0, top-score tie 1 rows.
- `history_full`: stable=True; validation raw margins [-12.1127, 4.0458], exact endpoints 0, near endpoints 0, top-score tie 94 rows.
- `history_no_format_none`: stable=True; validation raw margins [-11.4633, 3.8363], exact endpoints 0, near endpoints 0, top-score tie 1 rows.
- `history_no_format_sqrt`: stable=True; validation raw margins [-9.8570, 3.8469], exact endpoints 0, near endpoints 0, top-score tie 1 rows.
- `history_no_format_full`: stable=True; validation raw margins [-11.5551, 3.9248], exact endpoints 0, near endpoints 0, top-score tie 1 rows.

Every post-initial tree update obeys the 0.06 bound. The first tree
includes the intercept. No margins or final scores were clipped. Training
loss traces were recorded for all iterations and were not used for stopping.

Recommend freezing **history_none** for the subsequent frozen holdout evaluation.
Its validation AP is **0.56053649** versus LR's **0.26172877**; ROC-AUC is **0.98298160** versus **0.97426269**. At 9,655 ranked alerts, it catches **824** positives versus **607**: precision **8.5344%**, recall **79.5367%**.

The new saved whole-tier threshold is `0.011489041059356882`. Keep the saved preprocessing, model, scoring policy and threshold fixed.
This recommendation is recorded only in the new results; the original
selection and threshold remain unchanged as a comparison baseline.

The square-root-weight history model catches 832 positives at the same budget
versus 824 for the AP winner, and has ROC-AUC 0.98478 versus 0.98298.
Its AP is lower (0.52380 versus 0.56054), so the predeclared AP rule selects
the unweighted model. The objective was not changed after this tradeoff emerged.
Without payment format, unweighted history AP is 0.46358: the improvement
is not solely attributable to payment format, though its contribution remains material.

Decisions and limitations:

- Do not add more validation tuning to this stage. Any further experiment
  needs a separate predeclared scope.
- The same validation period has now been reused for two bounded model
  comparisons. Neither the AP gain nor the recommendation proves generalization
  or statistical significance; future evaluation remains a development holdout.
- Payment-format effects are measured by the matched ablations in the report.
  Synthetic shortcuts and retrospective attribute-availability assumptions persist.
- No probability calibration was fitted or tested. Even the unweighted model
  produces review scores, not verified probabilities or proof of wrongdoing.

## Reproduction

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked python -m mulegraph.ml_stabilization_report \
  --verify --features-dir "$FEATURE_DIR"
```

The plan and training commands are documented in the [contract](ml_stabilization.md).
Completed training refuses reruns; report generation and the label-free audit
can be repeated without fitting or retrieving labels.

See [all measured results](ml_stabilization_report.md).
