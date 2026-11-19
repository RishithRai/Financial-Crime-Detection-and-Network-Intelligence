# interpretable rules baseline

`rules-v1` scores existing `historical-v1` transactions. It does not change
features, source records, labels, or PostgreSQL configuration. No ML model is
trained. A suspicious alert means **review suggested**, never proof of laundering.
The 0–10 score is a sum of heuristic points, not a calibrated probability.

## Rule design

Rules and weights were specified using domain reasoning before validation-label
access. Absolute reference values come only from September 1–6 training features.
No training labels are needed. The scorer does not inspect account identifiers,
source-row IDs, split names, labels, patterns, or future records. It consumes
current amounts/currencies and the existing strictly-prior account histories.

The following four rules are applied separately to sender and receiver:

| Rule family | Exact trigger | Points per endpoint |
| --- | --- | --- |
| Amount spike | At least 5 prior direction/currency observations; positive historical sum; current amount strictly greater than 10× that historical mean AND the training currency p95 | 2 |
| Frequency surge | Observed history age at least 24h; at least 5 transactions in the prior hour; `count_1h × 23 > 5 × (count_24h − count_1h)` | 1 |
| High recent activity | Observed history age at least 24h; prior 24h count strictly greater than `max(20, training endpoint p99 count_24h)` | 1 |
| Direction change | Observed history age at least 24h; at least 10 prior transactions in the opposite direction and at most 1 in the current direction; current amount strictly above training currency p95 | 1 |

Currency p95 references require at least 1,000 training observations for that
currency and direction. High-activity p99 references use training rows with at
least 24h of observed account history. Sender money uses amount paid and payment
currency; receiver money uses amount received and receiving currency. There are
no pooled currency amounts, FX conversions, or fitted encodings. Decimal
comparisons remain exact for the validated artifact's monetary range.

These are plausible anomaly indicators, not universal laundering signatures:
large transfers, busy merchant accounts, payment bursts, and changes in payment
direction can all be legitimate. Historical means are sensitive to old outliers.
Overlapping sender/receiver rules can count related evidence twice; weights are
transparent heuristics, not independent likelihoods. No self-transfer, currency,
or payment format alone is treated as proof of suspicion by the main detector.

## Cold starts and history limits

With fewer than five matching direction/currency observations, amount spikes
are suppressed. A missing/unsupported training currency also suppresses amount
and direction rules; frequency/activity rules can still operate when enough
account history exists. Prediction files explicitly flag limited currency
history and unsupported currencies. Missing age suppresses the time-maturity
rules. Zero historical sums do not trigger division-by-zero amount spikes.

A new sender can still receive an alert because of well-supported receiver
behavior, or vice versa. No fabricated historical mean is substituted for an
unknown one. Twenty-four hours of observed history is a minimum safeguard, not
proof of a complete real-world account history. The dataset remains left-censored.
All original feature limitations remain: immediate arrival is assumed, receiving
attributes must be available at scoring time, and same-timestamp peers are absent
from historical calculations.

## Score explanations and sanity baselines

Every prediction includes all eight Boolean triggers and an ordered list of
reason codes, such as `SENDER_AMOUNT_SPIKE` or `RECEIVER_FREQUENCY_SURGE`.
`rules.json` maps each code to its human-readable explanation and point weight.
`suspicious_alert` means the summed score meets the finalized validation threshold.
An empty reason list means no rule triggered, not proof of legitimate activity.

Three fixed sanity baselines accompany the main score:

- **ACH-only:** score 1 for ACH, 0 otherwise; its alert policy flags every ACH row.
  This intentionally tests a known synthetic-dataset shortcut. ACH is not a
  component of the main score.
- **Currency-tail-only:** score 1 when amount paid strictly exceeds its supported
  training payment-currency p99.5, otherwise 0. This tests a simple amount heuristic.
- **Constant/no alerts:** score 0 everywhere and no alerts. Its Average Precision
  equals positive prevalence; its tied ranking illustrates chance-level ordering.

These baselines are not constrained to the main detector's alert budget. Compare
ranking metrics and their reported alert volumes, rather than comparing recall
alone across different volumes.

## Calibration, finalization, and holdout access

The approved splits remain September 1–6 train, 7–8 validation, 9–10 primary test,
and 11–18 separate stress. Every boundary is half-open as defined in EDA.

1. Verify the immutable feature checksum. Profile **train only** for currency and
   activity references. Score validation without any label input.
2. Fetch **validation labels only** from a read-only PostgreSQL snapshot. Join by
   source identity after scoring, verifying one-to-one coverage.
3. Select among integer thresholds 1 through 11. Threshold 11 permits a no-alert
   result. Maximize validation F2 subject to an alert rate at most **1%**; equal F2
   chooses the higher threshold. Whole score tiers are included; ties never get
   split to fit the operating cap.
4. Persist finalized definitions, training references, constants, weights,
   selected threshold, all threshold candidates, feature/code/dependency hashes,
   and finalization time. Publish validation predictions and calibration metrics.
5. Only then allow the separate evaluation command to fetch test/stress labels.
   It verifies frozen hashes and evaluates both splits without parameter changes.
   Recalibration into the same directory and repeat holdout evaluation are refused.

The 1% cap and recall-weighted F2 are declared portfolio operating assumptions,
not a known investigator capacity or business loss model. Review them before
operational deployment. Validation metrics at the chosen threshold are selected
on that same validation set and therefore optimistic as deployment estimates.

Training rows are used for reference statistics, not exported as predictions:
full-training references would be retrospective for early training transactions.
Validation alerts are calibration diagnostics; the completed operating policy
would become available after September 8. Test and stress predictions use the
already finalized policy. Earlier unlabeled observation history rolls forward
across splits, as specified by historical-v1; no parameters are refitted there.

Earlier EDA already examined aggregate test/stress labels. These are development
holdouts, not pristine externally blinded tests. Within rules-baseline stage, no holdout
labels are fetched until finalization, and no holdout-driven iteration is made.

## Evaluation definitions

Average Precision uses descending **score groups**:
`AP = sum((new positives / all positives) × cumulative precision)`.
This is non-interpolated AP, not trapezoidal PR-AUC. Equal scores stay in one group,
so AP cannot be inflated by favorable ordering inside ties. With no positives,
AP and recall are undefined and recorded as JSON null rather than fabricated zeros.

Precision@K and Recall@K are measured at K = 100, 1,000, and 10,000. K is capped at
the split size, and both requested and effective K are reported. Within equal
scores, ordering uses SHA-256 of dataset fingerprint, source row, and a fixed
versioned salt; source row breaks any residual hash collision. Labels and event
chronology do not choose the order. This is one reproducible arbitrary ordering,
not evidence that the detector distinguishes rows within a tied score group.
Source identity is used only to resolve budget ties, not as a risk predictor.

Precision@K can include zero-score rows and does not equal the operating alert
policy. Also report actual operating alert counts, true/false positives, precision,
recall, alert rate, positive prevalence, score-tier counts, and rule trigger counts.
Zero alerts yield undefined precision. No test or stress metrics select a rule,
weight, threshold, or tie seed. Stress results are reported separately because
its prevalence and transaction composition differ sharply from the primary period.

## Commands and artifacts

Use the locked uv environment and local `.env`. See [reproduction](reproducibility.md)
for setup and historical environment requirements.

```sh
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked --env-file .env python -m mulegraph.rules_baseline \
  --phase calibrate --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env python -m mulegraph.rules_baseline \
  --phase evaluate --features-dir "$FEATURE_DIR"
```

Default output: ignored `data/rules/rules-v1/`:

- `rules.json`: finalized, human-reviewable definition and threshold policy.
- `calibration.json`: validation metrics, threshold-selection evidence via the
  definition, label-access timestamp/hash, and prediction hash.
- `validation_predictions.parquet`: scores, flags, reasons, alert decision,
  version/hash, source identity, event time, and split; no labels.
- `holdout/evaluation.json`: separate test and stress metrics and access evidence.
- `holdout/test_predictions.parquet`, `holdout/stress_predictions.parquet`:
  independently scored holdout predictions, with the same frozen rule hash.

Do not rerun these commands to tune on already inspected holdouts. A future
research version must explicitly acknowledge holdout reuse and seek an untouched
evaluation dataset. Artifact hashes detect accidental changes, not adversarial
editing of both files and their checksum records.

Arrow and DuckDB process columnar data without loading all rows into Pandas.
DuckDB uses a 256 MiB buffer limit and one worker; PostgreSQL label exports use
bounded batches. Evaluation targets exist only in disposable local files during
evaluation and are removed afterward. Prediction files contain no row-level
labels. Source features are never rewritten.

```sh
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Implementation: `rules.py`, `rule_metrics.py`, and `rules_baseline.py` under
`src/mulegraph/`. Read [the measured report](rules_report.md) for results and
verification. Future/peer leakage tests from historical-v1 remain part of the
suite, alongside rule-input isolation, training-only profiling, SQL/reference
agreement, deterministic scoring, metric arithmetic, and frozen-stage tests.

Regenerate the aggregate report from saved results without scoring or reopening
holdout labels:

```sh
uv run --locked python -m mulegraph.rules_report
```

The report also saves an exact aggregate-only copy of the finalized definition
at `docs/rules_definition_v1.json` for portfolio review. The generated report does
not itself run tests; actual execution evidence is maintained separately in
[the verification log](rules_verification.md).
