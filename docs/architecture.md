# MuleGraph architecture and data contracts

MuleGraph is an offline, retrospective system. The [README diagram](../README.md#architecture)
shows the data flow; there is no live inference, streaming alert service or GNN.

| Boundary | Responsibilities and contract |
| --- | --- |
| CSV → PostgreSQL | Positional parsing handles repeated Account headers. `(dataset, source_row)` identifies every transaction; `(bank, account)` identifies nodes. Streaming COPY, exact NUMERIC, reconciliation and completion commit atomically. Duplicate content is preserved. |
| Core versus labels | Core holds transaction attributes; separate labels schema holds targets. Labels enter training/evaluation separately, never graph construction, predictor matrices, saved scores or analyst responses. Schema separation is not a hardened least-privilege application role. |
| Core → historical-v1 | Read-only repeatable-read endpoint streams, bounded batches and account-local state. Timestamp peers emit before updates. Parquet has exact decimals, source/time/split provenance and hashes. |
| Historical-v1 → learning | Explicit allowlists exclude identifiers, times, split and targets. Train-only vocabularies/scales, chronological split and predeclared configurations. Training labels are legitimate targets, not feature inputs. |
| Frozen models → scores | Versioned models/preprocessors, validation-selected thresholds, label-free source/score predictions, integrity checks and separate aggregate evaluation. The application reads original stabilized `history_none`, never the 7C candidate. |
| Historical-v1 → pair graph experiment | Separate DuckDB timestamp-group windows compute prior directed/reverse counts and recencies. Four inputs plus two missingness indicators extend the control's 84 columns to 90. All rows receive features; only train/validation enter the two-fit experiment. |
| Core + saved scores → investigation | Indexed bounded PostgreSQL incident expansion builds a NetworkX MultiDiGraph. Ordered paths require increasing time and compatible handoff currency. Scores prioritize, never determine pattern membership. |
| Findings → cases/annotations | Deterministic shared-evidence groups retain original witnesses. Distinct incident rows determine account maxima/coverage. Separate evidence annotations report exact amount differences and local timing without changing grouping or scores. |
| Model/features → explanation | Bounded native TreeSHAP uses original preprocessing; raw-margin additivity and saved-score agreement must pass. Training-period rows stay unscored. |
| Services → FastAPI → React | GET-only local API delegates to existing services. Pagination, concurrency, SQL/search/evidence caps, sanitized errors and stale-result clearing. Cytoscape groups visual arrows but preserves every source reference; timeline selections show exact evidence. |

## Temporal and identity rules

Train September 1–6, validation 7–8, primary test 9–10 and stress 11–18, 2022.
All source timestamps are timezone-naive. Historical features and investigations
use strictly earlier events; windows are `[start, cutoff)`. Earlier unlabeled
observations roll forward across splits, while fitted preprocessing never does.
Focal transactions appear separately. Same-time ordering by row ID is not allowed
to imply causality or add history. Actual arrival/availability times are absent,
so event-time correctness does not establish production point-in-time availability.

Cross-bank account strings are distinct. Parallel, repeated, reverse and self
transfers retain source identity. Monetary sums/comparisons stay currency-specific.
Pair topology counts span currencies but perform no monetary aggregation. Equal
amounts or chronological connectivity do not identify the same funds.

## Engineering tradeoffs

- PostgreSQL owns source integrity; Arrow and DuckDB enable streaming/disk-backed
  model assembly instead of loading the full network into Python.
- Incremental account state and pair SQL windows avoid millions of NetworkX snapshots.
  NetworkX serves bounded investigations, not full-dataset predictive snapshots.
- Saved predictions ensure demo consistency and leave explicit training-score gaps.
  They are retrospective, not scores demonstrably available at each historical time.
- Hashes, immutable versions and failed-attempt guards favor traceability over easy
  reruns. They are reproducibility controls, not adversarial audit signatures.
- Resource caps reject whole requests instead of silently sampling evidence. Per-query
  timeouts and process-local concurrency limits are not distributed service guarantees.
- React adds graph interaction; the thin Python adapter preserves tested services.
  Streamlit remains available. No UI claims authentication or operational case status.

Detailed contracts: [features](historical_features.md), [graph](transaction_graph.md),
[cases](case_intelligence.md), [API/UI](analyst_application.md),
[evidence annotations](evidence_quality.md), [graph experiment](graph_prediction.md).
