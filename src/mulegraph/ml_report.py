"""Render aggregate-only validation results without reopening any labels."""

import argparse
import json
from pathlib import Path

import duckdb


def percentage(value: float | None) -> str:
    return "undefined" if value is None else f"{100 * value:.3f}%"


def render(directory: Path, destination: Path) -> None:
    report = json.loads((directory / "results.json").read_text())
    plan = json.loads((directory / "plan.json").read_text())
    experiments = report["experiments"]
    best = next(r for r in experiments if r["name"] == report["recommended"])
    baseline = report["baselines"]["constant_score"]
    lines = [
        "# Milestone 4A: measured training and validation results",
        "",
        "All results below use September 7–8 validation only. No test/stress labels "
        "were accessed by this pipeline, and no test/stress predictions were made.",
        "",
        f"Training: {report['label_access'][0]['rows']:,} rows, "
        f"{report['training_positives']:,} positive labels. "
        f"Validation: {baseline['rows']:,} rows, {baseline['positives']:,} positives "
        f"({percentage(baseline['prevalence'])} prevalence).",
        "",
        f"The predeclared highest-AP selection recommends **{best['name']}** "
        "for a later, explicitly authorized final evaluation. This is a validation "
        "selection result, not a test result or evidence of real-world utility.",
        "",
        "## All experiments and comparable 1% ranking budget",
        "",
        "AP and ROC-AUC are fractions; precision/recall are percentages. The exact "
        f"ranking budget is {baseline['budget_1pct']['k']:,} alerts for every method.",
        "",
        "| Experiment | AP | ROC-AUC | Budget TP | Budget precision | "
        "Budget recall | Fit s | Predict s |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    methods = [(r["name"], r["metrics"], r) for r in experiments]
    methods += [(n, m, None) for n, m in report["baselines"].items()]
    for name, m, r in methods:
        budget = m["budget_1pct"]
        fit = f"{r['fit_seconds']:.2f}" if r else "—"
        score = f"{r['prediction_seconds']:.2f}" if r else "—"
        lines.append(
            f"| {name} | {m['average_precision']:.8f} | {m['roc_auc']:.6f} | "
            f"{budget['true_positives']} | {percentage(budget['precision'])} | "
            f"{percentage(budget['recall'])} | {fit} | {score} |"
        )
    lines += [
        "",
        "## Matched ablation comparisons",
        "",
        "These compare identical default model settings, so they do not "
        "confound history/payment-format changes with hyperparameter changes.",
        "",
        "| Family | Current AP | History AP | History AP gain | "
        "Current no-format AP | History no-format AP | "
        "History payment-format AP difference |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for family in ("lr", "lightgbm"):
        setting = 1.0 if family == "lr" else 15
        aps = {
            r["variant"]: r["metrics"]["average_precision"]
            for r in experiments
            if r["family"] == family and r["setting"] == setting
        }
        lines.append(
            f"| {family} | {aps['current']:.8f} | {aps['history']:.8f} | "
            f"{aps['history'] - aps['current']:+.8f} | "
            f"{aps['current_no_format']:.8f} | {aps['history_no_format']:.8f} | "
            f"{aps['history'] - aps['history_no_format']:+.8f} |"
        )
    lines += [
        "",
        "History gain and format reliance are empirical associations in "
        "this synthetic dataset. A positive format difference is not evidence "
        "that any payment method is inherently suspicious. No configuration "
        "was added after reviewing these outcomes.",
        "",
        "## Precision@K and Recall@K",
        "",
        "| Method | K | True positives | Precision@K | Recall@K |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, m, _ in methods:
        for k in m["at_k"]:
            lines.append(
                f"| {name} | {k['k']:,} | {k['true_positives']} | "
                f"{percentage(k['precision'])} | {percentage(k['recall'])} |"
            )
    lines += [
        "",
        "## Selected numeric thresholds",
        "",
        "Thresholds retain complete score tiers within the 1% cap. Ranking "
        "budgets above may split ties. Frozen rules keep their original "
        "score≥2 policy: 6,912 alerts, 21 true alerts, 0.3038% precision, "
        "2.0270% recall. Their score and weights were not changed.",
        "",
        "| Experiment | Threshold (≥) | Alerts | True alerts | Precision | Recall |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in experiments:
        m = r["metrics"]
        lines.append(
            f"| {r['name']} | {m['threshold']:.17g} | {m['alerts']:,} | "
            f"{m['true_alerts']} | {percentage(m['alert_precision'])} | "
            f"{percentage(m['alert_recall'])} |"
        )
    lines += [
        "",
        "## Computation and fit diagnostics",
        "",
        f"The completed run took {report['elapsed_seconds']:.3f} seconds. "
        f"Python process lifetime peak RSS was {report['peak_rss_mib']:.2f} MiB. "
        "This is a local measurement, not a benchmark or server memory measure. "
        "Fit and prediction times exclude preprocessing; shared preprocessing "
        "is listed once per variant below.",
        "",
        "| Variant | Preprocessing s | Encoded columns |",
        "| --- | --- | --- |",
    ]
    for variant in ("current", "current_no_format", "history", "history_no_format"):
        r = next(r for r in experiments if r["variant"] == variant)
        lines.append(
            f"| {variant} | {r['preprocessing_seconds']:.3f} | "
            f"{len(r['feature_names'])} |"
        )
    lines += [
        "",
        "| Experiment | Iterations (LR) | Fit warnings |",
        "| --- | --- | --- |",
    ]
    for r in experiments:
        lines.append(
            f"| {r['name']} | {r.get('iterations', 'fixed 120 trees')} | "
            f"{'; '.join(' '.join(w.split()) for w in r['warnings']) or 'None'} |"
        )
    lines += [
        "",
        "## Score saturation diagnostic",
        "",
        "All five tested LightGBM configurations place more than 1% of rows "
        "at exactly 1.0. A whole-tier numeric cutoff therefore alerts zero "
        "rows under the cap. Their exact-budget results select an arbitrary "
        "hashed subset of the top tie, and probability-scale saturation "
        "collapses ranking resolution. These fits are not recommended. "
        "Investigating stabilization or raw-margin ranking would require a "
        "separately declared development experiment; no such retuning was done.",
        "",
        "| Experiment | Scores exactly 0 | Scores exactly 1 | Distinct scores |",
        "| --- | --- | --- | --- |",
    ]
    diagnostics = {}
    with duckdb.connect() as db:
        for r in experiments:
            db.read_parquet(
                str(directory / r["name"] / "validation.parquet")
            ).create_view("scores", replace=True)
            zero, one, distinct = db.execute(
                "SELECT count(*) FILTER(WHERE score=0), "
                "count(*) FILTER(WHERE score=1), count(DISTINCT score) FROM scores"
            ).fetchone()
            diagnostics[r["name"]] = {
                "score_zero": zero,
                "score_one": one,
                "distinct_scores": distinct,
            }
            lines.append(f"| {r['name']} | {zero:,} | {one:,} | {distinct:,} |")
    (directory / "score_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n"
    )
    importance = best.get("gain_importance", best.get("coefficients", {}))
    lines += [
        "",
        "## Selected model interpretation",
        "",
        "Largest gain importances or absolute LR coefficients. Numeric inputs "
        "are standardized; one-hot categories and missingness flags are unscaled. "
        "Correlated counts and flags make individual coefficients non-unique "
        "interpretations, not causal effects or independent evidence:",
        "",
        "| Encoded feature | Value |",
        "| --- | --- |",
    ]
    for name, value in sorted(
        importance.items(), key=lambda p: abs(p[1]), reverse=True
    )[:12]:
        lines.append(f"| {name} | {value:.6g} |")
    lines += [
        "",
        "## Limitations and next decision",
        "",
        "Review the chosen model, operational availability of receiving-side "
        "attributes, 1% workload budget, and payment-format ablation before "
        "authorizing final evaluation. Keep the chosen preprocessing/model "
        "and threshold fixed. No calibration has been fitted; class-weighted "
        "scores are not calibrated probabilities. Alerting is a request for "
        "review, not proof of laundering.",
        "",
        "The selected budget includes "
        f"{best['metrics']['alerts'] - best['metrics']['true_alerts']:,} "
        "negative-labeled transactions. C=0.1 catches two more positives at the "
        "same budget, but C=1 wins the predeclared AP objective. Review whether "
        "that objective matches operational priorities before future development. "
        "All ten configurations used the same validation period for comparison. "
        "There are no confidence intervals or multiple-selection corrections. "
        "History is left-censored and rolls across chronological splits under "
        "the immediate-arrival assumption. Synthetic shortcuts and the "
        "previously documented post–September 10 shift limit generalization. "
        "Earlier EDA/rules results mean future evaluation remains a development "
        "holdout rather than an untouched external validation set.",
        "",
        f"Feature checksum remained `{report['feature_sha256_unchanged']}`. "
        "Plan, per-experiment parameters, preprocessing, coefficients/importance, "
        "model/prediction checksums, and label-access records are saved under "
        f"`{directory}`. Read [the contract](supervised_learning.md) and "
        "[verification](ml_verification.md).",
        "",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines))
    (destination.parent / "ml_experiment_plan_v1.json").write_text(
        json.dumps(plan, indent=2) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=Path("data/ml/supervised-v1"))
    parser.add_argument("--output", type=Path, default=Path("docs/ml_report.md"))
    args = parser.parse_args()
    render(args.artifacts, args.output)


if __name__ == "__main__":
    main()
