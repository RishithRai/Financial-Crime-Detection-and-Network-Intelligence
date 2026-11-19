"""Regenerate aggregate holdout reports and audit predictions without labels."""

import argparse
import json
import tempfile
import time
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from mulegraph.features import sha256_file
from mulegraph.ml_holdout import HOLDOUTS, METHODS, predict_split, validate_freeze
from mulegraph.rules_baseline import open_features, write_json


def verify(directory: Path, features: Path, sources: dict[str, Path]) -> dict:
    started = time.perf_counter()
    freeze_path = directory / "freeze.json"
    frozen = validate_freeze(freeze_path, features, sources)
    result = json.loads((directory / "results.json").read_text())
    if (
        sha256_file(freeze_path) != result["freeze_sha256"]
        or result["selected"] != frozen["selected"]
        or set(result["splits"]) != set(HOLDOUTS)
    ):
        raise ValueError("Completed evaluation provenance mismatch")
    checks = {}
    with (
        tempfile.TemporaryDirectory(prefix="mg-holdout-audit-") as temp,
        duckdb.connect() as db,
    ):
        open_features(db, features)
        for split in HOLDOUTS:
            path = directory / f"{split}.parquet"
            if sha256_file(path) != result["prediction_sha256"][split]:
                raise ValueError("Prediction checksum mismatch")
            saved = pq.read_table(path)
            if saved.column_names != ["source_row", *METHODS]:
                raise ValueError("Unexpected prediction schema")
            fresh = predict_split(db, split, sources, frozen, Path(temp))
            if not saved.equals(fresh):
                raise ValueError("Reloaded predictions differ")
            for method in METHODS:
                m = result["splits"][split]["metrics"][method]
                n = len(saved)
                alerts = int(
                    (saved[method].to_numpy() >= frozen["thresholds"][method]).sum()
                )
                c = m["confusion"]
                if (
                    m["threshold"] != frozen["thresholds"][method]
                    or m["rows"] != n
                    or m["alerts"] != alerts
                    or c["tp"] + c["fp"] != alerts
                    or sum(c.values()) != n
                    or c["tp"] + c["fn"] != m["positives"]
                    or m["budget"]["k"] != n // 100
                ):
                    raise ValueError("Frozen policy/aggregate consistency mismatch")
            checks[split] = {
                "rows": len(saved),
                "methods": len(METHODS),
                "exact_scores": True,
            }
            print(f"Verified {split}: {len(saved):,} rows, all five scores", flush=True)
    audit = {
        "splits": checks,
        "label_accesses": 0,
        "originals_unchanged": True,
        "elapsed_seconds": time.perf_counter() - started,
    }
    write_json(directory / "verification.json", audit)
    return audit


def number(value: float | None, percentage: bool = False) -> str:
    if value is None:
        return "undefined"
    return f"{100 * value:.4f}%" if percentage else f"{value:.6f}"


def render(directory: Path, destination: Path) -> None:
    r = json.loads((directory / "results.json").read_text())
    frozen = json.loads((directory / "freeze.json").read_text())
    lines = [
        "# Milestone 4B: frozen development-holdout results v1",
        "",
        f"Selected model: **{r['selected']}**, unchanged before and after evaluation.",
        "Comparators: frozen Logistic Regression, rules, ACH-only, "
        "constant-score prevalence.",
        "No retraining, model selection, feature changes or "
        "threshold adjustment occurred.",
        "These periods were previously inspected by EDA/rules: they "
        "are development holdouts.",
        "",
        "AP must be read against each split's prevalence. AP/prevalence is descriptive "
        "lift, not a complete adjustment for population differences. "
        "Results are never pooled.",
        "Ranking budgets may split ties using the original label-free identity hash; "
        "threshold alerts preserve the original numeric policies.",
    ]
    for split in HOLDOUTS:
        methods = r["splits"][split]["metrics"]
        base = methods["prevalence"]
        lines += [
            "",
            f"## {split.title()}",
            "",
            f"Period: `{frozen['splits'][split][0]}` to "
            f"`{frozen['splits'][split][1]}` (end exclusive). "
            f"**{base['rows']:,}** transactions; **{base['positives']:,}** positives; "
            f"prevalence **{number(base['prevalence'], True)}**. "
            f"Ranking budget: **{base['budget']['k']:,}** alerts.",
            "",
            "| Method | AP | AP/prevalence | ROC-AUC | P@100 | P@1,000 | "
            "P@1% | R@1% | Budget TP |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for method in METHODS:
            m = methods[method]
            values = [
                method,
                number(m["ap"]),
                number(m["ap_over_prevalence"]),
                number(m["roc_auc"]),
                number(m["at_100"]["precision"], True),
                number(m["at_1000"]["precision"], True),
                number(m["budget"]["precision"], True),
                number(m["budget"]["recall"], True),
                str(m["budget"]["tp"]),
            ]
            lines.append("| " + " | ".join(values) + " |")
        lines += [
            "",
            f"Effective K: {base['at_100']['k']:,} for @100 and "
            f"{base['at_1000']['k']:,} for @1,000.",
            "",
            "| Method | Frozen threshold ≥ | Alerts | Alert rate | "
            "Precision | Recall | TN | FP | FN | TP |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for method in METHODS:
            m = methods[method]
            c = m["confusion"]
            values = [
                method,
                f"{m['threshold']:.17g}",
                f"{m['alerts']:,}",
                number(m["alert_rate"], True),
                number(m["alert_precision"], True),
                number(m["alert_recall"], True),
                *[f"{c[k]:,}" for k in ("tn", "fp", "fn", "tp")],
            ]
            lines.append("| " + " | ".join(values) + " |")
        for grouping, rows in r["splits"][split]["groups"].items():
            lines += [
                "",
                f"### Descriptive breakdown: {grouping}",
                "",
                "| Group | Rows | Positives | Prevalence | LGB alerts | LGB "
                "TP | LR alerts | LR TP |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
            for group, n, pos, la, lt, ra, rt in rows:
                lines.append(
                    f"| {group} | {n:,} | {pos:,} | {100 * pos / n:.4f}% | {la:,} "
                    f"| {lt:,} | {ra:,} | {rt:,} |"
                )
    lines += [
        "",
        "## Label-free distribution shifts",
        "",
        "Shares use the population of each split. These are descriptive comparisons,",
        "not changes to predictors or operating policies.",
    ]
    for column in ("payment_format", "payment_currency", "receiving_currency"):
        names = sorted(
            {name for split in r["shift"].values() for name, _ in split[column]}
        )
        lines += [
            "",
            f"### {column}",
            "",
            "| Value | Train | Validation | Test | Stress |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for name in names:
            shares = []
            for split in ("train", "validation", *HOLDOUTS):
                s = r["shift"][split]
                shares.append(
                    f"{100 * dict(s[column]).get(name, 0) / s['history'][0]:.4f}%"
                )
            lines.append("| " + name + " | " + " | ".join(shares) + " |")
    lines += [
        "",
        "### Historical activity",
        "",
        "| Split | Rows | Sender cold | Receiver cold | Median "
        "sender count | Median sender currency count | Median "
        "inactivity seconds | Median history age seconds |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ("train", "validation", *HOLDOUTS):
        n, cold_s, cold_r, *medians = r["shift"][split]["history"]
        lines.append(
            f"| {split} | {n:,} | {100 * cold_s / n:.4f}% | {100 * cold_r / n:.4f}% | "
            + " | ".join("undefined" if x is None else f"{x:,.2f}" for x in medians)
            + " |"
        )
    lines += [
        "",
        "### Paid amounts within currency",
        "",
        "Cells show median / p99 in the named currency; never "
        "compare different currency units. Quantiles for groups with fewer "
        "than 20 rows are suppressed in this public report.",
        "",
        "| Currency | Train | Validation | Test | Stress |",
        "| --- | --- | --- | --- | --- |",
    ]
    currencies = sorted(
        {row[0] for s in r["shift"].values() for row in s["amount_by_currency"]}
    )
    for currency in currencies:
        cells = []
        for split in ("train", "validation", *HOLDOUTS):
            found = next(
                (
                    row
                    for row in r["shift"][split]["amount_by_currency"]
                    if row[0] == currency
                ),
                None,
            )
            if found is None:
                cells.append("absent")
            elif int(found[1]) < 20:
                cells.append("n<20; suppressed")
            else:
                cells.append(f"{found[2]} / {found[3]}")
        lines.append("| " + currency + " | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Provenance and limitations",
        "",
        f"Freeze recorded `{frozen['frozen_at']}`; digest `{r['freeze_sha256']}`.",
        f"Evaluation completed `{r['completed_at']}` in "
        f"{r['elapsed_seconds']:.3f} seconds.",
        "Both prediction files were generated before either label "
        "export. Access records:",
        "",
        "| Split | Freeze verified (UTC) | Label export completed (UTC) | Rows |",
        "| --- | --- | --- | ---: |",
    ]
    for a in r["label_access"]:
        lines.append(
            f"| {a['split']} | {a['freeze_verified_at']} | "
            f"{a['retrieved_at']} | {a['rows']:,} |"
        )
    lines += [
        "",
        "Original hashes and feature checksum remained unchanged. Predictions contain",
        "source row and five scores only; temporary labels were removed. The constant",
        "baseline has one complete score tie, so its ranking-budget "
        "outcome is arbitrary.",
        "ACH and rules also have score ties; AP groups them instead of breaking ties.",
        "",
        "Neither probability-scale model was calibrated. Predictions "
        "are review suggestions,",
        "not proof of wrongdoing. Synthetic shortcuts, label "
        "quality, immediate attribute",
        "availability, left-censored history and repeated development inspection limit",
        "generalization. Small subgroup estimates and stress ranking "
        "budgets are unstable.",
        "No significance claims or threshold guarantees are made.",
        "",
        "See [the frozen contract](ml_holdout_evaluation.md) and",
        "[interpretation and verification](ml_holdout_verification.md).",
    ]
    destination.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts", type=Path, default=Path("data/ml/supervised-holdout-v1")
    )
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--original", type=Path, default=Path("data/ml/supervised-v1"))
    parser.add_argument(
        "--stable", type=Path, default=Path("data/ml/lightgbm-stable-v1")
    )
    parser.add_argument("--rules", type=Path, default=Path("data/rules/rules-v1"))
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--report", type=Path, default=Path("docs/ml_holdout_report_v1.md")
    )
    args = parser.parse_args()
    if args.verify:
        if args.features_dir is None:
            parser.error("--features-dir is required for audit")
        verify(
            args.artifacts,
            args.features_dir,
            {n: getattr(args, n) for n in ("original", "stable", "rules")},
        )
    render(args.artifacts, args.report)


if __name__ == "__main__":
    main()
