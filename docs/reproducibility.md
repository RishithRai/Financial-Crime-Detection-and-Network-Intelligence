# Reproducibility: reviewer checks and full-data reconstruction

These are distinct paths. A successful synthetic suite does not recreate the
published ML experiment. The October 15, 2026 verification used a tracked-source-only copy
with a fresh virtual environment and no `.env`, data, models or node_modules.
It reused this machine's package caches and Python/OpenMP installation; it was
not a network-cold installation on another OS. See [actual checks](portfolio_release.md).

## A. Reviewer verification without IBM data

Install Git, uv, Python 3.12 and Node 22.12+ with npm. The measured local run used
Python 3.12.15 and Node 24.11.0/npm 11.6.1; CI targets Node 22 on Ubuntu.
On macOS install OpenMP if LightGBM reports a missing `libomp` library.

From a fresh checkout, with no database test environment variable set:

```sh
uv python install 3.12
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
npm ci --prefix frontend
npm test --prefix frontend
npm run check --prefix frontend
npm run build --prefix frontend
```

Expected at this release: **154 passed, 30 PostgreSQL skips**. Synthetic fixtures
exercise ingestion, feature generation, model training, graphs, cases, SHAP and
API/UI behavior; they do not require the original saved models. Small synthetic
fits are tests, not additional real-data experiments. The frontend build is not
a functioning data-free investigation demo. Presentation assets include the
[reviewed screenshots](screenshots/README.md), README architecture diagram, and
aggregate reports/EDA plots. Screenshots illustrate a recorded run, not a new verification.

For database tests, install/start Docker Desktop or Docker Engine with Compose:

```sh
cp .env.example .env  # fresh checkout only; never replace an existing .env
# Edit local credentials/port consistently in .env before initializing a new volume.
docker compose up -d --wait
uv run --locked --env-file .env mulegraph-db-check
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
```

Expected: **184 passed**, using disposable `mg_test_*` schemas. The URL must
allow creating/removing those test schemas; do not point it at an unrelated
production database. The default container is PostgreSQL 17 on localhost:5432;
choose another localhost port if needed. Changing `.env` passwords after initialization
does not update database roles. `docker compose stop` preserves the volume;
never use `down -v` for verification. `.env` is not loaded by Python automatically.

The [CI workflow](../.github/workflows/verify.yml) runs the same synthetic suite
against an ephemeral PostgreSQL service, Ruff and frontend checks. No datasets,
secrets, full-model artifacts or browser-dependent real-data tests are required.
The workflow has not run on GitHub because nothing was published.

## B. Full dataset and experiment reconstruction

**Full reconstruction from this public snapshot is unverified and incomplete.**
The original stages were executed locally. The October verification checked existing
artifact integrity and application replay, not a clean-room retraining. Historical
source revisions and their earlier dependency lock are not included here. Some
integrity auditors require those exact environments.

The following describes the pipeline and its dependencies. It is not a guaranteed
end-to-end reproduction recipe using only this snapshot. Expect several GB of source/database,
feature, environment and scratch storage; full disk capacity was not benchmarked.
Do not run these commands over the completed working dataset/model directories.

### Source and database

Use a separate clone/workspace and a separately named Compose project/volume with
an unused localhost port. Keep its `.env` separate. Follow
[acquisition](data_acquisition.md) for the official IBM-linked Kaggle HI-Small
version 8 inputs: `HI-Small_Trans.csv`, `HI-Small_accounts.csv`, and
`HI-Small_Patterns.txt`. Record actual bytes, hashes, URLs, version and retrieval
time in `data/provenance/hi-small/manifest.json`; compare with the published
[validation report](data_validation_report.md). Do not substitute another dataset
version and call it the same experiment. Patterns are source-validation material,
never feature inputs or analyst evidence. Do not redistribute downloaded data here.

After configuring the separate database:

```sh
uv run --locked python -m mulegraph.validation \
  --provenance data/provenance/hi-small/manifest.json
uv run --locked --env-file .env python -m mulegraph.ingestion
uv run --locked --env-file .env python -m mulegraph.ingestion --verify-only
uv run --locked --env-file .env python -m mulegraph.features
```

Ingestion is atomic and verifies identical reruns. Feature generation reads core
transactions and writes `data/features/historical-v1/<dataset-fingerprint>/`.
Derive `FEATURE_DIR` from that build's manifest, not an assumed dataset ID.
The exact original fingerprint is recorded in [feature verification](feature_verification.md).
EDA is optional for reconstruction; running it accesses aggregate labels and
writes reports. Do not confuse it with a label-free integrity check.

### Historical environment boundary

Use the included `uv.lock` and Python 3.12 for the code checks in path A.
The original pipeline crossed two dependency environments:

| Stage | Required artifacts | Historical environment |
| --- | --- | --- |
| Ingestion, historical features, rules, initial ML | `data/features/historical-v1`, `data/rules/rules-v1`, `data/ml/supervised-v1` | Original lock, not bundled |
| Stable LightGBM | `data/ml/lightgbm-stable-v1`, external plan and attempt records | Original lock, not bundled |
| Frozen supervised evaluation | `data/ml/supervised-holdout-v1` | Original lock, not bundled |
| Investigation application and separate graph experiment | Original saved artifacts; graph experiment additionally needs `graph-features-v1` and `graph-prediction-v1` | Included lock |

Original lock SHA-256:
`bbbfafc3618c37ddb16fe145bd9604ef5ee8271dee64c25beb65c6d9579d96a0`.
Included lock SHA-256:
`1125a6c6883aaf54cfd63e169df5460ea9a81894a0afac5947d65d2e9f0b8384`.
A digest identifies an environment; it does not supply the missing lockfile.
Commit IDs in historical reports identify private development revisions and cannot
be checked out from this snapshot.

Stage commands are documented in [rules](rules_baseline.md),
[initial training](supervised_learning.md), [stabilization](ml_stabilization.md),
[frozen evaluation](ml_holdout_evaluation.md), and the
[separate graph experiment](graph_prediction.md). Before attempting an exact
historical reconstruction, obtain a reviewed source/environment bundle for the
original stages. Do not substitute the current lock or edit hashes to make an
old auditor pass. No such bundle is supplied with this snapshot.

Preserve complete output directories and external plan/attempt files. Hashes cover
metadata as well as models. Do not add files inside a frozen directory after another
stage snapshots it; store audit outputs elsewhere. A new experiment under the
current environment must carry its own provenance and cannot be presented as a
reproduction of the reported run without verification.

The dataset pipeline includes legitimate training/evaluation label access; the
app does not. Model phases must follow their predeclared plans and freeze gates.
Rules and original supervised holdout reconstruction use test/stress labels as
specified in those contracts. The graph-augmented experiment uses train/validation
only. The documentation review did not repeat these training/evaluation phases.

Model files may differ across platforms even with seeds and versions. Stop on a
control/hash mismatch and document it; never bypass guards, edit saved digests,
remove attempt records, overwrite artifacts or retune to reproduce a published score.
Newly reconstructed timestamps/metadata have their own provenance. If a reconstruction
fails, preserve the failed attempt and diagnose in a new workspace. Original saved
runs cannot be reconstructed merely by copying aggregate JSON from `docs/`.

### Application prerequisites and replay

The app needs PostgreSQL core data plus historical-v1, original rules/supervised/
stabilized bundles, the supervised-holdout freeze/results and saved validation,
test and stress predictions. See `DashboardData` and `SavedScoreProvider` for
integrity dependencies. The 7C graph experiment is **not** an application prerequisite.
The app also requires `frontend/dist`, generated by `npm ci` and `npm run build`.

Launch using [README](../README.md#run-the-investigation-demo-with-local-artifacts).
Follow [the demo](demo_walkthrough.md). Existing browser tests require a running
localhost:8000 API, actual artifacts and Chrome:

```sh
npm run test:browser --prefix frontend
```

`CHROME_PATH` overrides the default macOS Chrome executable. Tests save row-level
screenshots under ignored `data/dashboard/7a/`; preserve any earlier screenshots before running browser tests.
Do not interpret `/api/health` as database/model integrity certification.

For current label-free 7C verification, choose a new audit filename:

```sh
uv run --locked python -m mulegraph.graph_prediction_verify \
  --features-dir "$FEATURE_DIR" --output data/graph-prediction/release-check-new.json
```

This checks original snapshots, graph features, model reloads and train-only
preprocessing without fetching labels. Older original ML audits still require
their exact original lock; the release did not relax this requirement.
