"""Render measured aggregate results as portable charts and Markdown."""

from pathlib import Path


def prevalence(positive: int, total: int) -> float:
    return 100 * positive / total if total else 0.0


def table(headers: list[str], rows: list[list]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(map(cell, row)) + " |" for row in rows],
        ]
    )


def category_counts(data: dict, category: str, period: str, label: int) -> dict:
    return {
        r["value"]: r["transactions"]
        for r in data["categories"]
        if (r["category"], r["period"], r["is_laundering"]) == (category, period, label)
    }


def total_variation(first: dict, second: dict) -> float | None:
    """Categorical distribution distance in [0, 1]; no pseudocounts."""
    a, b = sum(first.values()), sum(second.values())
    if not a or not b:
        return None
    return (
        sum(
            abs(first.get(k, 0) / a - second.get(k, 0) / b)
            for k in first.keys() | second.keys()
        )
        / 2
    )


def charts(data: dict, directory: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory.mkdir(parents=True, exist_ok=True)
    daily = data["daily"]
    days = [r["day"][5:] for r in daily]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(
        days,
        [r["transactions"] - r["positives"] for r in daily],
        marker="o",
        label="Label 0",
    )
    axes[0].plot(days, [r["positives"] for r in daily], marker="o", label="Label 1")
    axes[0].set(
        yscale="log",
        ylabel="Transactions (log scale)",
        title="HI-Small: daily volume and class prevalence",
    )
    axes[0].legend()
    axes[1].plot(
        days,
        [prevalence(r["positives"], r["transactions"]) for r in daily],
        marker="o",
        color="darkred",
    )
    axes[1].set(ylabel="Positive labels (%)", xlabel="September 2022 (source time)")
    for ax in axes:
        ax.axvline(9.5, color="black", linestyle="--", label="Stress boundary")
        ax.grid(alpha=0.2)
    axes[1].tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(directory / "daily.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    values = sorted(
        {r["value"] for r in data["categories"] if r["category"] == "payment_format"}
    )
    for ax, label in zip(axes, (0, 1), strict=True):
        for offset, period in ((-0.2, "primary"), (0.2, "stress")):
            counts = category_counts(data, "payment_format", period, label)
            total = sum(counts.values())
            ax.bar(
                [i + offset for i in range(len(values))],
                [prevalence(counts.get(v, 0), total) for v in values],
                width=0.4,
                label=f"{period} (n={total:,})",
            )
        ax.set_xticks(range(len(values)), values, rotation=45, ha="right")
        ax.set_title(f"Payment format conditional on label {label}")
        ax.legend()
    axes[0].set_ylabel("Share within period and class (%)")
    fig.tight_layout()
    fig.savefig(directory / "payment_shift.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    rows = [
        r for r in data["amounts"] if r["side"] == "paid" and r["period"] == "primary"
    ]
    currencies = sorted({r["currency"] for r in rows})
    for label, offset in ((0, -0.15), (1, 0.15)):
        selected = [r for r in rows if r["is_laundering"] == label]
        ax.scatter(
            [currencies.index(r["currency"]) + offset for r in selected],
            [float(r["p50"]) for r in selected],
            label=f"Label {label}",
        )
    ax.set_xticks(range(len(currencies)), currencies, rotation=45, ha="right")
    ax.set(
        yscale="log",
        ylabel="Median paid amount (native currency; log scale)",
        title="Primary period: compare classes within each currency only",
    )
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(directory / "amounts.png", dpi=160)
    plt.close(fig)


def render(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    charts(data, path.parent / "figures" / "eda")
    splits = data["splits"]
    primary = sum(r["transactions"] for r in splits if r["split"] != "stress")
    primary_pos = sum(r["positives"] for r in splits if r["split"] != "stress")
    stress = next(r for r in splits if r["split"] == "stress")
    primary_rate = prevalence(primary_pos, primary)
    stress_rate = prevalence(stress["positives"], stress["transactions"])
    stress_ach = sum(
        category_counts(data, "payment_format", "stress", label).get("ACH", 0)
        for label in (0, 1)
    )
    stress_cross_negative = category_counts(data, "cross_currency", "stress", 0)
    stress_self_negative = category_counts(data, "self_transfer", "stress", 0)
    primary_ach_positive = category_counts(data, "payment_format", "primary", 1)
    all_positive_cross = sum(
        category_counts(data, "cross_currency", period, 1).get("true", 0)
        for period in ("primary", "stress")
    )
    sections = [
        "# Milestone 2: exploratory analysis and temporal evaluation design",
        f"Generated {data['generated_at']}. Dataset "
        f"`{data['dataset']['dataset_key']}`; "
        f"fingerprint `{data['dataset']['fingerprint']}`. SQL SHA-256 "
        f"`{data['query_sha256']}`. Database aggregation took "
        f"{data['elapsed_seconds']} seconds in this run (not a benchmark).",
        "Execution and test evidence: [verification log](eda_verification.md).",
        "## Scope and reproducibility",
        "All observations below come from one PostgreSQL REPEATABLE READ, READ ONLY "
        "snapshot of the completed ingestion. SQL aggregates run on the server; Python "
        "receives only summary rows. No raw data, stored transactions, "
        "labels, or schema "
        "were changed. Both money columns remain exact NUMERIC; exact nearest-rank "
        "percentiles use percentile_disc. Only plotting converts values to floats. "
        "The dataset is synthetic: a positive label is a simulator annotation, not "
        "proof of real-world criminal conduct. Pattern annotations are not queried.",
        "Run from the project root with the existing environment:\n\n```sh\n"
        'export PATH="$PWD/.tools/bin:$PATH"\n'
        'export UV_CACHE_DIR="$PWD/.uv-cache"\n'
        'export UV_PYTHON_INSTALL_DIR="$PWD/.uv-python"\n'
        "uv run --locked --env-file .env python -m mulegraph.eda\n```\n\n"
        "Outputs: ignored `data/eda/hi-small.json` (all aggregates), this report, and "
        "`docs/figures/eda/*.png`. SQL lives in `src/mulegraph/sql/eda_*.sql`; "
        "split policy and runner in `src/mulegraph/eda.py`. Dates use source naive "
        "timestamps; no timezone is invented. Same input snapshot and locked code "
        "reproduce aggregates; generation time and runtime naturally vary.",
        "## Proposed chronological splits",
        table(
            [
                "Split",
                "Start inclusive",
                "End exclusive",
                "Rows",
                "Positive",
                "Negative",
                "Positive %",
            ],
            [
                [
                    r["split"],
                    r["starts_at"],
                    r["ends_at"],
                    f"{r['transactions']:,}",
                    r["positives"],
                    f"{r['negatives']:,}",
                    f"{prevalence(r['positives'], r['transactions']):.6f}",
                ]
                for r in splits
            ],
        ),
        "The calendar allocation is six training days, two validation days, and two "
        "test days, rather than equal row counts. Freeze this proposal "
        "before modeling. "
        "Use validation for threshold and hyperparameter choices; use the primary test "
        "once after those choices. Stress results are separate, never pooled with "
        "primary test performance. This EDA has examined test labels, so this is a "
        "development holdout, not a pristine externally blinded test. A "
        "future untouched "
        "dataset is needed for stronger generalization claims.",
        "## Temporal shift and imbalance",
        f"Primary: {primary:,} rows and {primary_pos:,} positives "
        f"({primary_rate:.6f}%). "
        f"Stress: {stress['transactions']:,} rows and "
        f"{stress['positives']:,} positives "
        f"({stress_rate:.6f}%). Positive prevalence rises "
        f"{stress_rate / primary_rate:.1f}×. "
        "This is a change in both transaction volume and class mixture, not merely "
        "a slightly later sample. The tail's small class counts limit "
        "stable comparisons.",
        f"ACH accounts for {stress_ach:,}/{stress['transactions']:,} stress rows "
        f"and {primary_ach_positive.get('ACH', 0):,}/{primary_pos:,} "
        "primary positives. "
        f"Among the {stress['negatives']:,} stress negatives, "
        f"{stress_cross_negative.get('true', 0):,} are cross-currency and "
        f"{stress_self_negative.get('true', 0):,} are self-transfers. "
        f"Across both periods, {all_positive_cross:,} positive rows "
        "are cross-currency. "
        "These strong class-conditional differences show distribution shift "
        "within classes; they are not universal financial-crime rules. A tail-only "
        "evaluation would test a very different task from the primary period.",
        "![Daily volume and prevalence](figures/eda/daily.png)",
        table(
            [
                "Day",
                "Rows",
                "Positive",
                "Positive %",
                "Self-transfers",
                "Cross-currency",
            ],
            [
                [
                    r["day"],
                    r["transactions"],
                    r["positives"],
                    f"{prevalence(r['positives'], r['transactions']):.4f}",
                    r["self_transfers"],
                    r["cross_currency"],
                ]
                for r in data["daily"]
            ],
        ),
        "Class-conditional total variation distance below compares category shares "
        "between primary and stress (0 = identical, 1 = disjoint). Conditioning on "
        "the label separates composition changes from the large label-prior shift. "
        "These are descriptive distances, not significance tests or causal evidence.",
        table(
            ["Category", "Label", "Primary→stress total variation"],
            [
                [
                    category,
                    label,
                    total_variation(
                        category_counts(data, category, "primary", label),
                        category_counts(data, category, "stress", label),
                    ),
                ]
                for category in (
                    "payment_format",
                    "payment_currency",
                    "receiving_currency",
                    "self_transfer",
                    "cross_currency",
                )
                for label in (0, 1)
            ],
        ),
        "![Class-conditional payment format shift](figures/eda/payment_shift.png)",
        "A simulator boundary or annotation-related tail is a plausible explanation, "
        "but these observations do not establish how generation produced the shift. "
        "Do not infer a real-world increase in crime or remove tail rows. Treat it as "
        "a separate distribution-shift stress set. Review simulator generation details "
        "before assigning a causal explanation.",
        "### Within-day activity",
        "Peak hours below use source clock time, not a known local timezone. "
        "Shares condition on period and class; ties choose the earliest hour. "
        "All 24-hour aggregate counts are retained in the JSON. No business-hours "
        "or timezone interpretation is established by the source.",
        table(
            ["Period", "Label", "Peak hour", "Rows in hour", "Class share %"],
            [
                [
                    period,
                    label,
                    peak["hour"],
                    peak["transactions"],
                    round(prevalence(peak["transactions"], total), 2),
                ]
                for period in ("primary", "stress")
                for label in (0, 1)
                if (
                    group := [
                        r
                        for r in data["hours"]
                        if r["period"] == period and r["is_laundering"] == label
                    ]
                )
                for total in [sum(r["transactions"] for r in group)]
                for peak in [max(group, key=lambda r: (r["transactions"], -r["hour"]))]
            ],
        ),
        "## Currency, format, and transfer behavior",
    ]
    for category in (
        "payment_format",
        "payment_currency",
        "receiving_currency",
        "self_transfer",
        "cross_currency",
    ):
        values = sorted(
            {r["value"] for r in data["categories"] if r["category"] == category}
        )
        sections += [
            f"### {category}",
            table(
                [
                    "Value",
                    "Primary label 0",
                    "Primary label 1",
                    "Stress label 0",
                    "Stress label 1",
                ],
                [
                    [
                        v,
                        *[
                            category_counts(data, category, p, label).get(v, 0)
                            for p, label in (
                                ("primary", 0),
                                ("primary", 1),
                                ("stress", 0),
                                ("stress", 1),
                            )
                        ],
                    ]
                    for v in values
                ],
            ),
        ]
    sections += [
        "Self-transfers require equal normalized bank AND account IDs, not just equal "
        "account strings. Cross-currency means receiving and payment "
        "currencies differ. "
        "Format/currency associations are descriptive; they must not become fixed "
        "label rules inferred from holdout data.",
        "## Amount distributions",
        "Money is summarized separately by side, currency, class, and period. Do not "
        "pool currencies or interpret the cross-currency chart as purchasing-power "
        "comparisons. The complete exact min/p50/p90/p99/max/sum tables "
        "are in the JSON. "
        "Medians below describe the primary period; USD paid quantiles additionally "
        "show the tail shift. Heavy tails make unscaled means poor summaries. Any "
        "future clipping/log transforms or scaling parameters must be "
        "fitted on train only.",
        "![Native-currency amount medians](figures/eda/amounts.png)",
        table(
            ["Currency", "Label", "Primary paid n", "Median", "p99", "Maximum"],
            [
                [
                    r["currency"],
                    r["is_laundering"],
                    r["transactions"],
                    r["p50"],
                    r["p99"],
                    r["maximum"],
                ]
                for r in data["amounts"]
                if r["period"] == "primary" and r["side"] == "paid"
            ],
        ),
        table(
            ["USD paid period", "Label", "n", "Min", "p50", "p90", "p99", "Max"],
            [
                [
                    r["period"],
                    r["is_laundering"],
                    r["transactions"],
                    r["minimum"],
                    r["p50"],
                    r["p90"],
                    r["p99"],
                    r["maximum"],
                ]
                for r in data["amounts"]
                if r["currency"] == "US Dollar" and r["side"] == "paid"
            ],
        ),
        "## Account activity and timestamp ties",
        f"The account catalog contains {data['accounts']['accounts']:,} "
        f"composite accounts. "
        "Activity counts distinct source rows touching an account; a self-transfer "
        "counts once for total activity, once as sent and once as received. 'Touches "
        "positive' is descriptive transaction-label exposure, not an "
        "account guilt label. "
        "Newly observed means first transaction in this dataset occurs in that split; "
        "it does not mean the account was created then. No account "
        "identifiers are exported.",
        table(
            [
                "Split",
                "Active",
                "Touches positive",
                "Newly observed",
                "Senders",
                "Receivers",
                "Activity p50",
                "p90",
                "p99",
                "Max",
            ],
            [
                [
                    r[k]
                    for k in (
                        "split",
                        "active_accounts",
                        "touches_positive",
                        "newly_observed_accounts",
                        "senders",
                        "receivers",
                        "p50",
                        "p90",
                        "p99",
                        "maximum",
                    )
                ]
                for r in data["activity"]
            ],
        ),
        table(
            [
                "Period",
                "Distinct timestamps",
                "Tied timestamps",
                "Rows in ties",
                "Largest tie",
            ],
            [
                [
                    r[k]
                    for k in (
                        "period",
                        "distinct_timestamps",
                        "tied_timestamps",
                        "transactions_in_ties",
                        "largest_group",
                    )
                ]
                for r in data["ties"]
            ],
        ),
        "## Point-in-time correctness contract",
        "1. Splits are half-open [start, end). A timestamp exactly at a "
        "boundary belongs "
        "to the later split. Never use source-row order as an event "
        "order or break ties "
        "using a label. Preserve repeated source records; they are "
        "separate observations.\n"
        "2. For a future transaction scored at T, historical transaction inputs must "
        "have event time strictly less than T AND availability time at or before T. "
        "Score all transactions sharing T against the same pre-T state, then update "
        "state after the group. Current-transaction attributes may be used only if "
        "known at scoring time. Never include peer transactions at T in history.\n"
        "3. This dataset lacks arrival, correction, label-resolution, and account "
        "metadata availability times. An event-time-only offline replay assumes "
        "immediate arrival and is not a verified production as-of reconstruction. "
        "Do not treat the entire account/entity catalog as historically available.\n"
        "4. Labels, full-record hashes containing labels, and pattern annotations are "
        "evaluation targets/audit metadata only. No historical label aggregates or "
        "outcome-derived inputs without separately evidenced availability.\n"
        "5. Fit vocabularies, imputers, scalers, sampling, and "
        "thresholds on train/validation "
        "as appropriate; never fit preprocessing on validation, test, or "
        "stress. Unknown "
        "categories need an explicit fallback. A future rolling replay may use earlier "
        "unlabeled observations from evaluation periods, but must freeze "
        "model parameters "
        "and obey the same cutoff. Document rolling versus frozen-history evaluation.\n"
        "6. Future feature tests must prove that adding later events or same-timestamp "
        "peers cannot change pre-T history. No features are implemented "
        "in this milestone.",
        "## Modeling implications and decisions to review",
        "Accuracy alone would hide the rare positive class in the primary period. "
        "Plan precision-recall curves, average precision with prevalence baseline, "
        "precision/recall and counts at a validation-selected operating threshold, and "
        "alert-volume measures. Report uncertainty by time block/account "
        "where possible; "
        "transactions are dependent, so naive independent-row intervals can mislead. "
        "Keep stress metrics separate because prevalence changes precision sharply.",
        "Review the proposed 6/2/2 calendar-day allocation, "
        "development-holdout status, "
        "strict timestamp-batch semantics, and immediate-arrival assumption before "
        "feature work. No purge/embargo duration is invented: choose it once label "
        "horizons, label delays, and feature lookback requirements are defined. "
        "Repeated transactions and overlapping accounts across splits "
        "remain intentional; "
        "this evaluates later activity, not generalization to entirely "
        "unseen accounts. "
        "Account-disjoint evaluation would be a separate experiment.",
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
