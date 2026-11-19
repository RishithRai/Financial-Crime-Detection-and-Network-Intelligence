# Frozen holdout verification

The selected model is frozen as `lightgbm-stable-v1/history_none`. The primary
test (September 9–10, 2022) and stress (September 11–18) were evaluated separately.
No model, preprocessor, feature, selection rule, or operating threshold changed.
These are **development holdouts**: earlier EDA and rules evaluation inspected
these periods. This is their first evaluation with these supervised models.

## Integrity and execution

The freeze was recorded at `2026-10-14T18:35:45.223509+00:00`, before either
frozen holdout stage label export. Its SHA-256 is
`4a727df4fcb728bea955f2c4ff206810b52ebf64b564a14f89c3507378c25e83`.
Verification covered model bytes, parameters, feature names, preprocessing,
training population, implementation signatures, dependencies and thresholds.
The two saved preprocessors agree exactly; their training-only provenance is
also established by the prior independent recomputation in Milestones 4A/4A.1.
No preprocessing was refitted here. All **1,931,048** saved validation scores for
LightGBM and LR reproduced before holdout access, without fetching labels.

Both holdout prediction files were generated before either label export.
The freeze and all original artifact hashes were checked immediately before
each export and again before atomic publication. Test labels were exported at
`2026-10-14T18:39:38.896654+00:00`; stress labels at
`2026-10-14T18:39:48.965068+00:00`. Both export hashes equal the earlier rules
stage exports, confirming the same evaluation populations. Labels were aligned
by unique source row, used separately for metrics, and removed from scratch.
Hashes and timestamps are reproducibility evidence, not an adversarial audit.

| Check | Actual result |
| --- | --- |
| Full PostgreSQL-enabled suite | **105 passed in 4.72 seconds**, no failures, skips or warnings |
| Ruff lint and formatting | Passed |
| Original ML, rules and feature artifacts | All frozen source hashes unchanged |
| Historical feature SHA-256 | `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89` |
| Persisted prediction coverage | 862,792 unique test rows; 1,108 unique stress rows |
| Prediction schemas | Source row and five scores only; no labels |
| Independent label-free audit | **4,319,500** scores reproduced exactly across five methods |
| Audit duration | 15.158 seconds; no label accesses |
| Original rules/ACH/constant predictions | Every score exactly matches prior holdout artifacts |
| Evaluation duration | 33.621 seconds; local run timing, not a benchmark |
| Scratch cleanup | No temporary holdout directory or label exports remain |

The durable attempt record deliberately remains to prevent accidental repeated
label evaluation. Completed runs refuse reruns; aggregate report rendering and
label-free verification are repeatable. Arrow emitted restricted CPU-cache
inspection diagnostics during the audit; scoring and verification succeeded.

Tests cover exact alignment, missing/duplicate identities, binary labels, tied
AP/AUC, empty ranking budgets, capped K, single-class metrics, float64 threshold
boundaries, deterministic predictions, temporal boundaries, model/source
corruption, threshold tampering, freeze-before-export ordering, both predictions
before either export, cleanup, report rendering and prediction corruption.
PostgreSQL tests use disposable synthetic `mg_test_*` schemas and preserve the
real dataset. A new integration test checks test/stress SQL boundaries and the
freeze gate; the real evaluation was run separately with the declared evaluation labels.

## Primary test interpretation

Test has 956 positives among 862,792 rows (prevalence **0.110803%**), close to
validation's 0.1073%. LightGBM AP decreased from **0.56054 to 0.51396** and
1% ranking-budget recall from **79.54% to 75.00%**. LR AP decreased from
**0.26173 to 0.17152** and budget recall from **58.59% to 41.63%**.
LightGBM retains a substantial measured advantage on this development holdout.

At 8,627 ranked alerts, LightGBM catches 717 positives (precision **8.3111%**),
versus LR's 398 (precision **4.6134%**). LightGBM Precision@100 is **98%** and
Precision@1,000 is **46.8%**. Rules AP is **0.001170**, ACH-only **0.006245**,
and prevalence **0.001108**. Complete comparator metrics and confusion matrices
are in the versioned report.

The unchanged LightGBM threshold produces **13,726 alerts (1.5909%)**, with
757 TP, 12,969 FP, 199 FN and 848,867 TN. LR produces **26,360 alerts (3.0552%)**,
with 550 TP, 25,810 FP, 406 FN and 836,026 TN. The 1% constraint applied to
validation; neither threshold guarantees 1% on later populations. No adjustment
was made to force either holdout back under the budget.

A concerning coverage pattern remains: **all threshold-based true positives
for both supervised models are ACH**. Both miss all **122 non-ACH positives**.
LightGBM emits 13,683 ACH alerts and 43 Credit Card alerts, with the latter all
false positives. ACH contains 834 of 956 test positives but only 13.82% of rows.
This is strong payment-format dependence, consistent with a possible synthetic
shortcut; it does not establish causation or justify changing the model here.
The matched validation ablation already showed useful performance without format.

## Stress interpretation

Stress has only **1,108 rows**, **655 positives (59.1155%)**, and **100% ACH**.
Daily volume falls from 396 rows on September 11 to 11 on September 18. The
median sender inactivity rises from 1,380 seconds on test to 64,500 on stress,
and median currency-specific sender history falls from 37 to 2. These changes
suggest a very different activity/coverage regime; the generator mechanism is
not established. Amount distributions are reported within currency, with public
quantiles suppressed for groups smaller than 20 rows.

LightGBM stress AP is **0.93860**, ROC-AUC **0.93475**; LR AP is **0.94591**,
ROC-AUC **0.95043**. This small LR advantage does **not** change the selection.
Higher stress AP than test is not evidence of improvement: stress prevalence
is dramatically higher. LightGBM AP/prevalence is 1.588 on stress versus 463.85
on test, but even this ratio has a prevalence-dependent ceiling and does not
fully adjust for population difficulty. Its ROC-AUC declines on stress.

Both models capture 11 positives at the 11-alert ranking budget: precision
**100%**, recall only **1.6794%**. At its frozen threshold LightGBM alerts on
**695 rows (62.7256%)**, with 623 TP, 72 FP, 32 FN and 381 TN. LR alerts on
**593 (53.5199%)**, with 549 TP, 44 FP, 106 FN and 409 TN. ACH-only cannot
rank this population: every score ties, AP equals prevalence and ROC-AUC is 0.5.
Tie-broken ranking statistics for constant baselines are arbitrary ordering
outcomes. LightGBM has no exact probability endpoints on either split; LR has
one score equal to 1 on stress. No score clipping or calibration was applied.

## Recommendation and limits

Retain **history_none** as the frozen selected model. Do not select another
model or tune thresholds using these holdouts. Further validation requires representative, untouched temporal evaluation data,
feature-availability checks, realistic review capacity, and a separately
predeclared calibration/operating-policy study. The observed non-ACH misses and
stress cohort composition warrant investigation using dataset provenance and
future independent evidence, not more optimization against these labels.

Synthetic data, reused validation, prior aggregate holdout inspection, small
stress size, temporal dependence, left-censored history and assumed immediate
attribute availability limit generalization. No significance claim or probability
calibration claim is made. Scores prioritize review and do not prove wrongdoing.

## Commands

From the repository root, after installing dependencies as described in the README:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked python -m mulegraph.ml_holdout_report --verify --features-dir "$FEATURE_DIR"
```

See [the evaluation contract](ml_holdout_evaluation.md),
[immutable freeze](ml_holdout_freeze_v1.json), and
[all measured results](ml_holdout_report_v1.md).
