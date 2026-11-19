# frozen development-holdout results v1

Selected model: **lightgbm-stable-v1/history_none**, unchanged before and after evaluation.
Comparators: frozen Logistic Regression, rules, ACH-only, constant-score prevalence.
No retraining, model selection, feature changes or threshold adjustment occurred.
These periods were previously inspected by EDA/rules: they are development holdouts.

AP must be read against each split's prevalence. AP/prevalence is descriptive lift, not a complete adjustment for population differences. Results are never pooled.
Ranking budgets may split ties using the original label-free identity hash; threshold alerts preserve the original numeric policies.

## Test

Period: `2022-09-09T00:00:00` to `2022-09-11T00:00:00` (end exclusive). **862,792** transactions; **956** positives; prevalence **0.1108%**. Ranking budget: **8,627** alerts.

| Method | AP | AP/prevalence | ROC-AUC | P@100 | P@1,000 | P@1% | R@1% | Budget TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lightgbm | 0.513960 | 463.850203 | 0.979857 | 98.0000% | 46.8000% | 8.3111% | 75.0000% | 717 |
| logistic | 0.171517 | 154.794397 | 0.961977 | 74.0000% | 22.3000% | 4.6134% | 41.6318% | 398 |
| rules | 0.001170 | 1.056089 | 0.517270 | 0.0000% | 0.0000% | 0.1623% | 1.4644% | 14 |
| ach | 0.006245 | 5.636509 | 0.867525 | 0.0000% | 0.4000% | 0.6144% | 5.5439% | 53 |
| prevalence | 0.001108 | 1.000000 | 0.500000 | 0.0000% | 0.0000% | 0.0580% | 0.5230% | 5 |

Effective K: 100 for @100 and 1,000 for @1,000.

| Method | Frozen threshold ≥ | Alerts | Alert rate | Precision | Recall | TN | FP | FN | TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lightgbm | 0.011489041059356882 | 13,726 | 1.5909% | 5.5151% | 79.1841% | 848,867 | 12,969 | 199 | 757 |
| logistic | 0.95350426435470592 | 26,360 | 3.0552% | 2.0865% | 57.5314% | 836,026 | 25,810 | 406 | 550 |
| rules | 2 | 9,787 | 1.1343% | 0.1533% | 1.5690% | 852,064 | 9,772 | 941 | 15 |
| ach | 1 | 119,195 | 13.8150% | 0.6997% | 87.2385% | 743,475 | 118,361 | 122 | 834 |
| prevalence | 1 | 0 | 0.0000% | undefined | 0.0000% | 861,836 | 0 | 956 | 0 |

### Descriptive breakdown: day

| Group | Rows | Positives | Prevalence | LGB alerts | LGB TP | LR alerts | LR TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-09-09 | 654,467 | 514 | 0.0785% | 9,514 | 382 | 21,864 | 261 |
| 2022-09-10 | 208,325 | 442 | 0.2122% | 4,212 | 375 | 4,496 | 289 |

### Descriptive breakdown: payment_format

| Group | Rows | Positives | Prevalence | LGB alerts | LGB TP | LR alerts | LR TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ACH | 119,195 | 834 | 0.6997% | 13,683 | 757 | 26,071 | 550 |
| Bitcoin | 24,329 | 10 | 0.0411% | 0 | 0 | 4 | 0 |
| Cash | 91,737 | 19 | 0.0207% | 0 | 0 | 12 | 0 |
| Cheque | 347,008 | 60 | 0.0173% | 0 | 0 | 117 | 0 |
| Credit Card | 250,247 | 33 | 0.0132% | 43 | 0 | 155 | 0 |
| Wire | 30,276 | 0 | 0.0000% | 0 | 0 | 1 | 0 |

## Stress

Period: `2022-09-11T00:00:00` to `2022-09-19T00:00:00` (end exclusive). **1,108** transactions; **655** positives; prevalence **59.1155%**. Ranking budget: **11** alerts.

| Method | AP | AP/prevalence | ROC-AUC | P@100 | P@1,000 | P@1% | R@1% | Budget TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lightgbm | 0.938598 | 1.587735 | 0.934754 | 98.0000% | 65.5000% | 100.0000% | 1.6794% | 11 |
| logistic | 0.945908 | 1.600101 | 0.950429 | 96.0000% | 65.5000% | 100.0000% | 1.6794% | 11 |
| rules | 0.594898 | 1.006331 | 0.502679 | 59.0000% | 60.0000% | 90.9091% | 1.5267% | 10 |
| ach | 0.591155 | 1.000000 | 0.500000 | 61.0000% | 59.9000% | 72.7273% | 1.2214% | 8 |
| prevalence | 0.591155 | 1.000000 | 0.500000 | 61.0000% | 59.9000% | 72.7273% | 1.2214% | 8 |

Effective K: 100 for @100 and 1,000 for @1,000.

| Method | Frozen threshold ≥ | Alerts | Alert rate | Precision | Recall | TN | FP | FN | TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lightgbm | 0.011489041059356882 | 695 | 62.7256% | 89.6403% | 95.1145% | 381 | 72 | 32 | 623 |
| logistic | 0.95350426435470592 | 593 | 53.5199% | 92.5801% | 83.8168% | 409 | 44 | 106 | 549 |
| rules | 2 | 21 | 1.8953% | 66.6667% | 2.1374% | 446 | 7 | 641 | 14 |
| ach | 1 | 1,108 | 100.0000% | 59.1155% | 100.0000% | 0 | 453 | 0 | 655 |
| prevalence | 1 | 0 | 0.0000% | undefined | 0.0000% | 453 | 0 | 655 | 0 |

### Descriptive breakdown: day

| Group | Rows | Positives | Prevalence | LGB alerts | LGB TP | LR alerts | LR TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-09-11 | 396 | 232 | 58.5859% | 249 | 218 | 205 | 183 |
| 2022-09-12 | 281 | 170 | 60.4982% | 179 | 164 | 150 | 142 |
| 2022-09-13 | 184 | 106 | 57.6087% | 109 | 99 | 104 | 98 |
| 2022-09-14 | 121 | 70 | 57.8512% | 79 | 67 | 67 | 59 |
| 2022-09-15 | 46 | 28 | 60.8696% | 30 | 27 | 23 | 23 |
| 2022-09-16 | 46 | 26 | 56.5217% | 27 | 26 | 25 | 25 |
| 2022-09-17 | 23 | 15 | 65.2174% | 15 | 15 | 15 | 15 |
| 2022-09-18 | 11 | 8 | 72.7273% | 7 | 7 | 4 | 4 |

### Descriptive breakdown: payment_format

| Group | Rows | Positives | Prevalence | LGB alerts | LGB TP | LR alerts | LR TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ACH | 1,108 | 655 | 59.1155% | 695 | 623 | 593 | 549 |

## Label-free distribution shifts

Shares use the population of each split. These are descriptive comparisons,
not changes to predictors or operating policies.

### payment_format

| Value | Train | Validation | Test | Stress |
| --- | ---: | ---: | ---: | ---: |
| ACH | 11.1909% | 12.1085% | 13.8150% | 100.0000% |
| Bitcoin | 2.8662% | 2.9666% | 2.8198% | 0.0000% |
| Cash | 9.1045% | 10.7048% | 10.6326% | 0.0000% |
| Cheque | 34.4796% | 41.1288% | 40.2192% | 0.0000% |
| Credit Card | 24.3238% | 29.2916% | 29.0043% | 0.0000% |
| Reinvestment | 14.8066% | 0.0000% | 0.0000% | 0.0000% |
| Wire | 3.2285% | 3.7999% | 3.5091% | 0.0000% |

### payment_currency

| Value | Train | Validation | Test | Stress |
| --- | ---: | ---: | ---: | ---: |
| Australian Dollar | 2.6922% | 2.6983% | 2.6913% | 2.6173% |
| Bitcoin | 2.8656% | 2.9660% | 2.8196% | 0.0903% |
| Brazil Real | 1.3869% | 1.3900% | 1.4148% | 1.4440% |
| Canadian Dollar | 2.7499% | 2.7741% | 2.7693% | 1.9856% |
| Euro | 23.0415% | 22.9090% | 22.9755% | 24.6390% |
| Mexican Peso | 2.1777% | 2.1556% | 2.1515% | 2.7978% |
| Ruble | 3.0541% | 3.0463% | 3.0729% | 2.5271% |
| Rupee | 3.7484% | 3.7469% | 3.7321% | 3.7004% |
| Saudi Riyal | 1.7397% | 1.7852% | 1.7588% | 7.2202% |
| Shekel | 3.7825% | 3.7840% | 3.7960% | 0.4513% |
| Swiss Franc | 4.6307% | 4.6286% | 4.5988% | 3.9711% |
| UK Pound | 3.5472% | 3.5782% | 3.5839% | 1.9856% |
| US Dollar | 37.3115% | 37.2765% | 37.3927% | 37.5451% |
| Yen | 3.0622% | 3.0421% | 3.0470% | 5.5054% |
| Yuan | 4.2099% | 4.2192% | 4.1958% | 3.5199% |

### receiving_currency

| Value | Train | Validation | Test | Stress |
| --- | ---: | ---: | ---: | ---: |
| Australian Dollar | 2.7244% | 2.7386% | 2.7259% | 3.1588% |
| Bitcoin | 2.9043% | 3.0113% | 2.8649% | 0.0000% |
| Brazil Real | 1.4025% | 1.4099% | 1.4314% | 1.3538% |
| Canadian Dollar | 2.7739% | 2.8093% | 2.7916% | 2.3466% |
| Euro | 23.1115% | 22.9916% | 23.0507% | 24.7292% |
| Mexican Peso | 2.1938% | 2.1784% | 2.1669% | 2.3466% |
| Ruble | 3.0946% | 3.0982% | 3.1149% | 2.7978% |
| Rupee | 3.7833% | 3.7917% | 3.7668% | 3.4296% |
| Saudi Riyal | 1.7576% | 1.8055% | 1.7795% | 7.3105% |
| Shekel | 3.8347% | 3.8461% | 3.8550% | 0.5415% |
| Swiss Franc | 4.6866% | 4.6978% | 4.6588% | 5.8664% |
| UK Pound | 3.5570% | 3.5939% | 3.5899% | 1.7148% |
| US Dollar | 37.0171% | 36.9037% | 37.0867% | 35.1083% |
| Yen | 3.0826% | 3.0691% | 3.0670% | 6.4982% |
| Yuan | 4.0760% | 4.0549% | 4.0499% | 2.7978% |

### Historical activity

| Split | Rows | Sender cold | Receiver cold | Median sender count | Median sender currency count | Median inactivity seconds | Median history age seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 3,248,921 | 13.3762% | 11.5591% | 13.00 | 8.00 | 1,020.00 | 165,300.00 |
| validation | 965,524 | 0.0948% | 0.0240% | 49.00 | 33.00 | 960.00 | 598,620.00 |
| test | 862,792 | 0.1032% | 0.0218% | 57.00 | 37.00 | 1,380.00 | 737,700.00 |
| stress | 1,108 | 0.5415% | 0.9025% | 27.00 | 2.00 | 64,500.00 | 987,750.00 |

### Paid amounts within currency

Cells show median / p99 in the named currency; never compare different currency units. Quantiles for groups with fewer than 20 rows are suppressed in this public report.

| Currency | Train | Validation | Test | Stress |
| --- | --- | --- | --- | --- |
| Australian Dollar | 1434.600000000 / 4512689.610000000 | 1155.700000000 / 2044382.080000000 | 1078.000000000 / 2136507.450000000 | 16065.380000000 / 1382342.990000000 |
| Bitcoin | 0.075285000 / 274.109443000 | 0.061899000 / 127.629393000 | 0.061857000 / 163.577826000 | n<20; suppressed |
| Brazil Real | 5634.130000000 / 27125680.240000000 | 4968.210000000 / 15817923.800000000 | 4785.590000000 / 16088803.510000000 | n<20; suppressed |
| Canadian Dollar | 1244.580000000 / 4659759.150000000 | 1046.250000000 / 2570061.060000000 | 961.380000000 / 2908778.300000000 | 7589.030000000 / 22310.520000000 |
| Euro | 817.650000000 / 3002462.310000000 | 660.380000000 / 1539747.660000000 | 624.570000000 / 1732115.130000000 | 7685.940000000 / 10619805.810000000 |
| Mexican Peso | 20355.150000000 / 63858181.640000000 | 16902.250000000 / 32294393.320000000 | 16035.040000000 / 36202377.200000000 | 282879.120000000 / 271361922.670000000 |
| Ruble | 74905.310000000 / 363242254.420000000 | 64866.330000000 / 247503248.810000000 | 61128.490000000 / 255342482.230000000 | 498379.220000000 / 1413192.280000000 |
| Rupee | 70266.910000000 / 321064766.280000000 | 58427.580000000 / 230197504.260000000 | 58088.530000000 / 237575609.830000000 | 1135582.760000000 / 886180041.840000000 |
| Saudi Riyal | 3710.600000000 / 10716147.870000000 | 3215.010000000 / 7089827.310000000 | 3068.360000000 / 6793808.090000000 | 34822.310000000 / 87724168.280000000 |
| Shekel | 3370.910000000 / 10689889.000000000 | 2831.970000000 / 5471594.430000000 | 2608.620000000 / 6303275.040000000 | n<20; suppressed |
| Swiss Franc | 865.780000000 / 3922626.490000000 | 702.820000000 / 2121248.830000000 | 641.640000000 / 2291273.030000000 | 7235.060000000 / 10075910.880000000 |
| UK Pound | 749.560000000 / 3113607.130000000 | 628.300000000 / 2014858.620000000 | 586.690000000 / 2014858.620000000 | 11095.880000000 / 9476632.740000000 |
| US Dollar | 986.540000000 / 3692638.310000000 | 810.080000000 / 1964491.660000000 | 762.030000000 / 2313124.840000000 | 10069.830000000 / 12240548.620000000 |
| Yen | 103453.190000000 / 435308712.420000000 | 90762.170000000 / 239520081.020000000 | 80679.870000000 / 280999955.750000000 | 1119152.570000000 / 243308041.200000000 |
| Yuan | 6578.280000000 / 25034138.490000000 | 5442.220000000 / 12419610.560000000 | 5243.820000000 / 14851693.000000000 | 75367.450000000 / 64020841.070000000 |

## Provenance and limitations

Freeze recorded `2026-10-14T18:35:45.223509+00:00`; digest `4a727df4fcb728bea955f2c4ff206810b52ebf64b564a14f89c3507378c25e83`.
Evaluation completed `2026-10-14T18:39:50.103622+00:00` in 33.621 seconds.
Both prediction files were generated before either label export. Access records:

| Split | Freeze verified (UTC) | Label export completed (UTC) | Rows |
| --- | --- | --- | ---: |
| test | 2026-10-14T18:39:35.042440+00:00 | 2026-10-14T18:39:38.896654+00:00 | 862,792 |
| stress | 2026-10-14T18:39:47.019417+00:00 | 2026-10-14T18:39:48.965068+00:00 | 1,108 |

Original hashes and feature checksum remained unchanged. Predictions contain
source row and five scores only; temporary labels were removed. The constant
baseline has one complete score tie, so its ranking-budget outcome is arbitrary.
ACH and rules also have score ties; AP groups them instead of breaking ties.

Neither probability-scale model was calibrated. Predictions are review suggestions,
not proof of wrongdoing. Synthetic shortcuts, label quality, immediate attribute
availability, left-censored history and repeated development inspection limit
generalization. Small subgroup estimates and stress ranking budgets are unstable.
No significance claims or threshold guarantees are made.

See [the frozen contract](ml_holdout_evaluation.md) and
[interpretation and verification](ml_holdout_verification.md).
