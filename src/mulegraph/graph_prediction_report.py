"""Render aggregate graph experiment metrics without fitting or reading labels."""

import json
from pathlib import Path


def render(models: Path, graph: Path) -> str:
    result = json.loads((models / "results.json").read_text())
    manifest = json.loads((graph / "manifest.json").read_text())
    plan = json.loads((models / "plan.json").read_text())
    a, b = result["experiments"]
    lines = [
        "# Milestone 7C: measured graph-feature comparison",
        "",
        "Exploratory September 7–8 validation only. No new test/stress predictions or",
        "label evaluation. The application retains frozen "
        "`lightgbm-stable-v1/history_none`.",
        "",
        "| Model | AP | ROC-AUC | P@1% | R@1% | Budget TP |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in (a, b):
        m = r["metrics"]
        k = m["budget_1pct"]
        lines.append(
            f"| {r['name']} | {m['average_precision']:.8f} | {m['roc_auc']:.8f} | "
            f"{k['precision']:.4%} | {k['recall']:.4%} | {k['true_positives']} |"
        )
    am, bm = a["metrics"], b["metrics"]
    tp_delta = bm["budget_1pct"]["true_positives"] - am["budget_1pct"]["true_positives"]
    lines += [
        "",
        f"Validation: {am['rows']:,} rows, {am['positives']:,} positives, "
        f"{am['prevalence']:.4%} prevalence; budget {am['budget_1pct']['k']:,} alerts.",
        f"AP change: **{bm['average_precision'] - am['average_precision']:+.8f}**. "
        f"Budget true-positive change: **{tp_delta:+d}**.",
        "The freshly fitted control exactly reproduced every frozen "
        "validation score and metric.",
        "",
        "## Computation and numerical checks",
        "",
        "| Fit | Encoded columns | Fit seconds | Train/validation "
        "diagnostic seconds | Matrix seconds | Stable |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in (a, b):
        lines.append(
            f"| {r['name']} | {len(r['feature_names'])} | {r['fit_seconds']:.3f} | "
            f"{r['prediction_seconds']:.3f} | "
            f"{r['matrix_seconds']:.3f} | {r['stable']} |"
        )
    lines += [
        "",
        "Shared training-only preprocessing: "
        f"{result['preprocessing_seconds']:.3f} seconds. "
        f"Complete experiment: {result['elapsed_seconds']:.3f} seconds; "
        f"process peak RSS {result['peak_rss_mib']:.2f} MiB.",
        f"Graph build: {manifest['checks']['rows']:,} rows in "
        f"{manifest['elapsed_seconds']:.3f} seconds; "
        f"process peak RSS {manifest['peak_rss_mib']:.2f} MiB; "
        f"Parquet {(graph / 'features.parquet').stat().st_size:,} bytes.",
        "These are local wall times, not production benchmarks. "
        "Diagnostic prediction time",
        "includes both train and validation raw-margin/probability "
        "passes; matrix work includes",
        "disk-backed retrieval and transformation. OS/native memory "
        "can exceed DuckDB limits.",
        "",
        "| Fit | Validation raw range | Exact endpoints | Top-score "
        "tie | Post-initial leaf max |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for r in (a, b):
        d = r["diagnostics"]["validation"]
        lines.append(
            f"| {r['name']} | [{d['raw_min']:.4f}, {d['raw_max']:.4f}] | "
            f"{d['exact_zero'] + d['exact_one']} | {d['top_tie']} | "
            f"{r['max_post_initial_leaf']:.8f} |"
        )
    lines += [
        "",
        "All full-validation reload checks passed in the training "
        "runner. Training loss",
        "traces and fit warnings are retained in ignored metadata; "
        "no stopping used validation.",
        "",
        f"Saved validation thresholds: control `{am['threshold']:.17g}` "
        f"({am['alerts']:,} alerts), augmented `{bm['threshold']:.17g}` "
        f"({bm['alerts']:,} alerts). Complete score tiers can yield fewer alerts",
        "than the exact ranking budget. The original operating threshold is unchanged.",
        "",
        "## Feature coverage (unlabeled)",
        "",
        "| Split | Rows | Prior forward interaction | Prior reverse "
        "interaction | Prior activity both directions |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in manifest["checks"]["splits"]:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    lines += [
        "",
        "Test/stress entries above are feature coverage only, not "
        "model predictions or label evaluation.",
        "",
        "## Freeze and access evidence",
        "",
        f"Execution freeze: `{plan['created_at']}`; protects "
        f"{len(plan['originals'])} original files.",
        f"Declaration SHA-256: `{plan['plan_sha256']}`.",
        f"Graph file SHA-256: `{manifest['file_sha256']}`.",
    ]
    for access in result["label_access"]:
        lines.append(
            f"- {access['split']} label export completed "
            f"`{access['completed_at']}`; {access['rows']:,} rows."
        )
    lines += [
        "",
        "Only the predeclared control and augmented fits ran. No "
        "original model or threshold",
        "was replaced. Labels and temporary matrices were removed; "
        "predictions contain source",
        "reference and review score only. Timestamps/hashes are "
        "reproducibility evidence.",
        "",
        "## Interpretation",
        "",
    ]
    if result["exploratory_promising"]:
        lines += [
            "The graph group meets the predeclared directional "
            "criterion: higher AP with no",
            "loss of 1% budget recall and stable numerical behavior. "
            "This suggests additional",
            "predictive information on this reused validation "
            "period, not statistical significance",
            "or improved performance on an untouched population. "
            "Retain the original selected",
            "model pending a separately authorized frozen "
            "development-holdout comparison.",
        ]
    else:
        lines += [
            "The graph group does not meet the predeclared "
            "AP/recall/stability criterion.",
            "Retain the original selected model; report this result "
            "without additional tuning.",
        ]
    lines += [
        "",
        "The graph features summarize pair interaction topology, not "
        "verified money flow.",
        "Repeated validation use, synthetic generator associations, "
        "observation-start censoring",
        "and assumed attribute availability limit interpretation. "
        "Reciprocity is rare in this",
        "dataset. No calibrated probability or causal explanation is "
        "established. This is a",
        "group-level ablation, not an attribution of gain to any "
        "single added predictor.",
        "",
        "See [contract and reproduction](graph_prediction.md) and",
        "[verification and recovery notes](graph_prediction_verification.md).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    Path("docs/graph_prediction_report.md").write_text(
        render(
            Path("data/ml/graph-prediction-v1"), Path("data/features/graph-features-v1")
        )
    )


if __name__ == "__main__":
    main()
