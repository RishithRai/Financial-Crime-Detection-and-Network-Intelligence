# measured rules baseline results

The baseline completed calibration and one frozen holdout evaluation. It is weak on the primary distribution: treat it as a transparent benchmark, not a deployable detector or evidence of criminal conduct. Source data and historical-v1 features remain unchanged; no ML model was trained.

## Validation outcome

The selected alert threshold is **score ≥ 2**. It flags 6,912 validation transactions (0.7159%), including 21 positive labels and 6,891 negative labels. Precision is 0.3038%; recall is 2.0270%. AP is 0.00113290, versus the prevalence baseline 0.00107299. This is only 1.056× baseline AP.

ACH-only has substantially higher primary-period AP, but flags far more transactions. It exposes a synthetic-dataset association rather than establishing ACH as inherently suspicious. The main rules intentionally do not include payment format. Absolute stress AP must be judged against its much higher prevalence, not compared directly with primary AP.

## Population and baselines

| Split | Rows | Positive labels | Prevalence / constant AP |
| --- | --- | --- | --- |
| validation | 965,524 | 1036 | 0.00107299 |
| test | 862,792 | 956 | 0.00110803 |
| stress | 1,108 | 655 | 0.59115523 |

AP below is a fraction in [0,1]. Precision/recall and alert rates are percentages. Undefined precision means no alerts. Baseline alert policies are fixed independently of the main detector's validation budget.

| Split | Method | AP | Alerts | True alerts | False alerts | Alert rate | Precision | Recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| validation | Main rules | 0.00113290 | 6,912 | 21 | 6,891 | 0.7159% | 0.3038% | 2.0270% |
| validation | ACH only | 0.00669108 | 116,910 | 890 | 116,020 | 12.1085% | 0.7613% | 85.9073% |
| validation | Currency tail | 0.00111207 | 3,531 | 14 | 3,517 | 0.3657% | 0.3965% | 1.3514% |
| validation | Constant/no alerts | 0.00107299 | 0 | 0 | 0 | 0.0000% | undefined | 0.0000% |
| test | Main rules | 0.00117018 | 9,787 | 15 | 9,772 | 1.1343% | 0.1533% | 1.5690% |
| test | ACH only | 0.00624542 | 119,195 | 834 | 118,361 | 13.8150% | 0.6997% | 87.2385% |
| test | Currency tail | 0.00115423 | 3,284 | 14 | 3,270 | 0.3806% | 0.4263% | 1.4644% |
| test | Constant/no alerts | 0.00110803 | 0 | 0 | 0 | 0.0000% | undefined | 0.0000% |
| stress | Main rules | 0.59489800 | 21 | 14 | 7 | 1.8953% | 66.6667% | 2.1374% |
| stress | ACH only | 0.59115523 | 1,108 | 655 | 453 | 100.0000% | 59.1155% | 100.0000% |
| stress | Currency tail | 0.59170882 | 21 | 13 | 8 | 1.8953% | 61.9048% | 1.9847% |
| stress | Constant/no alerts | 0.59115523 | 0 | 0 | 0 | 0.0000% | undefined | 0.0000% |

The validation 1% alert-rate cap is a selection constraint, not a guarantee on new periods. The frozen threshold exceeds that rate on primary test and stress; it was not adjusted after observing either result. Stress is entirely ACH, so the ACH score there has exactly the same AP as a constant score. No split results are pooled.

## Precision@K and Recall@K

Ranking uses descending score and a fixed label-free SHA-256 tie order. AP groups entire score ties; the @K metrics use one reproducible arbitrary order inside them. Strong ties limit conclusions from small K. K is capped at split size, and zero-score transactions may enter a top-K budget.

| Split | Method | Requested K | Effective K | Positives in K | Precision@K | Recall@K |
| --- | --- | --- | --- | --- | --- | --- |
| validation | Main rules | 100 | 100 | 0 | 0.0000% | 0.0000% |
| validation | Main rules | 1000 | 1000 | 3 | 0.3000% | 0.2896% |
| validation | Main rules | 10000 | 10000 | 23 | 0.2300% | 2.2201% |
| validation | ACH only | 100 | 100 | 0 | 0.0000% | 0.0000% |
| validation | ACH only | 1000 | 1000 | 7 | 0.7000% | 0.6757% |
| validation | ACH only | 10000 | 10000 | 77 | 0.7700% | 7.4324% |
| validation | Currency tail | 100 | 100 | 1 | 1.0000% | 0.0965% |
| validation | Currency tail | 1000 | 1000 | 4 | 0.4000% | 0.3861% |
| validation | Currency tail | 10000 | 10000 | 20 | 0.2000% | 1.9305% |
| validation | Constant/no alerts | 100 | 100 | 0 | 0.0000% | 0.0000% |
| validation | Constant/no alerts | 1000 | 1000 | 0 | 0.0000% | 0.0000% |
| validation | Constant/no alerts | 10000 | 10000 | 7 | 0.0700% | 0.6757% |
| test | Main rules | 100 | 100 | 0 | 0.0000% | 0.0000% |
| test | Main rules | 1000 | 1000 | 0 | 0.0000% | 0.0000% |
| test | Main rules | 10000 | 10000 | 15 | 0.1500% | 1.5690% |
| test | ACH only | 100 | 100 | 0 | 0.0000% | 0.0000% |
| test | ACH only | 1000 | 1000 | 4 | 0.4000% | 0.4184% |
| test | ACH only | 10000 | 10000 | 61 | 0.6100% | 6.3808% |
| test | Currency tail | 100 | 100 | 0 | 0.0000% | 0.0000% |
| test | Currency tail | 1000 | 1000 | 4 | 0.4000% | 0.4184% |
| test | Currency tail | 10000 | 10000 | 17 | 0.1700% | 1.7782% |
| test | Constant/no alerts | 100 | 100 | 0 | 0.0000% | 0.0000% |
| test | Constant/no alerts | 1000 | 1000 | 0 | 0.0000% | 0.0000% |
| test | Constant/no alerts | 10000 | 10000 | 6 | 0.0600% | 0.6276% |
| stress | Main rules | 100 | 100 | 59 | 59.0000% | 9.0076% |
| stress | Main rules | 1000 | 1000 | 600 | 60.0000% | 91.6031% |
| stress | Main rules | 10000 | 1108 | 655 | 59.1155% | 100.0000% |
| stress | ACH only | 100 | 100 | 61 | 61.0000% | 9.3130% |
| stress | ACH only | 1000 | 1000 | 599 | 59.9000% | 91.4504% |
| stress | ACH only | 10000 | 1108 | 655 | 59.1155% | 100.0000% |
| stress | Currency tail | 100 | 100 | 58 | 58.0000% | 8.8550% |
| stress | Currency tail | 1000 | 1000 | 599 | 59.9000% | 91.4504% |
| stress | Currency tail | 10000 | 1108 | 655 | 59.1155% | 100.0000% |
| stress | Constant/no alerts | 100 | 100 | 61 | 61.0000% | 9.3130% |
| stress | Constant/no alerts | 1000 | 1000 | 599 | 59.9000% | 91.4504% |
| stress | Constant/no alerts | 10000 | 1108 | 655 | 59.1155% | 100.0000% |

## Rule investigation on validation

These diagnostics describe individual triggers, not independent evidence and not a second round of parameter selection. Amount-spike rules have two points; all other rules have one. Reasons may overlap within an alert.

| Reason code | Triggers | Positive labels | Trigger precision |
| --- | --- | --- | --- |
| RECEIVER_AMOUNT_SPIKE | 145 | 14 | 9.6552% |
| RECEIVER_DIRECTION_CHANGE | 23 | 0 | 0.0000% |
| RECEIVER_FREQUENCY_SURGE | 14405 | 25 | 0.1736% |
| RECEIVER_HIGH_ACTIVITY | 7365 | 12 | 0.1629% |
| SENDER_AMOUNT_SPIKE | 2195 | 2 | 0.0911% |
| SENDER_DIRECTION_CHANGE | 20 | 3 | 15.0000% |
| SENDER_FREQUENCY_SURGE | 11197 | 1 | 0.0089% |
| SENDER_HIGH_ACTIVITY | 0 | 0 | undefined |

Receiver amount spikes and sender direction changes concentrate more validation positives than several other individual triggers, but their sample sizes are small. No weights were changed after seeing this. Frequency bursts and large transfers often flag legitimate-looking synthetic activity. The full score misses most positive labels.

| Endpoint | Mature training rows | High-activity cutoff (> threshold) |
| --- | --- | --- |
| receiver | 2020587 | 21 |
| sender | 2005405 | 22763 |

The sender reference is especially high and that rule never triggers in validation. These quantiles are transaction-weighted: busy accounts contribute many observations. This is a limitation of this simple reference design, preserved in the frozen baseline rather than corrected on holdouts.

## Cold-start and currency coverage

| Split | Endpoint | Fewer than 5 currency observations | Unsupported currency |
| --- | --- | --- | --- |
| validation | sender | 21162 | 0 |
| validation | receiver | 12233 | 0 |
| test | sender | 105642 | 0 |
| test | receiver | 63356 | 0 |
| stress | sender | 651 | 0 |
| stress | receiver | 569 | 0 |

Limited currency history suppresses the corresponding amount-spike rule, not every possible alert. Other endpoint evidence may remain available. Currency references and all constants are retained in [the frozen aggregate definition](rules_definition_v1.json); there are no currency conversions or future-derived imputations.

## Threshold selection audit

Only validation labels selected this integer operating threshold. The predeclared objective was maximum F2 under a 1% alert-rate cap, with ties favoring higher thresholds. A no-alert result was allowed.

| Threshold | Alerts | Positive alerts | F2 | Within cap |
| --- | --- | --- | --- | --- |
| 1 | 30348 | 50 | 0.00724806 | False |
| 2 | 6912 | 21 | 0.00949711 | True |
| 3 | 392 | 2 | 0.00220459 | True |
| 4 | 35 | 0 | 0.00000000 | True |
| 5 | 3 | 0 | 0.00000000 | True |
| 6 | 0 | 0 | 0.00000000 | True |
| 7 | 0 | 0 | 0.00000000 | True |
| 8 | 0 | 0 | 0.00000000 | True |
| 9 | 0 | 0 | 0.00000000 | True |
| 10 | 0 | 0 | 0.00000000 | True |
| 11 | 0 | 0 | 0.00000000 | True |

Finalized at **2026-10-14T05:29:09.231358+00:00**. Frozen rule file SHA-256: `fce28168d66d3a47bea0b2d63a681d4e97b4b333c02f75b34becef5f724f8b28`. Holdout evaluation records the same digest.

| Labels accessed | Rows | Retrieval completed (UTC) |
| --- | --- | --- |
| validation | 965524 | 2026-10-14T05:29:03.384756+00:00 |
| test | 862792 | 2026-10-14T05:31:07.256408+00:00 |
| stress | 1108 | 2026-10-14T05:31:15.551708+00:00 |

Validation export completion precedes finalization. Test and stress export completion occurs afterward. The staged integration test also checks access sequence and rejects evaluation without finalized definitions, repeated holdout evaluation, and recalibration into an existing directory.

## Execution and verification

Calibration completed in 18.681 seconds; frozen test/stress evaluation completed in 15.011 seconds. These are local execution measurements, not benchmarks. Training uses 3,248,921 reference rows; predictions cover all 1,829,424 validation/test/stress rows. Training predictions are intentionally absent because full-training references would be retrospective for early rows.

Actual test, checksum, and persisted-prediction verification results are recorded in [the verification log](rules_verification.md). Rendering this report does not rerun tests, score transactions, or access labels.

Prediction files and definitions live under ignored `data/rules/rules-v1/`. No row-level labels are stored in predictions; disposable label exports were removed. See [implementation and commands](rules_baseline.md).

## Limitations and review decisions

No execution blocker remains, but the low precision and recall make this unsuitable as a standalone operational detector. Review the illustrative 1% budget, F2 objective, and investigator capacity before deployment. Rules and weights are heuristic and correlated; the score is not a probability. Binary labels come from synthetic generation, and a trigger is not proof of wrongdoing.

The immediate-arrival/current-attribute assumptions and left-censored history remain unchanged. Validation metrics are selected on validation; prior EDA already inspected aggregate holdout labels, so these are development holdouts. Stress prevalence and composition are exceptional. Transactions and accounts are dependent, and no independent-event confidence intervals are claimed. No holdout-driven rule, weight, threshold, or tie-seed changes were made. Any future iteration needs an explicit new version and an honest evaluation protocol.
