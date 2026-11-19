# measured training and validation results

All results below use September 7–8 validation only. No test/stress labels were accessed by this pipeline, and no test/stress predictions were made.

Training: 3,248,921 rows, 2,530 positive labels. Validation: 965,524 rows, 1,036 positives (0.107% prevalence).

The predeclared highest-AP selection recommends **history_lr_1.0** for the subsequent frozen holdout evaluation. This is a validation selection result, not a test result or evidence of real-world utility.

## All experiments and comparable 1% ranking budget

AP and ROC-AUC are fractions; precision/recall are percentages. The exact ranking budget is 9,655 alerts for every method.

| Experiment | AP | ROC-AUC | Budget TP | Budget precision | Budget recall | Fit s | Predict s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current_lr_1.0 | 0.01514182 | 0.907459 | 87 | 0.901% | 8.398% | 7.63 | 1.60 |
| current_lightgbm_15 | 0.00786674 | 0.840877 | 92 | 0.953% | 8.880% | 13.44 | 1.86 |
| current_no_format_lr_1.0 | 0.00235803 | 0.741324 | 25 | 0.259% | 2.413% | 3.73 | 0.18 |
| current_no_format_lightgbm_15 | 0.00144360 | 0.625783 | 14 | 0.145% | 1.351% | 16.28 | 1.91 |
| history_lr_1.0 | 0.26172877 | 0.974263 | 607 | 6.287% | 58.591% | 63.72 | 3.13 |
| history_lightgbm_15 | 0.00870211 | 0.829842 | 89 | 0.922% | 8.591% | 41.51 | 2.99 |
| history_lr_0.1 | 0.25502194 | 0.974189 | 609 | 6.308% | 58.784% | 38.20 | 2.67 |
| history_lightgbm_31 | 0.00855837 | 0.829937 | 90 | 0.932% | 8.687% | 44.19 | 3.40 |
| history_no_format_lr_1.0 | 0.18536530 | 0.939187 | 501 | 5.189% | 48.359% | 45.12 | 0.86 |
| history_no_format_lightgbm_15 | 0.00512276 | 0.751954 | 57 | 0.590% | 5.502% | 39.36 | 2.03 |
| ach_score | 0.00669108 | 0.869391 | 73 | 0.756% | 7.046% | — | — |
| constant_score | 0.00107299 | 0.500000 | 7 | 0.073% | 0.676% | — | — |
| risk_score | 0.00113290 | 0.508573 | 23 | 0.238% | 2.220% | — | — |

## Matched ablation comparisons

These compare identical default model settings, so they do not confound history/payment-format changes with hyperparameter changes.

| Family | Current AP | History AP | History AP gain | Current no-format AP | History no-format AP | History payment-format AP difference |
| --- | --- | --- | --- | --- | --- | --- |
| lr | 0.01514182 | 0.26172877 | +0.24658694 | 0.00235803 | 0.18536530 | +0.07636346 |
| lightgbm | 0.00786674 | 0.00870211 | +0.00083538 | 0.00144360 | 0.00512276 | +0.00357935 |

History gain and format reliance are empirical associations in this synthetic dataset. A positive format difference is not evidence that any payment method is inherently suspicious. No configuration was added after reviewing these outcomes.

## Precision@K and Recall@K

| Method | K | True positives | Precision@K | Recall@K |
| --- | --- | --- | --- | --- |
| current_lr_1.0 | 100 | 4 | 4.000% | 0.386% |
| current_lr_1.0 | 1,000 | 17 | 1.700% | 1.641% |
| current_lr_1.0 | 10,000 | 87 | 0.870% | 8.398% |
| current_lightgbm_15 | 100 | 0 | 0.000% | 0.000% |
| current_lightgbm_15 | 1,000 | 8 | 0.800% | 0.772% |
| current_lightgbm_15 | 10,000 | 93 | 0.930% | 8.977% |
| current_no_format_lr_1.0 | 100 | 2 | 2.000% | 0.193% |
| current_no_format_lr_1.0 | 1,000 | 4 | 0.400% | 0.386% |
| current_no_format_lr_1.0 | 10,000 | 27 | 0.270% | 2.606% |
| current_no_format_lightgbm_15 | 100 | 0 | 0.000% | 0.000% |
| current_no_format_lightgbm_15 | 1,000 | 3 | 0.300% | 0.290% |
| current_no_format_lightgbm_15 | 10,000 | 14 | 0.140% | 1.351% |
| history_lr_1.0 | 100 | 85 | 85.000% | 8.205% |
| history_lr_1.0 | 1,000 | 316 | 31.600% | 30.502% |
| history_lr_1.0 | 10,000 | 612 | 6.120% | 59.073% |
| history_lightgbm_15 | 100 | 0 | 0.000% | 0.000% |
| history_lightgbm_15 | 1,000 | 7 | 0.700% | 0.676% |
| history_lightgbm_15 | 10,000 | 91 | 0.910% | 8.784% |
| history_lr_0.1 | 100 | 82 | 82.000% | 7.915% |
| history_lr_0.1 | 1,000 | 313 | 31.300% | 30.212% |
| history_lr_0.1 | 10,000 | 613 | 6.130% | 59.170% |
| history_lightgbm_31 | 100 | 0 | 0.000% | 0.000% |
| history_lightgbm_31 | 1,000 | 7 | 0.700% | 0.676% |
| history_lightgbm_31 | 10,000 | 92 | 0.920% | 8.880% |
| history_no_format_lr_1.0 | 100 | 77 | 77.000% | 7.432% |
| history_no_format_lr_1.0 | 1,000 | 251 | 25.100% | 24.228% |
| history_no_format_lr_1.0 | 10,000 | 506 | 5.060% | 48.842% |
| history_no_format_lightgbm_15 | 100 | 0 | 0.000% | 0.000% |
| history_no_format_lightgbm_15 | 1,000 | 5 | 0.500% | 0.483% |
| history_no_format_lightgbm_15 | 10,000 | 61 | 0.610% | 5.888% |
| ach_score | 100 | 0 | 0.000% | 0.000% |
| ach_score | 1,000 | 7 | 0.700% | 0.676% |
| ach_score | 10,000 | 77 | 0.770% | 7.432% |
| constant_score | 100 | 0 | 0.000% | 0.000% |
| constant_score | 1,000 | 0 | 0.000% | 0.000% |
| constant_score | 10,000 | 7 | 0.070% | 0.676% |
| risk_score | 100 | 0 | 0.000% | 0.000% |
| risk_score | 1,000 | 3 | 0.300% | 0.290% |
| risk_score | 10,000 | 23 | 0.230% | 2.220% |

## Selected numeric thresholds

Thresholds retain complete score tiers within the 1% cap. Ranking budgets above may split ties. Frozen rules keep their original score≥2 policy: 6,912 alerts, 21 true alerts, 0.3038% precision, 2.0270% recall. Their score and weights were not changed.

| Experiment | Threshold (≥) | Alerts | True alerts | Precision | Recall |
| --- | --- | --- | --- | --- | --- |
| current_lr_1.0 | 0.92149907350540172 | 9,655 | 87 | 0.901% | 8.398% |
| current_lightgbm_15 | 1.0000000000000002 | 0 | 0 | undefined | 0.000% |
| current_no_format_lr_1.0 | 0.87562197446823131 | 9,655 | 25 | 0.259% | 2.413% |
| current_no_format_lightgbm_15 | 1.0000000000000002 | 0 | 0 | undefined | 0.000% |
| history_lr_1.0 | 0.95350426435470592 | 9,655 | 607 | 6.287% | 58.591% |
| history_lightgbm_15 | 1.0000000000000002 | 0 | 0 | undefined | 0.000% |
| history_lr_0.1 | 0.9528181552886964 | 9,655 | 609 | 6.308% | 58.784% |
| history_lightgbm_31 | 1.0000000000000002 | 0 | 0 | undefined | 0.000% |
| history_no_format_lr_1.0 | 0.94227701425552379 | 9,655 | 501 | 5.189% | 48.359% |
| history_no_format_lightgbm_15 | 1.0000000000000002 | 0 | 0 | undefined | 0.000% |

## Computation and fit diagnostics

The completed run took 488.108 seconds. Python process lifetime peak RSS was 1551.91 MiB. This is a local measurement, not a benchmark or server memory measure. Fit and prediction times exclude preprocessing; shared preprocessing is listed once per variant below.

| Variant | Preprocessing s | Encoded columns |
| --- | --- | --- |
| current | 22.056 | 44 |
| current_no_format | 17.498 | 36 |
| history | 40.799 | 84 |
| history_no_format | 37.629 | 76 |

| Experiment | Iterations (LR) | Fit warnings |
| --- | --- | --- |
| current_lr_1.0 | [35] | None |
| current_lightgbm_15 | fixed 120 trees | None |
| current_no_format_lr_1.0 | [20] | None |
| current_no_format_lightgbm_15 | fixed 120 trees | None |
| history_lr_1.0 | [134] | None |
| history_lightgbm_15 | fixed 120 trees | None |
| history_lr_0.1 | [162] | None |
| history_lightgbm_31 | fixed 120 trees | None |
| history_no_format_lr_1.0 | [147] | None |
| history_no_format_lightgbm_15 | fixed 120 trees | None |

## Score saturation diagnostic

All five tested LightGBM configurations place more than 1% of rows at exactly 1.0. A whole-tier numeric cutoff therefore alerts zero rows under the cap. Their exact-budget results select an arbitrary hashed subset of the top tie, and probability-scale saturation collapses ranking resolution. These fits are not recommended. Investigating stabilization or raw-margin ranking would require a separately declared development experiment; no such retuning was done.

| Experiment | Scores exactly 0 | Scores exactly 1 | Distinct scores |
| --- | --- | --- | --- |
| current_lr_1.0 | 0 | 0 | 551,048 |
| current_lightgbm_15 | 68,171 | 90,201 | 883 |
| current_no_format_lr_1.0 | 0 | 0 | 450,338 |
| current_no_format_lightgbm_15 | 504,629 | 371,120 | 90 |
| history_lr_1.0 | 0 | 0 | 942,663 |
| history_lightgbm_15 | 93,597 | 88,044 | 38,780 |
| history_lr_0.1 | 0 | 0 | 939,787 |
| history_lightgbm_31 | 105,226 | 88,489 | 44,622 |
| history_no_format_lr_1.0 | 0 | 0 | 945,661 |
| history_no_format_lightgbm_15 | 288,005 | 116,542 | 102,768 |

## Selected model interpretation

Largest gain importances or absolute LR coefficients. Numeric inputs are standardized; one-hot categories and missingness flags are unscaled. Correlated counts and flags make individual coefficients non-unique interpretations, not causal effects or independent evidence:

| Encoded feature | Value |
| --- | --- |
| sender_currency_history_count | -7.37266 |
| payment_format=ACH | 4.66831 |
| sender_history_count | 3.73309 |
| payment_format=Reinvestment | -3.70494 |
| payment_format=Wire | -3.06325 |
| sender_sent_count | 2.62578 |
| sender_currency_count_24h | 2.32742 |
| sender_history_age_seconds__missing | 2.25419 |
| sender_seconds_since_last__missing | 2.25419 |
| sender_seconds_since_last | 1.99463 |
| sender_unique_counterparties | 1.5964 |
| cross_currency | -1.3574 |

## Limitations and next decision

Review the chosen model, operational availability of receiving-side attributes, 1% workload budget, and payment-format ablation before authorizing final evaluation. Keep the chosen preprocessing/model and threshold fixed. No calibration has been fitted; class-weighted scores are not calibrated probabilities. Alerting is a request for review, not proof of laundering.

The selected budget includes 9,048 negative-labeled transactions. C=0.1 catches two more positives at the same budget, but C=1 wins the predeclared AP objective. Review whether that objective matches operational priorities before future development. All ten configurations used the same validation period for comparison. There are no confidence intervals or multiple-selection corrections. History is left-censored and rolls across chronological splits under the immediate-arrival assumption. Synthetic shortcuts and the previously documented post–September 10 shift limit generalization. Earlier EDA/rules results mean future evaluation remains a development holdout rather than an untouched external validation set.

Feature checksum remained `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`. Plan, per-experiment parameters, preprocessing, coefficients/importance, model/prediction checksums, and label-access records are saved under `data/ml/supervised-v1`. Read [the contract](supervised_learning.md) and [verification](ml_verification.md).
