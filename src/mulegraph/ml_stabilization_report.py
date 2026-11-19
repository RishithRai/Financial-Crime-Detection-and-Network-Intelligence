"""Label-free audit and aggregate reporting for the fixed stabilization run."""

import argparse
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

from mulegraph.features import sha256_file
from mulegraph.ml_inference import score_batch
from mulegraph.ml_stabilization import score_diagnostics, validate_plan
from mulegraph.ml_training import batches, load_artifact
from mulegraph.rules_baseline import open_features, write_json


def verify(directory: Path, features: Path, original: Path) -> dict:
    start = time.perf_counter()
    plan = json.loads((directory / "plan.json").read_text())
    results = json.loads((directory / "results.json").read_text())
    validate_plan(plan, original)
    if sha256_file(directory / "plan.json") != results["plan_sha256"]:
        raise ValueError("Plan digest changed")
    expected = [c["name"] for c in plan["experiments"]]
    if [r["name"] for r in results["experiments"]] != expected:
        raise ValueError("Experiment coverage mismatch")
    checks = []
    with duckdb.connect() as db, threadpool_limits(limits=2):
        manifest = open_features(db, features)
        if (
            manifest["file_sha256"] != plan["feature_sha256"]
            or manifest["dataset"] != plan["dataset"]
        ):
            raise ValueError("Feature provenance mismatch")
        ids = db.execute(
            "SELECT source_row FROM features WHERE split='validation' "
            "ORDER BY source_row"
        ).fetchnumpy()["source_row"]
        if len(ids) != len(np.unique(ids)) or len(ids) != results["frozen_lr"]["rows"]:
            raise ValueError("Validation coverage mismatch")
        for result in results["experiments"]:
            dest = directory / result["name"]
            if json.loads((dest / "metadata.json").read_text()) != result:
                raise ValueError("Metadata mismatch")
            artifact = load_artifact(dest)
            if (
                artifact["threshold"] != result["metrics"]["threshold"]
                or artifact["preprocessor"].training_rows != results["training_rows"]
            ):
                raise ValueError("Threshold/preprocessing mismatch")
            path = dest / "validation.parquet"
            if sha256_file(path) != result["predictions_sha256"]:
                raise ValueError("Prediction checksum mismatch")
            table = pq.read_table(path)
            if table.column_names != ["source_row", "score"]:
                raise ValueError("Unexpected prediction schema")
            np.testing.assert_array_equal(table["source_row"].to_numpy(), ids)
            saved = table["score"].to_numpy()
            offset = alerts = 0
            margins = []
            for batch in batches(db, result["variant"], "validation"):
                score, alert = score_batch(artifact, batch)
                np.testing.assert_array_equal(
                    score, saved[offset : offset + len(batch)]
                )
                x = artifact["preprocessor"].transform(batch)
                margins.append(artifact["model"].booster_.predict(x, raw_score=True))
                offset += len(batch)
                alerts += int(alert.sum())
            if (
                offset != len(ids)
                or alerts != result["metrics"]["alerts"]
                or score_diagnostics(saved, np.concatenate(margins))
                != result["diagnostics"]["validation"]
            ):
                raise ValueError("Reloaded diagnostics/coverage/alerts mismatch")
            checks.append(
                {
                    "name": result["name"],
                    "rows": offset,
                    "alerts": alerts,
                    "exact_scores": True,
                }
            )
            print(f"Verified {result['name']}: {offset:,} scores", flush=True)
    report = {
        "experiments": checks,
        "label_accesses": 0,
        "originals_unchanged": True,
        "feature_sha256": plan["feature_sha256"],
        "elapsed_seconds": time.perf_counter() - start,
    }
    write_json(directory / "verification.json", report)
    return report


def render(directory: Path, destination: Path) -> None:
    r = json.loads((directory / "results.json").read_text())
    plan = json.loads((directory / "plan.json").read_text())
    methods = [("Frozen history_lr_1.0", r["frozen_lr"])] + [
        (x["name"], x["metrics"]) for x in r["experiments"]
    ]
    lines = [
        "# Milestone 4A.1: measured stabilization results",
        "",
        "All new fits use September 1–6 training and September 7–8 validation only.",
        "No test/stress labels were retrieved or evaluated. Original "
        "artifacts remain unchanged.",
        "",
        f"Training: {r['training_rows']:,} rows, "
        f"{r['training_positives']:,} positives. "
        f"Validation: {r['frozen_lr']['rows']:,} rows, "
        f"{r['frozen_lr']['positives']:,} positives "
        f"({100 * r['frozen_lr']['prevalence']:.4f}% prevalence).",
        "",
        f"The predeclared decision rule recommends **{r['recommended']}** "
        "for later final "
        "evaluation. This is a validation selection result; no final "
        "evaluation was run.",
        "",
        "## Comparable metrics",
        "",
        "AP and ROC-AUC are fractions. Precision and recall are percentages. "
        "All methods use the same exact 1% ranking budget and hashed "
        "identity tie order.",
        "",
        "| Model | AP | ROC-AUC | Budget | TP | Precision | Recall |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, m in methods:
        b = m["budget_1pct"]
        lines.append(
            f"| {name} | {m['average_precision']:.8f} | {m['roc_auc']:.8f} | "
            f"{b['k']:,} | {b['true_positives']:,} | {100 * b['precision']:.4f}% | "
            f"{100 * b['recall']:.4f}% |"
        )
    lines += [
        "",
        "| Model | K | TP | Precision@K | Recall@K |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, m in methods:
        for b in m["at_k"]:
            lines.append(
                f"| {name} | {b['k']:,} | {b['true_positives']:,} | "
                f"{100 * b['precision']:.4f}% | {100 * b['recall']:.4f}% |"
            )
    lines += [
        "",
        "## Matched payment-format ablation",
        "",
        "| Weight policy | History AP | No-format AP | AP difference |",
        "| --- | ---: | ---: | ---: |",
    ]
    for weight in ("none", "sqrt", "full"):
        a, b = [
            next(
                x["metrics"]["average_precision"]
                for x in r["experiments"]
                if x["variant"] == variant and x["weight"] == weight
            )
            for variant in ("history", "history_no_format")
        ]
        lines.append(f"| {weight} | {a:.8f} | {b:.8f} | {a - b:+.8f} |")
    lines += [
        "",
        "## Numerical stability and ties",
        "",
        "Near endpoints means ≤1e-12 or ≥1−1e-12. Raw margins are diagnostic only; "
        "probability-scale scores remain the ranking policy.",
        "",
        "| Model | Split | Raw min | Raw max | Exact 0 / 1 | Near endpoints | "
        "Unique scores | Largest tie | Top tie |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for x in r["experiments"]:
        for split, d in x["diagnostics"].items():
            lines.append(
                f"| {x['name']} | {split} | {d['raw_min']:.4f} | {d['raw_max']:.4f} | "
                f"{d['exact_zero']} / {d['exact_one']} | {d['near_endpoint']} | "
                f"{d['unique_scores']:,} | {d['largest_tie']:,} | {d['top_tie']:,} |"
            )
    lines += [
        "",
        "## Thresholds, stability and measured cost",
        "",
        "Threshold alerts preserve whole score tiers; ranking budgets "
        "above may split ties.",
        "Prediction time includes train and validation "
        "raw-margin/probability diagnostics.",
        "",
        "| Model | Threshold ≥ | Alerts | True alerts | Stable | Fit s | Predict s |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for x in r["experiments"]:
        m = x["metrics"]
        lines.append(
            f"| {x['name']} | {m['threshold']:.17g} | {m['alerts']:,} | "
            f"{m['true_alerts']:,} | {x['stable']} | {x['fit_seconds']:.2f} | "
            f"{x['prediction_seconds']:.2f} |"
        )
    lines += [
        "",
        "| Model | Trees | Max post-initial leaf | Train loss first → "
        "last | Warnings |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for x in r["experiments"]:
        loss = x["training_logloss"]
        lines.append(
            f"| {x['name']} | {x['trees']} | {x['max_post_initial_leaf']:.6f} | "
            f"{loss[0]:.6f} → {loss[-1]:.6f} | {', '.join(x['warnings']) or 'None'} |"
        )
    lines += [
        "",
        "Training logloss is the unweighted training diagnostic; weighted objectives "
        "need not minimize it. Every full trace is saved, with no early stopping.",
        "",
        f"Total runtime: {r['elapsed_seconds']:.3f} seconds; process peak RSS: "
        f"{r['peak_rss_mib']:.2f} MiB. These local measurements are not benchmarks.",
        "Shared preprocessing seconds: "
        + ", ".join(f"{k}={v:.3f}" for k, v in r["preprocessing_seconds"].items())
        + ".",
        "",
        "## Provenance and limitations",
        "",
        f"Plan saved at `{plan['created_at']}`; run completed at "
        f"`{r['completed_at']}`.",
        "The plan predates both label exports:",
    ]
    for a in r["label_access"]:
        lines.append(
            f"- {a['split']}: {a['rows']:,} rows, completed `{a['completed_at']}`."
        )
    lines += [
        "",
        f"Plan SHA-256: `{r['plan_sha256']}`.",
        f"Historical feature SHA-256: `{r['feature_sha256']}`.",
        "",
        "All original artifact hashes match, preprocessing matches the train-fitted "
        "originals, and every new saved validation score reproduced "
        "exactly on model reload.",
        "",
        "This fixed six-fit follow-up reuses development validation already used for "
        "model selection. Improvements are not unbiased estimates or "
        "significance claims. "
        "The regularization changes form a combined stabilization "
        "intervention; this study "
        "does not isolate the causal effect of each setting. Payment-format reliance, "
        "synthetic-data shortcuts, left-censored histories, and immediate attribute "
        "availability remain limitations. No calibration was fitted or "
        "tested, including "
        "for unweighted models. Scores are review priorities, not proof of laundering.",
        "",
        "See [the predeclared contract](ml_stabilization.md) and "
        "[verification](ml_stabilization_verification.md).",
    ]
    destination.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts", type=Path, default=Path("data/ml/lightgbm-stable-v1")
    )
    parser.add_argument("--original", type=Path, default=Path("data/ml/supervised-v1"))
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--report", type=Path, default=Path("docs/ml_stabilization_report.md")
    )
    args = parser.parse_args()
    if args.verify:
        if args.features_dir is None:
            parser.error("--features-dir is required for verification")
        verify(args.artifacts, args.features_dir, args.original)
    render(args.artifacts, args.report)


if __name__ == "__main__":
    main()
