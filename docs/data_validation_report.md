# HI-Small data validation report

Generated at 2026-10-13T23:18:52.018071+00:00 (UTC).

## Result

**0 errors; 9 warnings.** Warnings preserve observations for review; they do not trigger data deletion.

### Errors

None detected by the implemented checks.

### Warnings

- transactions: 9 repeated parsed records; retained
- Transactions are not globally sorted by timestamp; file order is not chronology.
- Transactions exist outside the advertised September 1–10 primary window; retained.
- Severe class imbalance: the minority class is below 1% of valid binary labels.
- Self-transfers exist; they are observations, not automatically invalid records.
- Currency or amount differences exist; do not compare or sum money across currencies.
- Literal bank-account joins have unmatched keys; inspect the bank-padding diagnostic.
- Timestamps have no timezone or availability time; historical availability cannot be verified.
- Labels and pattern annotations are outcome information, not historical predictor inputs.

## Key observations

Scanned **5,078,345 transactions** and **518,581 account rows**. Transactions contain **9 repeated parsed records**. The detailed schema tables below report missing and invalid values.

**8 account numbers occur in multiple banks**. Literal joins leave 515,088 distinct transaction keys unmatched; the bank-padding diagnostic leaves 0. Normalization collisions: 0. Keep composite identities and review normalization before ingestion.

Outside the September 1–10 primary window: **655 laundering and 453 legitimate transactions**. Use these measured counts rather than assuming all late transactions have one label. File order is not a valid chronological split.


## Provenance and integrity

Source: [IBM AML-Data](https://github.com/IBM/AML-Data) → [official linked Kaggle dataset](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml).

Dataset version: **8**; source last updated: 2025-07-08T14:59:13.28Z. Retrieved: 2026-10-13T23:13:40.828776+00:00.

Data license reported by source: Community Data License Agreement - Sharing - Version 1.0. This is distinct from the GitHub repository's code license.

Acquisition method: Unauthenticated HTTPS individual-file download; no archive or text transformations.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| HI-Small_Patterns.txt | 323844 | `2c546b5ce6009e73851f0139af053cf845f08bf92f3bc82fe1eb937dec2ef39b` |
| HI-Small_Trans.csv | 475664283 | `b19d39f515523373f991b689c07e11e7b0b95c17a2c27a87d91584ae16c5b040` |
| HI-Small_accounts.csv | 34053187 | `786808526e33cfc441212dd6fccda7edfc24172149bed59c6ef59b186836b014` |

- [HI-Small_Patterns.txt source request](https://www.kaggle.com/api/v1/datasets/download/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/HI-Small_Patterns.txt)
- [HI-Small_Trans.csv source request](https://www.kaggle.com/api/v1/datasets/download/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/HI-Small_Trans.csv?datasetVersionNumber=8)
- [HI-Small_accounts.csv source request](https://www.kaggle.com/api/v1/datasets/download/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/HI-Small_accounts.csv?datasetVersionNumber=8)

This audit is limited to the three requested filenames. The default raw location is ignored `data/raw/hi-small/`; acquisition metadata belongs in ignored `data/provenance/hi-small/`. Available files are hashed locally. When supplied, acquisition fingerprints are checked before scanning; complete audits also rehash files after scanning. These hashes are integrity baselines, not publisher signatures.

## Method and limits

The validator streams CSV records with Python's positional CSV reader. It retains at most 5,000 records per batch and uses disposable SQLite indexes for exact parsed-record duplicates and bank-account relationships (32 MiB SQLite page cache). Categorical summaries scale with distinct categories; timestamp parsing has a bounded 65,536-entry cache. Temporary disk use scales with unique records. No PostgreSQL ingestion takes place.

Duplicate counts mean occurrences beyond the first equal list of decoded CSV fields, including the label; quoting differences do not create new records. Raw hashes cover byte-level differences. Duplicates are not assumed to be erroneous payments. Missing means empty/whitespace-only present fields; short/long rows are separately invalid. Identifiers are never cast to numbers.

Errors include unexpected schemas, malformed records, missing required fields, surrounding whitespace, nonnumeric bank IDs, invalid calendar timestamps, negative/nonfinite/unparseable amounts, labels other than 0/1, conflicting entity assignments, broken pattern references, and provenance mismatches. Nonempty currency and payment-format names are inventoried, not checked against an invented whitelist. Account formats have no numeric/hex restriction.

Amounts use Decimal and are summarized separately by side and currency. No FX conversion, cross-currency total, correction, filtering, feature engineering, or model training is performed. Timezone and data-availability timestamps are absent; event-time validation cannot establish historical availability. The advertised September 1–10 primary period is a diagnostic window, not an enforced exclusion rule.

## Accounts

| Metric | Observed |
| --- | --- |
| complete | True |
| rows | 518581 |
| unique_rows | 518581 |
| duplicate_rows | 0 |
| invalid_rows | 0 |
| bank_values_with_leading_zeros | 0 |

### Actual positional schema and missing values

| Position (1-based) | Raw header | Missing values |
| --- | --- | --- |
| 1 | Bank Name | 0 |
| 2 | Bank ID | 0 |
| 3 | Account Number | 0 |
| 4 | Entity ID | 0 |
| 5 | Entity Name | 0 |

Invalid-reason counts (a record can have multiple reasons): `{}`.

## Transactions

| Metric | Observed |
| --- | --- |
| complete | True |
| rows | 5078345 |
| unique_rows | 5078336 |
| duplicate_rows | 9 |
| invalid_rows | 0 |
| bank_values_with_leading_zeros | 10156690 |

### Actual positional schema and missing values

| Position (1-based) | Raw header | Missing values |
| --- | --- | --- |
| 1 | Timestamp | 0 |
| 2 | From Bank | 0 |
| 3 | Account | 0 |
| 4 | To Bank | 0 |
| 5 | Account | 0 |
| 6 | Amount Received | 0 |
| 7 | Receiving Currency | 0 |
| 8 | Amount Paid | 0 |
| 9 | Payment Currency | 0 |
| 10 | Payment Format | 0 |
| 11 | Is Laundering | 0 |

Invalid-reason counts (a record can have multiple reasons): `{}`.

Positions **3 and 5 both have the raw header `Account`**. They mean sender and receiver respectively. Do not use a dictionary CSV reader that silently overwrites one. Identity uses `(From Bank, Account[3])` or `(To Bank, Account[5])`, not account alone.

### Is Laundering

| Value | Rows |
| --- | --- |
| 0 | 5073168 |
| 1 | 5177 |

### Payment Currency

| Value | Rows |
| --- | --- |
| Australian Dollar | 136769 |
| Bitcoin | 146066 |
| Brazil Real | 70703 |
| Canadian Dollar | 140042 |
| Euro | 1168297 |
| Mexican Peso | 110159 |
| Ruble | 155178 |
| Rupee | 190202 |
| Saudi Riyal | 89014 |
| Shekel | 192184 |
| Swiss Franc | 234860 |
| UK Pound | 180738 |
| US Dollar | 1895172 |
| Yen | 155209 |
| Yuan | 213752 |

### Payment Format

| Value | Rows |
| --- | --- |
| ACH | 600797 |
| Bitcoin | 146091 |
| Cash | 490891 |
| Cheque | 1864331 |
| Credit Card | 1323324 |
| Reinvestment | 481056 |
| Wire | 171855 |

### Receiving Currency

| Value | Rows |
| --- | --- |
| Australian Dollar | 138511 |
| Bitcoin | 148151 |
| Brazil Real | 71544 |
| Canadian Dollar | 141357 |
| Euro | 1172017 |
| Mexican Peso | 111030 |
| Ruble | 157361 |
| Rupee | 192065 |
| Saudi Riyal | 89971 |
| Shekel | 194988 |
| Swiss Franc | 237884 |
| UK Pound | 181255 |
| US Dollar | 1879341 |
| Yen | 156319 |
| Yuan | 206551 |

Laundering rate among valid binary labels: **0.101943%**.

| Relationship observation | Rows |
| --- | --- |
| self_transfers | 591212 |
| cross_currency_rows | 72170 |
| same_currency_unequal_amounts | 0 |

### Timestamps

| Metric | Observed |
| --- | --- |
| min | 2022-09-01 00:00:00 |
| max | 2022-09-18 16:18:00 |
| adjacent_decreases | 2418736 |
| outside_primary_window_by_label | {"0": 453, "1": 655} |

| Date / label | Rows |
| --- | --- |
| 2022-09-01 \| 0 | 1114599 |
| 2022-09-01 \| 1 | 322 |
| 2022-09-02 \| 0 | 754041 |
| 2022-09-02 \| 1 | 408 |
| 2022-09-03 \| 0 | 206991 |
| 2022-09-03 \| 1 | 391 |
| 2022-09-04 \| 0 | 207023 |
| 2022-09-04 \| 1 | 407 |
| 2022-09-05 \| 0 | 482179 |
| 2022-09-05 \| 1 | 471 |
| 2022-09-06 \| 0 | 481558 |
| 2022-09-06 \| 1 | 531 |
| 2022-09-07 \| 0 | 482254 |
| 2022-09-07 \| 1 | 497 |
| 2022-09-08 \| 0 | 482234 |
| 2022-09-08 \| 1 | 539 |
| 2022-09-09 \| 0 | 653953 |
| 2022-09-09 \| 1 | 514 |
| 2022-09-10 \| 0 | 207883 |
| 2022-09-10 \| 1 | 442 |
| 2022-09-11 \| 0 | 164 |
| 2022-09-11 \| 1 | 232 |
| 2022-09-12 \| 0 | 111 |
| 2022-09-12 \| 1 | 170 |
| 2022-09-13 \| 0 | 78 |
| 2022-09-13 \| 1 | 106 |
| 2022-09-14 \| 0 | 51 |
| 2022-09-14 \| 1 | 70 |
| 2022-09-15 \| 0 | 18 |
| 2022-09-15 \| 1 | 28 |
| 2022-09-16 \| 0 | 20 |
| 2022-09-16 \| 1 | 26 |
| 2022-09-17 \| 0 | 8 |
| 2022-09-17 \| 1 | 15 |
| 2022-09-18 \| 0 | 3 |
| 2022-09-18 \| 1 | 8 |

### Amounts by side and currency

| Side | Currency | Finite | Min | Max | Zero | Negative | Invalid |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Amount Paid | Australian Dollar | 136769 | 0.01 | 2474350163.85 | 0 | 0 | 0 |
| Amount Paid | Bitcoin | 146066 | 0.000001 | 135890.107125 | 0 | 0 | 0 |
| Amount Paid | Brazil Real | 70703 | 0.01 | 149963208139.35 | 0 | 0 | 0 |
| Amount Paid | Canadian Dollar | 140042 | 0.01 | 21500692156.37 | 0 | 0 | 0 |
| Amount Paid | Euro | 1168297 | 0.01 | 13463989346.24 | 0 | 0 | 0 |
| Amount Paid | Mexican Peso | 110159 | 0.01 | 30893133697.47 | 0 | 0 | 0 |
| Amount Paid | Ruble | 155178 | 0.01 | 626035501453.45 | 0 | 0 | 0 |
| Amount Paid | Rupee | 190202 | 0.01 | 965933305301.71 | 0 | 0 | 0 |
| Amount Paid | Saudi Riyal | 89014 | 0.01 | 3725980237.05 | 0 | 0 | 0 |
| Amount Paid | Shekel | 192184 | 0.01 | 9494645650.85 | 0 | 0 | 0 |
| Amount Paid | Swiss Franc | 234860 | 0.01 | 3576835693.12 | 0 | 0 | 0 |
| Amount Paid | UK Pound | 180738 | 0.01 | 1397665064.97 | 0 | 0 | 0 |
| Amount Paid | US Dollar | 1895172 | 0.01 | 16620608535.74 | 0 | 0 | 0 |
| Amount Paid | Yen | 155209 | 0.01 | 1046302363293.48 | 0 | 0 | 0 |
| Amount Paid | Yuan | 213752 | 0.01 | 5243592783.03 | 0 | 0 | 0 |
| Amount Received | Australian Dollar | 138511 | 0.01 | 2474350163.85 | 0 | 0 | 0 |
| Amount Received | Bitcoin | 148151 | 0.000001 | 135890.107125 | 0 | 0 | 0 |
| Amount Received | Brazil Real | 71544 | 0.01 | 149963208139.35 | 0 | 0 | 0 |
| Amount Received | Canadian Dollar | 141357 | 0.01 | 21500692156.37 | 0 | 0 | 0 |
| Amount Received | Euro | 1172017 | 0.01 | 13463989346.24 | 0 | 0 | 0 |
| Amount Received | Mexican Peso | 111030 | 0.01 | 30893133697.47 | 0 | 0 | 0 |
| Amount Received | Ruble | 157361 | 0.01 | 626035501453.45 | 0 | 0 | 0 |
| Amount Received | Rupee | 192065 | 0.01 | 965933305301.71 | 0 | 0 | 0 |
| Amount Received | Saudi Riyal | 89971 | 0.01 | 3725980237.05 | 0 | 0 | 0 |
| Amount Received | Shekel | 194988 | 0.01 | 9494645650.85 | 0 | 0 | 0 |
| Amount Received | Swiss Franc | 237884 | 0.01 | 3576835693.12 | 0 | 0 | 0 |
| Amount Received | UK Pound | 181255 | 0.01 | 1397665064.97 | 0 | 0 | 0 |
| Amount Received | US Dollar | 1879341 | 0.01 | 16620608535.74 | 0 | 0 | 0 |
| Amount Received | Yen | 156319 | 0.01 | 1046302363293.48 | 0 | 0 | 0 |
| Amount Received | Yuan | 206551 | 0.01 | 5243592783.03 | 0 | 0 | 0 |

## Account relationships

Literal joins retain bank strings exactly. The separate padding diagnostic removes leading ASCII zeros from numeric bank IDs only, leaving account identifiers unchanged. It does not rewrite files or authorize ingestion. Unmatched row counts are endpoint occurrences; a transaction can have both an unmatched sender and receiver. Composite-key counts are distinct pairs. Relationship checks include all structurally complete, nonblank identities, even if another field in that record is invalid.

| Metric | Observed |
| --- | --- |
| account_banks | 30470 |
| account_composite_keys | 518581 |
| account_keys_unused_after_bank_normalization | 3493 |
| account_numbers | 518573 |
| account_numbers_in_multiple_banks | 8 |
| bank_normalization_collisions | 0 |
| bank_padding_diagnostic | {"unmatched_composite_keys": 0, "unmatched_receiver_rows": 0, "unmatched_sender_rows": 0} |
| composite_keys_with_multiple_entities | 0 |
| entities | 166207 |
| literal | {"unmatched_composite_keys": 515088, "unmatched_receiver_rows": 5078345, "unmatched_sender_rows": 5078345} |
| transaction_composite_keys | 515088 |
| transaction_normalized_composite_keys | 515088 |

## Pattern annotations

Patterns are headerless transaction rows enclosed by BEGIN/END attempt markers. Every parsed row is checked against the transaction schema, binary label 1, and an exact full-record match in the transaction file. The file is annotation data; it is not expected to cover all laundering.

| Metric | Observed |
| --- | --- |
| blank_lines | 370 |
| blocks | 370 |
| closed_blocks | 370 |
| complete | True |
| duplicate_rows | 0 |
| invalid_rows | 0 |
| lines | 4319 |
| non_laundering_rows | 0 |
| structure_errors | 0 |
| transaction_rows | 3209 |
| types | {"BIPARTITE": 49, "CYCLE": 54, "FAN-IN": 40, "FAN-OUT": 48, "GATHER-SCATTER": 51, "RANDOM": 41, "SCATTER-GATHER": 44, "STACK": 43} |
| unique_transaction_rows | 3209 |
| unmatched_rows | 0 |

## Decisions requiring review

- Decide whether to adopt explicit bank-padding normalization for future joins after reviewing collision and unmatched-key counts. Retain raw bank IDs.
- Decide treatment of repeated records, unusual amounts, self-transfers, and out-of-window transactions. None were removed or corrected.
- Establish chronological evaluation and historical availability rules before any feature work. Later outcomes and pattern labels must never become historical predictors.

## Reproduction

```sh
uv run --locked python -m mulegraph.validation --provenance data/provenance/hi-small/manifest.json
```

The JSON audit is written to ignored `data/validation/hi-small.json`. This Markdown report contains aggregate observations only. Exit status is 0 for a completed audit without errors (warnings allowed), 1 for validation errors, or 2 for operational failure. Unit test results are reported separately; generating this document does not claim tests passed.
