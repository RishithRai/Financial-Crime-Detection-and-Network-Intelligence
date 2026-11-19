# Historical features verification

Executed on 2026-10-14 using the existing PostgreSQL dataset and Python 3.12.15. The full pipeline and safe rerun completed successfully. No raw data, source database tables, existing migrations, or labels were modified. The source snapshot explicitly confirmed `transaction_read_only=on`.

## Actual execution results

| Measurement | Observed result |
| --- | --- |
| Feature version | `historical-v1` |
| Feature rows | 5,078,345 |
| Columns | 53, including identity/routing/timestamp metadata |
| Invalid rows / missing required values | 0 |
| Full pipeline time | 433.804 seconds (about 7.23 minutes) |
| Python process lifetime peak RSS | 411.58 MiB, including Arrow and DuckDB |
| Final Parquet size | 417,104,711 bytes (397.78 MiB) |
| Identical-source rerun | `already_built`, 5,078,345 rows verified, 52.569 seconds; no artifact rewrite |
| Physical output order | All 5,078,345 rows verified ordered by `(occurred_at, source_row)` |
| Independent PostgreSQL sample check | 12 source rows × 2 endpoints; all 312 historical values matched |
| Pytest, PostgreSQL integration enabled | **61 passed in 3.02 seconds**, no failures or skips |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Git exclusions | Feature Parquet and manifest confirmed ignored |


The sample check used source rows 1, each multiple of 500,000 through 5,000,000, and 5,078,345. Independent SQL filtered account histories with `occurred_at < T` and compared total/directional/window counts, exact currency sums/counts, unique counterparties, and last prior timestamp. This is an additional sample audit, not a claim of independently recomputing every feature value for every row. The pipeline validates completeness/cutoff invariants across the entire file.


Runtime includes source sorting/reading, history calculation, serialization, external join/sort, output checks, and hashing up to manifest writing. These are local execution measurements, not benchmarks. Rerun verification and the sample audit were executed concurrently. PostgreSQL server peak memory was not measured; 32 MiB `work_mem` is per operation, not total server memory. Temporary Parquet/spill usage was observed at approximately 3.3 GiB during assembly; this was a spot observation, not a measured peak. Temporary build files were removed on success.

## Preserved split counts

| Split | Inclusive dates in September 2022 | Feature rows |
| --- | --- | --- |
| train | 1–6 | 3,248,921 |
| validation | 7–8 | 965,524 |
| test | 9–10 | 862,792 |
| stress | 11–18 | 1,108 |


All 5,078,345 source transactions are represented, including repeated records. The splits match the EDA counts exactly. No label distributions were used to build features; labels remain in the isolated PostgreSQL schema.

## Completeness and expected null values

Sender histories are empty for 436,392 rows; receiver histories are empty for 375,976 rows. These are cold-start observations in this dataset, not missing source records. Counts and amount sums are zero when history is empty. Last-activity time, inactivity, and history age are null without prior events; mean gap is null with fewer than two prior events.

| Nullable field | Rows with expected null |
| --- | --- |
| `sender_history_age_seconds` | 436,392 |
| `sender_last_activity_at` | 436,392 |
| `sender_mean_gap_seconds` | 704,941 |
| `sender_seconds_since_last` | 436,392 |
| `receiver_history_age_seconds` | 375,976 |
| `receiver_last_activity_at` | 375,976 |
| `receiver_mean_gap_seconds` | 634,491 |
| `receiver_seconds_since_last` | 375,976 |


All other required fields passed non-null validation. No monetary precision or range violations occurred. Money persisted as `DECIMAL(38,9)`; no floating-point conversion or currency conversion was used.

## Provenance

- Dataset fingerprint: `676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240`
- Feature definition SHA-256: `3fc06c0cd286a355f84ff85b4bc48e989734ae27a8f2ef8266599c03e9cfb8de`
- Label-free source stream SHA-256: `3184359b1d78068e878c9417339c5aac78ff57ed87344d85352245462e245c63`
- Feature Parquet SHA-256: `dffd3df6fe3b938281f6f28fccf6584736698af6f6206426754425d1bb2f8d89`
- Dependencies: Psycopg 3.3.6, PyArrow 23.0.1, DuckDB 1.5.6.


Artifact directory: `data/features/historical-v1/676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240`. The manifest records provenance and completeness; `data/features/sample_verification.json` records the supplementary sample/order audit. These row-level artifacts remain outside Git.

## Verification commands and test coverage

```sh
uv run --locked --env-file .env python -m mulegraph.features
# Repeat the same command to verify an existing artifact.
uv run --locked --env-file .env python -m mulegraph.features
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The tests prove invariance of existing historical features when later events or same-timestamp peers are added, both in memory and in persisted output. A seeded independent brute-force reference covers mixed directions, currencies, self-transfers, ties, and multiple composite identities. Other tests cover exact 1-hour/24-hour boundaries, nullable history, monetary precision rejection, failure cleanup, reruns, changed-source detection, and generating identical feature values after deleting all fixture labels. Production labels were never deleted; integration tests modify only disposable schemas.

One initial unit-test fixture placed a boundary event on August 31, outside the approved interval. The guard correctly rejected it; the fixture was moved within the interval and all tests subsequently passed. The date guard was not relaxed. No full-data build failed, and no final verification was skipped.

## Assumptions and remaining limitations

There are no unresolved execution blockers. Review the immediate-arrival assumption, receiving-side current-attribute availability at scoring time, and rolling unlabeled history across split boundaries before modeling. The source cannot establish real arrival/correction times. Account histories begin at the dataset boundary and are left-censored. The extreme stress-period shift and development-holdout status documented in EDA still apply.

Dataset/source-row IDs, fingerprint, version, split, and endpoint identities are provenance/join metadata, not approved model predictors. Labels and pattern annotations are absent from feature values. No preprocessing was fitted and no models, graph neural networks, or interface were built. See [feature definitions](historical_features.md) for the complete input contract.
