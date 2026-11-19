"""Render the saved, finalized baseline results without rescoring or fitting."""

import argparse
import json
from pathlib import Path

from mulegraph.eda_report import table

NAMES = {
    "risk_score": "Main rules",
    "ach_score": "ACH only",
    "currency_tail_score": "Currency tail",
    "constant_score": "Constant/no alerts",
}


def percent(value: float | None) -> str:
    return "undefined" if value is None else f"{100 * value:.4f}%"


def render(directory: Path, path: Path) -> None:
    definition = json.loads((directory / "rules.json").read_text())
    calibration = json.loads((directory / "calibration.json").read_text())
    holdout = json.loads((directory / "holdout" / "evaluation.json").read_text())
    results = {
        "validation": calibration["validation"],
        "test": holdout["test"],
        "stress": holdout["stress"],
    }
    risk = results["validation"]["risk_score"]
    training_rows = sum(
        p["observations"]
        for p in definition["profile"]["currencies"]
        if p["role"] == "sender"
    )
    prediction_rows = sum(r["risk_score"]["rows"] for r in results.values())
    text = [
        "# Milestone 3B: measured rules baseline results",
        "The baseline completed calibration and one frozen holdout evaluation. "
        "It is weak on the primary distribution: treat it as a transparent benchmark, "
        "not a deployable detector or evidence of criminal conduct. Source data and "
        "historical-v1 features remain unchanged; no ML model was trained.",
        "## Validation outcome",
        f"The selected alert threshold is **score ≥ {definition['threshold']}**. "
        f"It flags {risk['alerts']:,} validation transactions "
        f"({percent(risk['alert_rate'])}), including {risk['true_alerts']:,} positive "
        f"labels and {risk['false_alerts']:,} negative labels. Precision is "
        f"{percent(risk['precision'])}; recall is {percent(risk['recall'])}. "
        f"AP is {risk['average_precision']:.8f}, versus the prevalence baseline "
        f"{risk['prevalence']:.8f}. This is only "
        f"{risk['average_precision'] / risk['prevalence']:.3f}× baseline AP.",
        "ACH-only has substantially higher primary-period AP, but flags far more "
        "transactions. It exposes a synthetic-dataset association rather than "
        "establishing ACH as inherently suspicious. The main rules intentionally "
        "do not include payment format. Absolute stress AP must be judged against "
        "its much higher prevalence, not compared directly with primary AP.",
        "## Population and baselines",
        table(
            ["Split", "Rows", "Positive labels", "Prevalence / constant AP"],
            [
                [
                    split,
                    f"{r['risk_score']['rows']:,}",
                    r["risk_score"]["positives"],
                    f"{r['risk_score']['prevalence']:.8f}",
                ]
                for split, r in results.items()
            ],
        ),
        "AP below is a fraction in [0,1]. Precision/recall and alert rates are "
        "percentages. Undefined precision means no alerts. Baseline alert policies "
        "are fixed independently of the main detector's validation budget.",
        table(
            [
                "Split",
                "Method",
                "AP",
                "Alerts",
                "True alerts",
                "False alerts",
                "Alert rate",
                "Precision",
                "Recall",
            ],
            [
                [
                    split,
                    label,
                    f"{r[score]['average_precision']:.8f}",
                    f"{r[score]['alerts']:,}",
                    r[score]["true_alerts"],
                    f"{r[score]['false_alerts']:,}",
                    percent(r[score]["alert_rate"]),
                    percent(r[score]["precision"]),
                    percent(r[score]["recall"]),
                ]
                for split, r in results.items()
                for score, label in NAMES.items()
            ],
        ),
        "The validation 1% alert-rate cap is a selection constraint, not a guarantee "
        "on new periods. The frozen threshold exceeds that rate on primary test "
        "and stress; it was not adjusted after observing either result. Stress is "
        "entirely ACH, so the ACH score there has exactly the same AP as a constant "
        "score. No split results are pooled.",
        "## Precision@K and Recall@K",
        "Ranking uses descending score and a fixed label-free SHA-256 tie order. "
        "AP groups entire score ties; the @K metrics use one reproducible arbitrary "
        "order inside them. Strong ties limit conclusions from small K. K is capped "
        "at split size, and zero-score transactions may enter a top-K budget.",
        table(
            [
                "Split",
                "Method",
                "Requested K",
                "Effective K",
                "Positives in K",
                "Precision@K",
                "Recall@K",
            ],
            [
                [
                    split,
                    label,
                    k["requested_k"],
                    k["effective_k"],
                    k["true_positives"],
                    percent(k["precision"]),
                    percent(k["recall"]),
                ]
                for split, r in results.items()
                for score, label in NAMES.items()
                for k in r[score]["at_k"]
            ],
        ),
        "## Rule investigation on validation",
        "These diagnostics describe individual triggers, not independent evidence "
        "and not a second round of parameter selection. Amount-spike rules have "
        "two points; all other rules have one. Reasons may overlap within an alert.",
        table(
            ["Reason code", "Triggers", "Positive labels", "Trigger precision"],
            [
                [code, r["triggers"], r["positives"], percent(r["precision"])]
                for code, r in results["validation"]["rule_triggers"].items()
            ],
        ),
        "Receiver amount spikes and sender direction changes concentrate more "
        "validation positives than several other individual triggers, but their "
        "sample sizes are small. No weights were changed after seeing this. "
        "Frequency bursts and large transfers often flag legitimate-looking "
        "synthetic activity. The full score misses most positive labels.",
        table(
            ["Endpoint", "Mature training rows", "High-activity cutoff (> threshold)"],
            [
                [role, p["eligible_training_rows"], p["cutoff"]]
                for role, p in definition["profile"]["activity"].items()
            ],
        ),
        "The sender reference is especially high and that rule never triggers in "
        "validation. These quantiles are transaction-weighted: busy accounts "
        "contribute many observations. This is a limitation of this simple reference "
        "design, preserved in the frozen baseline rather than corrected on holdouts.",
        "## Cold-start and currency coverage",
        table(
            [
                "Split",
                "Endpoint",
                "Fewer than 5 currency observations",
                "Unsupported currency",
            ],
            [
                [
                    split,
                    role,
                    r["coverage_flags"][f"{role}_limited_currency_history"],
                    r["coverage_flags"][f"{role}_unsupported_currency"],
                ]
                for split, r in results.items()
                for role in ("sender", "receiver")
            ],
        ),
        "Limited currency history suppresses the corresponding amount-spike rule, "
        "not every possible alert. Other endpoint evidence may remain available. "
        "Currency references and all constants are retained in "
        "[the frozen aggregate definition](rules_definition_v1.json); there are no "
        "currency conversions or future-derived imputations.",
        "## Threshold selection audit",
        "Only validation labels selected this integer operating threshold. The "
        "predeclared objective was maximum F2 under a 1% alert-rate cap, with ties "
        "favoring higher thresholds. A no-alert result was allowed.",
        table(
            ["Threshold", "Alerts", "Positive alerts", "F2", "Within cap"],
            [
                [
                    r["threshold"],
                    r["alerts"],
                    r["true_positives"],
                    f"{r['f2']:.8f}",
                    r["eligible"],
                ]
                for r in definition["selection"]["candidates"]
            ],
        ),
        f"Finalized at **{definition['finalized_at']}**. Frozen rule file SHA-256: "
        f"`{calibration['rules_sha256']}`. Holdout evaluation records the same digest.",
        table(
            ["Labels accessed", "Rows", "Retrieval completed (UTC)"],
            [
                [r["split"], r["rows"], r["retrieved_at"]]
                for r in [calibration["label_access"], *holdout["label_access"]]
            ],
        ),
        "Validation export completion precedes finalization. Test and stress export "
        "completion occurs afterward. The staged integration test also checks access "
        "sequence and rejects evaluation without finalized definitions, repeated "
        "holdout evaluation, and recalibration into an existing directory.",
        "## Execution and verification",
        f"Calibration completed in {calibration['elapsed_seconds']} seconds; "
        f"frozen test/stress evaluation completed in {holdout['elapsed_seconds']} "
        "seconds. These are local execution measurements, not benchmarks. "
        f"Training uses {training_rows:,} reference rows; predictions cover all "
        f"{prediction_rows:,} "
        "validation/test/stress rows. Training predictions are intentionally absent "
        "because full-training references would be retrospective for early rows.",
        "Actual test, checksum, and persisted-prediction verification results are "
        "recorded in [the verification log](rules_verification.md). "
        "Rendering this report does not rerun tests, score transactions, "
        "or access labels.",
        "Prediction files and definitions live under ignored `data/rules/rules-v1/`. "
        "No row-level labels are stored in predictions; disposable label exports "
        "were removed. See [implementation and commands](rules_baseline.md).",
        "## Limitations and review decisions",
        "No execution blocker remains, but the low precision and recall make this "
        "unsuitable as a standalone operational detector. Review the illustrative "
        "1% budget, F2 objective, and investigator capacity before deployment. "
        "Rules and weights are heuristic and correlated; the score is not a "
        "probability. Binary labels come from synthetic generation, and a trigger "
        "is not proof of wrongdoing.",
        "The immediate-arrival/current-attribute assumptions and left-censored "
        "history remain unchanged. Validation metrics are selected on validation; "
        "prior EDA already inspected aggregate holdout labels, so these are "
        "development holdouts. Stress prevalence and composition are exceptional. "
        "Transactions and accounts are dependent, and no independent-event confidence "
        "intervals are claimed. No holdout-driven rule, weight, threshold, or tie-seed "
        "changes were made. Any future iteration needs an explicit new version and "
        "an honest evaluation protocol.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(text) + "\n")
    (path.parent / "rules_definition_v1.json").write_bytes(
        (directory / "rules.json").read_bytes()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/rules/rules-v1"))
    parser.add_argument("--report", type=Path, default=Path("docs/rules_report.md"))
    args = parser.parse_args()
    render(args.input_dir, args.report)


if __name__ == "__main__":
    main()
