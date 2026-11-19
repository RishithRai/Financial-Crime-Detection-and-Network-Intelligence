# measured graph-feature comparison

Exploratory September 7–8 validation only. No new test/stress predictions or
label evaluation. The application retains frozen `lightgbm-stable-v1/history_none`.

| Model | AP | ROC-AUC | P@1% | R@1% | Budget TP |
| --- | ---: | ---: | ---: | ---: | ---: |
| history_control | 0.56053649 | 0.98298160 | 8.5344% | 79.5367% | 824 |
| history_plus_graph | 0.62812458 | 0.98770020 | 8.9073% | 83.0116% | 860 |

Validation: 965,524 rows, 1,036 positives, 0.1073% prevalence; budget 9,655 alerts.
AP change: **+0.06758809**. Budget true-positive change: **+36**.
The freshly fitted control exactly reproduced every frozen validation score and metric.

## Computation and numerical checks

| Fit | Encoded columns | Fit seconds | Train/validation diagnostic seconds | Matrix seconds | Stable |
| --- | ---: | ---: | ---: | ---: | --- |
| history_control | 84 | 110.827 | 43.351 | 37.104 | True |
| history_plus_graph | 90 | 114.216 | 45.396 | 41.080 | True |

Shared training-only preprocessing: 42.020 seconds. Complete experiment: 480.230 seconds; process peak RSS 987.86 MiB.
Graph build: 5,078,345 rows in 23.651 seconds; process peak RSS 1056.22 MiB; Parquet 19,361,592 bytes.
These are local wall times, not production benchmarks. Diagnostic prediction time
includes both train and validation raw-margin/probability passes; matrix work includes
disk-backed retrieval and transformation. OS/native memory can exceed DuckDB limits.

| Fit | Validation raw range | Exact endpoints | Top-score tie | Post-initial leaf max |
| --- | --- | ---: | ---: | ---: |
| history_control | [-11.8851, 3.6581] | 0 | 1 | 0.06000000 |
| history_plus_graph | [-12.1014, 3.5117] | 0 | 1 | 0.06000000 |

All full-validation reload checks passed in the training runner. Training loss
traces and fit warnings are retained in ignored metadata; no stopping used validation.

Saved validation thresholds: control `0.011489041059356882` (9,655 alerts), augmented `0.010017885759686455` (9,654 alerts). Complete score tiers can yield fewer alerts
than the exact ranking budget. The original operating threshold is unchanged.

## Feature coverage (unlabeled)

| Split | Rows | Prior forward interaction | Prior reverse interaction | Prior activity both directions |
| --- | ---: | ---: | ---: | ---: |
| stress | 1108 | 381 | 35 | 28 |
| test | 862792 | 826200 | 1659 | 394 |
| train | 3248921 | 2296105 | 1831 | 399 |
| validation | 965524 | 927445 | 1317 | 322 |

Test/stress entries above are feature coverage only, not model predictions or label evaluation.

## Freeze and access evidence

Execution freeze: `2026-10-14T21:42:50.908782+00:00`; protects 73 original files.
Declaration SHA-256: `3720b9127f36acaa58ff62c8cff1bae91e14a6aafe0fd5490a8a19cf02cd1fa4`.
Graph file SHA-256: `ea5d698d8c8cea576b515051ca6e24ec2c092dd365c6af85836f1b963d764e21`.
- train label export completed `2026-10-14T21:43:10.690023+00:00`; 3,248,921 rows.
- validation label export completed `2026-10-14T21:43:21.902874+00:00`; 965,524 rows.

Only the predeclared control and augmented fits ran. No original model or threshold
was replaced. Labels and temporary matrices were removed; predictions contain source
reference and review score only. Timestamps/hashes are reproducibility evidence.

## Interpretation

The graph group meets the predeclared directional criterion: higher AP with no
loss of 1% budget recall and stable numerical behavior. This suggests additional
predictive information on this reused validation period, not statistical significance
or improved performance on an untouched population. Retain the original selected
model pending a separately predeclared frozen development-holdout comparison.

The graph features summarize pair interaction topology, not verified money flow.
Repeated validation use, synthetic generator associations, observation-start censoring
and assumed attribute availability limit interpretation. Reciprocity is rare in this
dataset. No calibrated probability or causal explanation is established. This is a
group-level ablation, not an attribution of gain to any single added predictor.

See [contract and reproduction](graph_prediction.md) and
[verification and recovery notes](graph_prediction_verification.md).
