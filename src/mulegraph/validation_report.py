"""Render aggregate observations only; never publish raw account records."""

import json


def _cell(value: object) -> str:
    if isinstance(value, dict):
        value = json.dumps(value, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_cell(value) for value in row) + " |" for row in rows
    )
    return "\n".join(lines) + "\n"


def render_report(report: dict) -> str:
    """Build Markdown solely from this audit's measured results and provenance."""
    lines = [
        "# HI-Small data validation report\n",
        f"Generated at {report['generated_at_utc']} (UTC).\n",
        "## Result\n",
        f"**{len(report['errors'])} errors; {len(report['warnings'])} warnings.** "
        "Warnings preserve observations for review; they do not "
        "trigger data deletion.\n",
        "### Errors\n",
        *(f"- {item}" for item in report["errors"]),
        *([] if report["errors"] else ["None detected by the implemented checks."]),
        "\n### Warnings\n",
        *(f"- {item}" for item in report["warnings"]),
    ]
    transactions = report.get("transactions", {})
    accounts = report.get("accounts", {})
    if transactions.get("complete") and accounts.get("complete"):
        lines.extend(
            [
                "\n## Key observations\n",
                f"Scanned **{transactions['rows']:,} transactions** and "
                f"**{accounts['rows']:,} account rows**. Transactions contain "
                f"**{transactions['duplicate_rows']:,} repeated parsed records**. "
                "The detailed schema tables below report missing and invalid values.\n",
            ]
        )
        relations = report.get("relationships", {})
        if relations:
            diagnostic = relations["bank_padding_diagnostic"]
            lines.append(
                f"**{relations['account_numbers_in_multiple_banks']:,} account "
                "numbers occur in multiple banks**. Literal joins leave "
                f"{relations['literal']['unmatched_composite_keys']:,} distinct "
                "transaction keys unmatched; the bank-padding diagnostic leaves "
                f"{diagnostic['unmatched_composite_keys']:,}. "
                "Normalization collisions: "
                f"{relations['bank_normalization_collisions']:,}. "
                "Keep composite identities and review normalization before ingestion.\n"
            )
        outside = transactions["timestamps"]["outside_primary_window_by_label"]
        if outside:
            lines.append(
                f"Outside the September 1–10 primary window: **{outside.get('1', 0):,} "
                f"laundering and {outside.get('0', 0):,} legitimate transactions**. "
                "Use these measured counts rather than assuming all late transactions "
                "have one label. File order is not a valid chronological split.\n"
            )
    lines.append("\n## Provenance and integrity\n")
    provenance = report["provenance"]
    if provenance:
        lines.extend(
            [
                f"Source: [IBM AML-Data]({provenance.get('upstream_url', '')}) → "
                "[official linked Kaggle dataset]"
                f"({provenance.get('dataset_url', '')}).\n",
                f"Dataset version: **{provenance.get('dataset_version', 'unknown')}**; "
                "source last updated: "
                f"{provenance.get('dataset_last_updated', 'unknown')}. "
                f"Retrieved: {provenance.get('retrieved_at_utc', 'unknown')}.\n",
                "Data license reported by source: "
                f"{provenance.get('license', 'unknown')}. "
                "This is distinct from the GitHub repository's code license.\n",
                f"Acquisition method: {provenance.get('method', 'unknown')}.\n",
            ]
        )
    lines.append(
        _table(
            ["File", "Bytes", "SHA-256"],
            [
                [name, values["size_bytes"], f"`{values['sha256']}`"]
                for name, values in report["files"].items()
            ],
        )
    )
    for name, metadata in provenance.get("files", {}).items():
        lines.append(f"- [{name} source request]({metadata.get('source_url', '')})")
    lines.extend(
        [
            "\nThis audit is limited to the three requested filenames. The default "
            "raw location is ignored `data/raw/hi-small/`; acquisition metadata "
            "belongs in ignored `data/provenance/hi-small/`. Available files are "
            "hashed locally. When supplied, acquisition fingerprints are checked "
            "before scanning; complete audits also rehash files after scanning. "
            "These hashes are integrity baselines, not publisher signatures.\n",
            "## Method and limits\n",
            "The validator streams CSV records with Python's positional CSV reader. It "
            "retains at most 5,000 records per batch and uses "
            "disposable SQLite indexes "
            "for exact parsed-record duplicates and bank-account relationships (32 MiB "
            "SQLite page cache). Categorical summaries scale with distinct categories; "
            "timestamp parsing has a bounded 65,536-entry cache. "
            "Temporary disk use scales "
            "with unique records. No PostgreSQL ingestion takes place.\n",
            "Duplicate counts mean occurrences beyond the first equal list of decoded "
            "CSV fields, including the label; quoting differences do not create new "
            "records. Raw hashes cover byte-level differences. "
            "Duplicates are not assumed "
            "to be erroneous payments. Missing means "
            "empty/whitespace-only present fields; "
            "short/long rows are separately invalid. Identifiers are "
            "never cast to numbers.\n",
            "Errors include unexpected schemas, malformed records, "
            "missing required fields, "
            "surrounding whitespace, nonnumeric bank IDs, invalid calendar timestamps, "
            "negative/nonfinite/unparseable amounts, labels other "
            "than 0/1, conflicting "
            "entity assignments, broken pattern references, and provenance mismatches. "
            "Nonempty currency and payment-format names are inventoried, not checked "
            "against an invented whitelist. Account formats have no "
            "numeric/hex restriction.\n",
            "Amounts use Decimal and are summarized separately by side and currency. "
            "No FX conversion, cross-currency total, correction, filtering, feature "
            "engineering, or model training is performed. Timezone "
            "and data-availability "
            "timestamps are absent; event-time validation cannot establish historical "
            "availability. The advertised September 1–10 primary "
            "period is a diagnostic "
            "window, not an enforced exclusion rule.\n",
        ]
    )
    for kind in ("accounts", "transactions"):
        audit = report.get(kind)
        if not audit:
            continue
        lines.extend(
            [
                f"## {kind.title()}\n",
                _table(
                    ["Metric", "Observed"],
                    [
                        [key, audit.get(key)]
                        for key in (
                            "complete",
                            "rows",
                            "unique_rows",
                            "duplicate_rows",
                            "invalid_rows",
                            "bank_values_with_leading_zeros",
                        )
                    ],
                ),
                "### Actual positional schema and missing values\n",
                _table(
                    ["Position (1-based)", "Raw header", "Missing values"],
                    [
                        [index, name, audit["missing"].get(f"{index}: {name}", 0)]
                        for index, name in enumerate(audit["header"], start=1)
                    ],
                ),
                "Invalid-reason counts (a record can have multiple reasons): "
                f"`{json.dumps(audit['invalid_reasons'], sort_keys=True)}`.\n",
            ]
        )
        if kind == "transactions":
            lines.append(
                "Positions **3 and 5 both have the raw header `Account`**. They mean "
                "sender and receiver respectively. Do not use a dictionary CSV reader "
                "that silently overwrites one. Identity uses `(From Bank, Account[3])` "
                "or `(To Bank, Account[5])`, not account alone.\n"
            )
            for category, counts in audit["categories"].items():
                lines.extend(
                    [
                        f"### {category}\n",
                        _table(
                            ["Value", "Rows"],
                            [[name, count] for name, count in sorted(counts.items())],
                        ),
                    ]
                )
            rate = audit.get("laundering_rate_percent")
            rate_text = "unavailable" if rate is None else f"{rate:.6f}%"
            lines.append(
                f"Laundering rate among valid binary labels: **{rate_text}**.\n"
            )
            lines.append(
                _table(
                    ["Relationship observation", "Rows"],
                    [
                        [key, audit[key]]
                        for key in (
                            "self_transfers",
                            "cross_currency_rows",
                            "same_currency_unequal_amounts",
                        )
                    ],
                )
            )
            lines.extend(
                [
                    "### Timestamps\n",
                    _table(
                        ["Metric", "Observed"],
                        [
                            [key, audit["timestamps"][key]]
                            for key in (
                                "min",
                                "max",
                                "adjacent_decreases",
                                "outside_primary_window_by_label",
                            )
                        ],
                    ),
                    _table(
                        ["Date / label", "Rows"],
                        [
                            [key, value]
                            for key, value in sorted(
                                audit["timestamps"]["dates_by_label"].items()
                            )
                        ],
                    ),
                ]
            )
            lines.append("### Amounts by side and currency\n")
            lines.append(
                _table(
                    [
                        "Side",
                        "Currency",
                        "Finite",
                        "Min",
                        "Max",
                        "Zero",
                        "Negative",
                        "Invalid",
                    ],
                    [
                        [
                            side,
                            currency,
                            values["finite_count"],
                            values["min"],
                            values["max"],
                            values["zero_count"],
                            values["negative_count"],
                            values["invalid_count"],
                        ]
                        for side, currencies in audit["amounts"].items()
                        for currency, values in sorted(currencies.items())
                    ],
                )
            )
    if "relationships" in report:
        lines.extend(
            [
                "## Account relationships\n",
                "Literal joins retain bank strings exactly. The separate "
                "padding diagnostic "
                "removes leading ASCII zeros from numeric bank IDs only, "
                "leaving account "
                "identifiers unchanged. It does not rewrite files or "
                "authorize ingestion. "
                "Unmatched row counts are endpoint occurrences; a transaction can have "
                "both an unmatched sender and receiver. Composite-key "
                "counts are distinct "
                "pairs. Relationship checks include all structurally "
                "complete, nonblank "
                "identities, even if another field in that record is invalid.\n",
                _table(
                    ["Metric", "Observed"],
                    [[key, value] for key, value in report["relationships"].items()],
                ),
            ]
        )
    if "patterns" in report:
        lines.extend(
            [
                "## Pattern annotations\n",
                "Patterns are headerless transaction rows enclosed by "
                "BEGIN/END attempt "
                "markers. Every parsed row is checked against the transaction schema, "
                "binary label 1, and an exact full-record match in the "
                "transaction file. "
                "The file is annotation data; it is not expected to "
                "cover all laundering.\n",
                _table(
                    ["Metric", "Observed"],
                    [[key, value] for key, value in report["patterns"].items()],
                ),
            ]
        )
    lines.extend(
        [
            "## Decisions requiring review\n",
            "- Decide whether to adopt explicit bank-padding normalization for future "
            "joins after reviewing collision and unmatched-key "
            "counts. Retain raw bank IDs.",
            "- Decide treatment of repeated records, unusual amounts, "
            "self-transfers, and "
            "out-of-window transactions. None were removed or corrected.",
            "- Establish chronological evaluation and historical "
            "availability rules before "
            "any feature work. Later outcomes and pattern labels must never become "
            "historical predictors.",
            "\n## Reproduction\n",
            "```sh\n"
            "uv run --locked python -m mulegraph.validation "
            "--provenance data/provenance/hi-small/manifest.json\n"
            "```\n",
            "The JSON audit is written to ignored `data/validation/hi-small.json`. "
            "This Markdown report contains aggregate observations only. Exit status is "
            "0 for a completed audit without errors (warnings "
            "allowed), 1 for validation "
            "errors, or 2 for operational failure. Unit test results are reported "
            "separately; generating this document does not claim tests passed.\n",
        ]
    )
    return "\n".join(lines) + "\n"
