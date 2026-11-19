# Ingestion report

Recorded 2026-10-14T05:19:25.803396+05:30 (Asia/Kolkata).

## Outcome

**Committed dataset 1 (`ibm-aml-hi-small-v8`).** All **147 SQL reconciliation checks passed** during loading and again on an identical-input rerun. The rerun returned `already_loaded`, retained the same dataset ID/fingerprint, and inserted no rows.

Dataset fingerprint: `676d1c42a92e495ca159fc0cadf28acd0e33598b728fdc236b6e089dd8f28240`.

Committed completion timestamp: `2026-10-13T23:47:13.008095+00:00` (UTC), or October 14, 2026 at 05:17:13 Asia/Kolkata.

## Committed counts and reconciliation

| Metric | Observed |
| --- | --- |
| transactions | 5,078,345 |
| first_source_row | 1 |
| last_source_row | 5,078,345 |
| labels | 5,078,345 |
| laundering | 5,177 |
| legitimate | 5,073,168 |
| min_timestamp | 2022-09-01 00:00:00 |
| max_timestamp | 2022-09-18 16:18:00 |
| self_transfers | 591,212 |
| cross_currency_rows | 72,170 |
| same_currency_unequal_amounts | 0 |
| outside_window_laundering | 655 |
| outside_window_legitimate | 453 |
| accounts | 518,581 |
| first_account_source_row | 1 |
| last_account_source_row | 518,581 |
| banks | 30,470 |
| entities | 166,207 |
| duplicate_source_records | 9 |
| account_numbers_in_multiple_banks | 8 |
| unmatched_endpoints | 0 |
| unused_accounts | 3,493 |
| dataset metadata rows | 1 |
| source-file metadata rows | 3 |
| validated foreign keys | 10 |
| valid indexes, including primary/unique indexes | 15 |

Every original transaction source row from 1 through 5,078,345 is present. All nine repeated parsed records remain distinct source rows. There are 5,078,345 isolated labels, including 5,177 laundering and 5,073,168 legitimate labels. Both original bank strings remain stored; generated normalized bank IDs resolve all account references. Account numbers remain strings.

Both money columns were inspected in `information_schema` and are unrestricted `numeric` (no fixed precision/scale). All ten foreign keys and all fifteen indexes were inspected in PostgreSQL and are valid. The eight account numbers used in multiple banks retain separate composite identities.

The 147 checks also match per-currency counts/minima/maxima/zero counts, currency and payment-format distributions, daily class counts, file fingerprints, and the other observed metrics above. All three raw-file hashes matched the acquisition and validation records before and after each successful command.

## Execution results

| Command/run | Result | Measured elapsed seconds |
| --- | --- | --- |
| Initial load attempt | Rolled back during reconciliation: Docker shared-memory allocation failed | Not recorded |
| Successful retry | `loaded`; 147 checks passed | 291.974 |
| Identical-input rerun | `already_loaded`; 147 checks passed | 41.773 |

Elapsed values use the importer's wall-clock timer and include input hash verification and SQL reconciliation. The successful load also includes COPY, table insertion, index creation, and commit. These are measurements from this local run, not a throughput benchmark or a claim about other machines. Peak memory was not measured.

The initial failure was PostgreSQL `DiskFull` while a parallel query tried to expand a shared-memory segment. Container `/dev/shm` was measured at **64 MiB**; the PostgreSQL data filesystem still had free space. A separate connection confirmed `mulegraph.datasets` did not exist after rollback. The importer now sets `max_parallel_workers_per_gather = 0` locally within its transaction. Docker Compose, database defaults, and existing volumes were preserved. The retry succeeded with that correction.

## Automated verification

- **Pytest: 37 passed**, with PostgreSQL integration enabled; no skips in the final run.
- Integration coverage includes text-only bank normalization, preserved duplicate rows, exact NUMERIC values, composite identities, label separation, constraint rejections, sequential/concurrent reruns, changed input rejection, missing-label detection, and whole-load rollback after a reconciliation mismatch.
- **Ruff lint and formatting passed.**
- **Wheel build passed.** Its four SQL resources were verified; raw data, environment files, and caches were absent. The first build attempt hit sandbox DNS restrictions; retrying with package-index access succeeded.

## Artifacts, limitations, and next actions

- Execution details: ignored `data/ingestion/first_load.json` and `data/ingestion/rerun.json`.
- [Schema and commands](schema_and_ingestion.md); [source validation report](data_validation_report.md).
- Ingestion committed the dataset to PostgreSQL, and the identical-input rerun was verified. Raw data is not committed to Git.
- The container retains its 64 MiB shared-memory configuration. The ingestion and verification commands apply their workaround per transaction.
- Raw files were not changed. Patterns remain provenance-only, not an ingested annotation table. No predictive features, models, or interface were built.
- The database owner can access both schemas; PUBLIC cannot access the labels schema. Future application roles need deliberate grants. Event timestamps still have no timezone or availability-time semantics.
