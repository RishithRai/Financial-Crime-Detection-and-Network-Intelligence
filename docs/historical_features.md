# historical transaction features

`historical-v1` creates one feature row for every source transaction, retaining
all repeated records. It reads only the core PostgreSQL transaction table plus
dataset ID/fingerprint/status metadata. It does not read labels, label-bearing
source-record hashes, pattern annotations, account names, or entity metadata.
No source table, existing schema definition, raw file, or database configuration
is modified. This milestone implements no model or fitted preprocessing.

## Storage and reproducibility

Run with the existing environment and `.env`:

```sh
uv run --locked --env-file .env python -m mulegraph.features
```

The output is `data/features/historical-v1/<dataset-fingerprint>/`:

- `features.parquet`: one row per source record, globally ordered by source event
  timestamp and source row. Source-row ordering is for reproducible serialization,
  never for breaking historical ties.
- `manifest.json`: dataset identity, version, definition SHA-256, split policy,
  dependency/Python versions, label-free source signature, output SHA-256/size,
  measured runtime/RSS, and completeness counts.

Both files remain excluded from Git. `--output-dir PATH` selects another parent.
The version belongs to the artifact, without modifying the existing PostgreSQL
schema migration. Features reference `(dataset_id, source_row)`; the portable
identity also includes the dataset fingerprint. Timestamps retain source naive
microsecond precision. There is no invented timezone or arrival timestamp.

A definition fingerprint covers the feature implementation modules, the two
source SQL queries, the split policy, version, and relevant dependency versions.
An identical rerun hashes the current label-free transaction stream and the
stored output, then returns `already_built` without rewriting it. Changed code,
dependencies, source values, or artifact bytes cause rejection. A deliberate
new feature definition requires a new `VERSION`, not overwriting version 1.
The source signature covers normalized endpoint identities, source rows, times,
both amounts/currencies, and payment format. It excludes every label field.
Dataset provenance may identify label-containing raw files, but is not a feature.

A filesystem lock prevents concurrent builds under the same output parent.
Outputs are built in a private sibling directory, checked, and renamed atomically
only after completion. Ordinary failures remove that run's partial files. A hard
process kill can leave a `.building-*` directory; it is never treated as complete.
Review and remove only that interrupted run's directory if cleanup is needed.
A post-publication CLI-output failure does not undo the artifact; rerun safely.
The manifest is a reproducibility record, not a signed tamper-proof attestation.

## Feature contract

All historical fields carry `sender_` or `receiver_` prefixes. Each endpoint's
account history includes both incoming and outgoing activity. Identity always
uses the full `(bank_id, account_number)` pair. Self-transfers count once in total
activity, once in sent count, and once in received count. Duplicate source records
remain distinct transactions. The account itself is excluded from unique
counterparties; other banks with the same account string remain distinct.

| Fields | Definition at current timestamp T |
| --- | --- |
| `history_count` | Distinct source transactions touching this account at times strictly before T |
| `sent_count`, `received_count` | Prior outgoing and incoming source transactions, respectively |
| `count_1h`, `count_24h` | Account activity in `[T−1 hour,T)` and `[T−24 hours,T)`; exact lower boundaries included |
| `unique_counterparties` | Exact number of other composite accounts observed in either direction before T |
| `last_activity_at` | Maximum strictly prior account event timestamp; null when history is empty |
| `seconds_since_last` | T minus last prior activity; null when history is empty |
| `history_age_seconds` | T minus first observed prior account activity; not account age since creation |
| `mean_gap_seconds` | `(last_prior_time−first_prior_time)/(history_count−1)`; null with fewer than two prior transactions; includes zero gaps between prior peers |
| `frequency_1h`, `frequency_24h` | Prior window counts divided by 1 or 24 hours, in transactions/hour; fixed denominators |
| `currency_history_count`, `currency_history_sum` | Prior count and exact sum in the current endpoint's direction and current transaction currency |
| `currency_count_1h`, `currency_sum_1h` | Same direction/currency within `[T−1 hour,T)` |
| `currency_count_24h`, `currency_sum_24h` | Same direction/currency within `[T−24 hours,T)` |

For sender money histories, direction means **sent** and currency means the
current payment currency. For receiver histories, direction means **received**
and currency means the current receiving currency. All currency histories are
maintained separately, then only the matching current currency is emitted. A
currency with no matching history gets count/sum zero. No exchange rates,
conversion, combined cross-currency sums, or future currency vocabulary is used.

Current attributes retain both monetary values, both currency names, payment
format, and self-transfer/cross-currency flags. Current time and normalized
endpoint identifiers are also persisted. These attributes are assumed known at
transaction scoring time. In a pre-settlement use case, receiving-side attributes
may not yet be known; that use case needs a narrower input contract before modeling.

Monetary outputs use Arrow/Parquet `DECIMAL(38,9)` and Decimal arithmetic at
60-digit working precision, never binary floating point. Values requiring more
than nine fractional digits or at least 29 integer digits fail rather than round.
This explicit version-1 storage contract accommodates the validated HI-Small
values and is checked for both source values and historical sums. PostgreSQL
source NUMERIC values remain unrestricted and unchanged. A different dataset may
require a new feature schema. Only time/rate indicators use floating-point values.

### Metadata and prospective model inputs

`dataset_id`, `dataset_fingerprint`, `feature_version`, `source_row`, `split`, and
the four endpoint identity columns are routing/provenance/join metadata, not
approved numeric or categorical model predictors. Do not feed source-row IDs,
dataset fingerprints, or split names into a model. `occurred_at` and
`*_last_activity_at` support timing audits; any later calendar encoding needs an
explicit modeling contract. This milestone does not choose a final model-input
subset. Labels can be joined separately for evaluation using dataset/source-row
identity, never used to compute these persisted features.

## Point-in-time semantics and splits

For each composite account, events are processed in chronological timestamp
groups. Every row in a group is emitted against the same pre-T state, and only
then does the entire group update history. No same-timestamp peer contributes
counts, sums, counterparties, or last-activity values, regardless of source row.
Each account has independent state: processing independent accounts in lexical
order is equivalent to a global chronological replay for these account-local
features. It avoids holding all accounts' historical state in Python at once.
Final output is globally chronological. No cross-account or graph feature is
computed, and no finished account's state is shared with another account.

The EDA policy is reused unchanged, with half-open boundaries:

| Split | Inclusive start | Exclusive end |
| --- | --- | --- |
| Train | 2022-09-01 00:00 | 2022-09-07 00:00 |
| Validation | 2022-09-07 00:00 | 2022-09-09 00:00 |
| Primary test | 2022-09-09 00:00 | 2022-09-11 00:00 |
| Stress | 2022-09-11 00:00 | 2022-09-19 00:00 |

This is **rolling observation history**, not frozen training history: earlier
unlabeled validation/test events may inform later events, but no labels or model
updates are involved. Splits do not reset histories. Stress results must remain
separate in later evaluation. Rows outside the policy cause a failed build.

The source has no availability timestamps. Version 1 explicitly assumes event
time equals availability time, so this is an offline event-time replay, not a
verified production reconstruction. Late arrivals and later corrections cannot
be simulated faithfully from this source. A future deployment must filter by
both event and actual availability times. The beginning of the dataset is
left-censored: zero history means unobserved history, not a new or inactive real
account. Fixed-window frequency is correspondingly underestimated near the
start; use history age and cold-start indicators in later analysis. NULL history
fields must not be silently imputed as known zeros using full-dataset statistics.

## Efficiency and verification

PostgreSQL provides two server-side cursors in one `REPEATABLE READ READ ONLY`
snapshot. `COLLATE "C"` aligns lexical account ordering with Python merging,
independent of the database's locale. Sorts can spill to disk; local `work_mem`
is 32 MiB per operation and query parallelism is disabled. Existing indexes and
configuration are preserved. Statement timeout is 30 minutes.

Python merges the streams and stores state only for one account: cumulative
counters, exact unique counterparties, separate direction/currency totals, and
at most 24 hours of timestamp-group activity. Buffers contain 8,192 rows per
endpoint writer. Memory scales with the busiest account and output batches,
not the total five-million-row history. Counterparty sets are exact; an unusually
large hub account can still increase memory requirements.

Temporary endpoint Parquet files are joined by source row, timestamp, and split
using DuckDB with a 256 MiB buffer-pool limit, one worker, and disk spilling.
This is an artifact assembly step; PostgreSQL remains the source database.
There is no Pandas load of the dataset. Final validation requires full unique
source coverage on both sides, no missing required values, consistent rolling
counts, and strictly earlier last-activity timestamps. Nullable-history counts,
cold starts, split counts, output hashes, and output size are recorded.

`ru_maxrss` measures the lifetime peak of the Python process, including Arrow and
DuckDB native allocations. It is not PostgreSQL server memory or combined system
memory. A fresh CLI process gives a meaningful per-run peak; repeated API calls
in one process retain the lifetime high-water mark. The DuckDB buffer limit is
not a total process RSS limit. Runtime includes source reading/sorting, feature
calculation, serialization, assembly, checks, and hashing, up to manifest writing.
Allow disk space for source sorts, both endpoint files, the final file, and spill.

```sh
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Tests cover future and peer invariance in memory and through persisted artifacts,
window boundaries, money precision, mixed directions/currencies, composite IDs,
self-transfers, failure cleanup, source changes, reruns, and label independence.
Integration tests use disposable schemas only. See
[measured feature results](feature_verification.md) for actual full-run evidence.
