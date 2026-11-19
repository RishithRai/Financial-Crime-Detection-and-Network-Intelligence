# historical graph features and controlled comparison

The [predeclared plan](graph_prediction_plan_v1.json) evaluates four pair-specific
graph statistics that augment the existing endpoint activity features.
The two fits use the exact stabilized, unweighted LightGBM configuration; this is
an exploratory ablation on the already-used validation period, not a search or
new final holdout evaluation. The application's selected model remains unchanged.

## Feature contract

| Feature | Definition at transaction time T |
| --- | --- |
| `pair_prior_count` | Number of observed sender → receiver transactions strictly before T |
| `reverse_prior_count` | Number of observed receiver → sender transactions strictly before T; zero for self-transfers |
| `pair_seconds_since_last` | Seconds since the latest strictly earlier sender → receiver transaction; null if none |
| `reverse_seconds_since_last` | Seconds since the latest strictly earlier reverse transaction; null if none or self-transfer |

Positive prior counts in both directions represent historical reciprocal activity.
A separate reciprocity Boolean would duplicate those counts, so it is reported as
coverage rather than added as a fifth predictor. Pair counts and directional
recencies differ from existing account-wide counts and unique counterparties.
There are six new encoded columns: four transformed numerics and two explicit
missing-recency indicators.

Account identity is `(normalized bank, unchanged account string)`. The input
manifest scopes every row to one verified dataset. Source-row duplicates are
preserved as separate transactions; identical timestamp peers all see the same
prior state. Self-transfers have their own directed history but cannot manufacture
reverse interaction. Zero-amount transfers remain structural edges. Counts cover
all currencies and do not add, compare or convert monetary amounts. The feature
represents interaction topology, not proof of same-funds movement or laundering.
History is left-censored at the dataset start; unseen pairs have zero counts and
null recencies. Event time is assumed to equal availability, as in historical-v1.

## Pipeline and preservation

`graph_features.py` reads only source reference, time, split and composite endpoints
from the checksum-verified historical-v1 file. It never reads labels, pattern
annotations, entity metadata or future outcomes. Using existing immutable core
columns avoids another database-wide export and preserves the same source universe.

DuckDB groups by an unordered pair of **struct** endpoint identities and timestamp,
counts both directions, and computes cumulative history over preceding timestamp
groups only. It then joins those values back to every original source row and
writes in source order. No full NetworkX snapshots or Python dictionary of millions
of edges is constructed. Struct keys avoid delimiter collisions. The split column
is provenance, never a predictor; history may roll forward using earlier unlabeled
transactions across the original temporal boundaries.

The build uses one DuckDB thread, a 1 GB memory budget and temporary disk spill.
That engine setting is not a total process-RSS limit. A temporary directory is
removed on success/failure and the separate `data/features/graph-features-v1/`
artifact is published atomically. Existing outputs are rejected, not overwritten.
The manifest records definition/implementation/input hashes, dependencies, row
coverage, duration and peak RSS. Historical-v1 remains unchanged.

## Controlled experiment

The declaration was saved before implementation or label access. After tests and
feature construction, an execution plan freezes implementation/dependency/lock
hashes, graph inputs and original artifact hashes. A durable attempt record prevents
accidental refitting. The two predeclared real-data configurations are:

1. `history_control`: original historical predictors, freshly fitted control.
2. `history_plus_graph`: identical predictors plus the four graph features.

Both reuse `ml_stabilization.PARAMETERS`: 240 trees, learning rate 0.03, 15 leaves,
maximum depth 6, minimum Hessian 10, minimum child samples 200, L1 1, L2 10,
`max_delta_step=2`, class weight 1, seed 42 and two CPU threads. No early stopping,
extra seeds or hyperparameter search is allowed. Training loss is diagnostic only.

The history preprocessor is fitted on September 1–6 and must exactly match the
original saved means/scales/vocabularies/names. Graph counts and recencies use
training-only log1p means/scales; absent recency is zero-imputed before scaling and
marked by a missingness column. Original preprocessing columns are unchanged.
Matrices are disk-backed float32, one configuration at a time. Pair IDs, timestamps
and splits never enter estimator inputs.

The control must reproduce every original `history_none` validation score and its
metrics exactly; otherwise the experiment halts rather than interpreting a
confounded comparison. Metrics use September 7–8 only: AP is primary, with ROC-AUC
and Precision/Recall at floor(1% × validation rows). Existing whole-tier threshold
selection is saved for each experimental model but never replaces the original
threshold. Stability, raw margins, endpoint saturation, training loss, gain
importance, costs and exact full-validation reloads are also recorded.

A stable AP improvement with no loss in 1% recall is directionally promising under
the predeclared rule; it is not statistical significance or authorization to deploy
or replace the frozen model. A negative result is retained without further tuning.
Only the existing train/validation label-export guard is imported. Graph features
are built for all 5,078,345 rows, but no new test/stress predictions or label
retrievals are made.

## Commands

From the repository root, after dependency installation:

```sh
FEATURE_DIR=data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240
uv run --locked python -m mulegraph.graph_features --features-dir "$FEATURE_DIR"
uv run --locked python -m mulegraph.graph_ml --phase freeze --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env python -m mulegraph.graph_ml \
  --phase train --features-dir "$FEATURE_DIR"
uv run --locked --env-file .env python -m mulegraph.graph_prediction_verify \
  --features-dir "$FEATURE_DIR" --postgresql-sample \
  --output data/graph-prediction/new-verification.json
```

Build/freeze/train commands refuse to overwrite completed versions. Repeat only
the label-free verification with a fresh output filename. Do not remove attempt
records to try additional configurations. Source, feature and original artifact
changes fail integrity checks. Saved models and row-level predictions stay ignored
under `data/ml/graph-prediction-v1/`; local audits remain under `data/graph-prediction/`.

See [measured results and verification](graph_prediction_report.md).
