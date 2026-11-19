# measured stabilization results

All new fits use September 1–6 training and September 7–8 validation only.
No test/stress labels were retrieved or evaluated. Original artifacts remain unchanged.

Training: 3,248,921 rows, 2,530 positives. Validation: 965,524 rows, 1,036 positives (0.1073% prevalence).

The predeclared decision rule recommends **history_none** for later final evaluation. This is a validation selection result; no final evaluation was run.

## Comparable metrics

AP and ROC-AUC are fractions. Precision and recall are percentages. All methods use the same exact 1% ranking budget and hashed identity tie order.

| Model | AP | ROC-AUC | Budget | TP | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Frozen history_lr_1.0 | 0.26172877 | 0.97426269 | 9,655 | 607 | 6.2869% | 58.5907% |
| history_none | 0.56053649 | 0.98298160 | 9,655 | 824 | 8.5344% | 79.5367% |
| history_sqrt | 0.52380416 | 0.98477579 | 9,655 | 832 | 8.6173% | 80.3089% |
| history_full | 0.38652489 | 0.98380288 | 9,655 | 784 | 8.1201% | 75.6757% |
| history_no_format_none | 0.46357524 | 0.97240420 | 9,655 | 728 | 7.5401% | 70.2703% |
| history_no_format_sqrt | 0.43948821 | 0.97493202 | 9,655 | 729 | 7.5505% | 70.3668% |
| history_no_format_full | 0.36717680 | 0.97201543 | 9,655 | 664 | 6.8773% | 64.0927% |

| Model | K | TP | Precision@K | Recall@K |
| --- | ---: | ---: | ---: | ---: |
| Frozen history_lr_1.0 | 100 | 85 | 85.0000% | 8.2046% |
| Frozen history_lr_1.0 | 1,000 | 316 | 31.6000% | 30.5019% |
| Frozen history_lr_1.0 | 10,000 | 612 | 6.1200% | 59.0734% |
| history_none | 100 | 100 | 100.0000% | 9.6525% |
| history_none | 1,000 | 541 | 54.1000% | 52.2201% |
| history_none | 10,000 | 831 | 8.3100% | 80.2124% |
| history_sqrt | 100 | 99 | 99.0000% | 9.5560% |
| history_sqrt | 1,000 | 497 | 49.7000% | 47.9730% |
| history_sqrt | 10,000 | 832 | 8.3200% | 80.3089% |
| history_full | 100 | 98 | 98.0000% | 9.4595% |
| history_full | 1,000 | 377 | 37.7000% | 36.3900% |
| history_full | 10,000 | 793 | 7.9300% | 76.5444% |
| history_no_format_none | 100 | 99 | 99.0000% | 9.5560% |
| history_no_format_none | 1,000 | 450 | 45.0000% | 43.4363% |
| history_no_format_none | 10,000 | 734 | 7.3400% | 70.8494% |
| history_no_format_sqrt | 100 | 100 | 100.0000% | 9.6525% |
| history_no_format_sqrt | 1,000 | 428 | 42.8000% | 41.3127% |
| history_no_format_sqrt | 10,000 | 733 | 7.3300% | 70.7529% |
| history_no_format_full | 100 | 98 | 98.0000% | 9.4595% |
| history_no_format_full | 1,000 | 369 | 36.9000% | 35.6178% |
| history_no_format_full | 10,000 | 667 | 6.6700% | 64.3822% |

## Matched payment-format ablation

| Weight policy | History AP | No-format AP | AP difference |
| --- | ---: | ---: | ---: |
| none | 0.56053649 | 0.46357524 | +0.09696126 |
| sqrt | 0.52380416 | 0.43948821 | +0.08431595 |
| full | 0.38652489 | 0.36717680 | +0.01934809 |

## Numerical stability and ties

Near endpoints means ≤1e-12 or ≥1−1e-12. Raw margins are diagnostic only; probability-scale scores remain the ranking policy.

| Model | Split | Raw min | Raw max | Exact 0 / 1 | Near endpoints | Unique scores | Largest tie | Top tie |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| history_none | train | -11.9742 | 3.5650 | 0 / 0 | 0 | 2,260,312 | 45,815 | 1 |
| history_none | validation | -11.8851 | 3.6581 | 0 / 0 | 0 | 794,680 | 306 | 1 |
| history_sqrt | train | -11.0990 | 3.8133 | 0 / 0 | 0 | 2,615,936 | 70,670 | 1 |
| history_sqrt | validation | -11.0583 | 3.7427 | 0 / 0 | 0 | 920,141 | 94 | 1 |
| history_full | train | -13.0734 | 4.0458 | 0 / 0 | 0 | 1,707,196 | 61,360 | 117 |
| history_full | validation | -12.1127 | 4.0458 | 0 / 0 | 0 | 582,496 | 1,507 | 94 |
| history_no_format_none | train | -11.6744 | 4.1448 | 0 / 0 | 0 | 2,399,756 | 39,579 | 1 |
| history_no_format_none | validation | -11.4633 | 3.8363 | 0 / 0 | 0 | 816,986 | 218 | 1 |
| history_no_format_sqrt | train | -9.8328 | 3.8217 | 0 / 0 | 0 | 2,536,338 | 57,394 | 1 |
| history_no_format_sqrt | validation | -9.8570 | 3.8469 | 0 / 0 | 0 | 878,055 | 406 | 1 |
| history_no_format_full | train | -11.8538 | 3.9395 | 0 / 0 | 0 | 2,393,653 | 67,040 | 2 |
| history_no_format_full | validation | -11.5551 | 3.9248 | 0 / 0 | 0 | 831,874 | 585 | 1 |

## Thresholds, stability and measured cost

Threshold alerts preserve whole score tiers; ranking budgets above may split ties.
Prediction time includes train and validation raw-margin/probability diagnostics.

| Model | Threshold ≥ | Alerts | True alerts | Stable | Fit s | Predict s |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| history_none | 0.011489041059356882 | 9,655 | 824 | True | 96.01 | 40.09 |
| history_sqrt | 0.24935145345898621 | 9,655 | 832 | True | 94.48 | 42.80 |
| history_full | 0.90267917589630275 | 9,655 | 784 | True | 88.11 | 34.51 |
| history_no_format_none | 0.0088369386356210878 | 9,655 | 728 | True | 105.74 | 44.02 |
| history_no_format_sqrt | 0.2124038192168545 | 9,655 | 729 | True | 99.98 | 42.81 |
| history_no_format_full | 0.87748867769432459 | 9,655 | 664 | True | 95.30 | 37.38 |

| Model | Trees | Max post-initial leaf | Train loss first → last | Warnings |
| --- | ---: | ---: | --- | --- |
| history_none | 240 | 0.060000 | 0.006296 → 0.002877 | The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead. |
| history_sqrt | 240 | 0.060000 | 0.006340 → 0.014580 | The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead. |
| history_full | 240 | 0.060000 | 0.006340 → 0.167768 | The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead. |
| history_no_format_none | 240 | 0.060000 | 0.006312 → 0.003460 | The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead. |
| history_no_format_sqrt | 240 | 0.060000 | 0.006344 → 0.017441 | The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead. |
| history_no_format_full | 240 | 0.060000 | 0.006353 → 0.248454 | The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead. |

Training logloss is the unweighted training diagnostic; weighted objectives need not minimize it. Every full trace is saved, with no early stopping.

Total runtime: 940.731 seconds; process peak RSS: 1657.41 MiB. These local measurements are not benchmarks.
Shared preprocessing seconds: history=37.338, history_no_format=30.529.

## Provenance and limitations

Plan saved at `2026-10-14T17:57:05.955454+00:00`; run completed at `2026-10-14T18:12:54.526191+00:00`.
The plan predates both label exports:
- train: 3,248,921 rows, completed `2026-10-14T17:57:19.333080+00:00`.
- validation: 965,524 rows, completed `2026-10-14T17:57:24.051724+00:00`.

Plan SHA-256: `29b4476986270fd1d9166179dcb72ee495dcf4378304d081d8465665c7687950`.
Historical feature SHA-256: `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`.

All original artifact hashes match, preprocessing matches the train-fitted originals, and every new saved validation score reproduced exactly on model reload.

This fixed six-fit follow-up reuses development validation already used for model selection. Improvements are not unbiased estimates or significance claims. The regularization changes form a combined stabilization intervention; this study does not isolate the causal effect of each setting. Payment-format reliance, synthetic-data shortcuts, left-censored histories, and immediate attribute availability remain limitations. No calibration was fitted or tested, including for unweighted models. Scores are review priorities, not proof of laundering.

See [the predeclared contract](ml_stabilization.md) and [verification](ml_stabilization_verification.md).
