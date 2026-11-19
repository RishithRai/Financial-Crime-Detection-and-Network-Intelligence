# Supervised model recovery verification

Final verification subsequently started Docker Desktop and the existing Compose
PostgreSQL service successfully: **84 tests passed in 5.95 seconds**, with no
skips or failures. Ruff lint and formatting also passed. The recovery account
below is retained as history; its database blocker is resolved. See
[final model diagnostics](ml_final_verification.md) for the completed checks,
feature contribution review, and LightGBM saturation findings.

Recovery inspection on 2026-10-14 found a completed ten-experiment run under
ignored `data/ml/supervised-v1/`. Training had finished at
`2026-10-14T05:58:09.672627+00:00`, before the interrupted session was resumed.
The model bundles, preprocessing, thresholds, metadata, validation predictions,
experiment plan, measured report, and an earlier artifact audit already existed.
No retraining or additional experiment selection was needed.

The unfinished work was a report-renderer line-length lint error and this missing
verification document, already linked from README and the ML documentation.
Recovery fixed the renderer's string formatting, regenerated the aggregate report,
and repeated verification. Frozen training code, models, thresholds, historical
features, source data, and rules were preserved. The earlier artifact audit was
retained as `verification_before_resume.json` before refreshing `verification.json`.

## Artifact and temporal checks

| Check | Recovery result |
| --- | --- |
| Planned versus completed experiments | All 10 configurations match; documentation plan equals saved plan |
| Incomplete training | No `.ml-*` staging directories, temporary labels, or matrix files remain |
| Build lock | Existing `.build.lock` is not held; its presence does not indicate an active run |
| Model integrity | All model hashes match metadata; feature names align after reload |
| Prediction integrity | All 10 prediction hashes and metadata match completed results |
| Full reload audit | 965,524 validation scores per model, 9,655,240 total; exact equality |
| Prediction coverage | Unique source rows match validation features; only source row and score are persisted |
| Operating thresholds | Reloaded alert counts equal saved results for every model |
| Preprocessing population | Every bundle records 3,248,921 training rows |
| Training implementation | Saved `ml.py` and `ml_training.py` hashes match current files |
| Historical features | SHA-256 remains `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89` |
| Frozen rules comparison | Existing validation-prediction hash matches the ML results |
| Locked environment | `uv sync --locked` passed; lock hash matches saved audit |
| Git exclusions | `data/ml/` artifacts and `.env` remain ignored |

The plan was saved at `2026-10-14T05:50:02.470479+00:00`, before the recorded
training label export completed at `05:50:07.330065+00:00` and validation export
at `05:50:12.233208+00:00`. These are the only two label accesses recorded by
the training run. Recovery used existing aggregate metrics and label-free
validation predictions; it retrieved no dataset labels and did not predict or
evaluate test/stress rows. Saved timestamps and hashes are reproducibility
evidence, not an independent adversarial audit.

## Checks executed during recovery

After installing dependencies as described in the README:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python -m mulegraph.ml_report
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
# Recovery invoked this module's verify() function after preserving the old audit:
uv run --locked python -m mulegraph.ml_verify --features-dir "$FEATURE_DIR"
```

Ruff lint and formatting passed after the renderer fix (43 files formatted).
Pytest finished with **66 passed, 18 skipped in 1.41 seconds**, no failures.
The 18 skips are opt-in PostgreSQL tests, including the ML train/validation label
export integration test. Docker Compose could not reach its daemon because the
Docker socket was absent, and the configured database connectivity check failed.
Database integration verification therefore remains outstanding; no database
volumes or configuration were changed. Earlier stage test results are not
substitutes for this recovery's skipped checks.

The full artifact audit succeeded without PostgreSQL. Arrow emitted sandbox
CPU-cache discovery diagnostics (`sysctlbyname: Operation not permitted`), which
did not prevent scoring or verification. Unit tests cover input isolation,
train-only preprocessing, unknown categories, missingness, temporal alignment,
holdout guards, metrics and ties, model reloads, repeated seeded fits, artifact
corruption rejection, threshold precision, and overwrite prevention.

## Measured validation outcome and remaining limitations

The predeclared AP objective selected **history_lr_1.0**: AP **0.26172877**,
ROC-AUC **0.97426269**. At 9,655 alerts (the common 1% ranking budget), it catches
607 of 1,036 positives: precision **6.2869%**, recall **58.5907%**. Precision@100
is **85%** and Precision@1,000 is **31.6%**. Validation prevalence is **0.1073%**;
training has 2,530 positives among 3,248,921 rows. Its frozen numeric threshold
is `0.9535042643547059` and yields the same 9,655 alerts on validation.

All five LightGBM fits exhibit score saturation, producing a top score tie larger
than the alert cap and zero whole-tier threshold alerts. This measured limitation
was preserved, without retuning. Full-run cost was 488.108 seconds and 1,551.91 MiB
process peak RSS; these are saved original-run measurements, not recovery timings.
Scores are class-weighted review priorities, not calibrated probabilities or proof
of laundering. Validation selection and synthetic-data limitations still apply.

Git inspection found an unborn `main` branch with all project sources untracked.
Recovery did not reset, stage, or create a repository-wide initial commit. Existing
work remains intact but is not yet protected by a Git commit.

initial supervised-learning stage implementation and saved validation artifacts are complete. The
remaining verification issue is rerunning the PostgreSQL suite when the service
is available. Test/stress evaluation remains outside this stage.

See [measured results](ml_report.md) and [implementation contract](supervised_learning.md).
