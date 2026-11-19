"""Fixed, label-free SHAP sample and additive annotations of an existing case report."""

import argparse
import hashlib
import json
import time
import tracemalloc
from pathlib import Path

import duckdb
import numpy as np

from mulegraph.explanations import ExplanationService
from mulegraph.features import sha256_file

SEED = "mulegraph-shap-v1"
SAMPLE_SIZE = 256


def run(output: Path, root: Path = Path(".")) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    began = time.perf_counter()
    service = ExplanationService(root)
    initialization = time.perf_counter() - began
    with duckdb.connect(config={"threads": 2, "memory_limit": "128MB"}) as db:
        sample = [
            r[0]
            for r in db.execute(
                "SELECT source_row FROM read_parquet(?) "
                "ORDER BY sha256(? || CAST(source_row AS VARCHAR)),source_row LIMIT ?",
                [
                    str(
                        root
                        / "data/ml/lightgbm-stable-v1/history_none/validation.parquet"
                    ),
                    SEED + ":",
                    SAMPLE_SIZE,
                ],
            ).fetchall()
        ]
    if len(sample) != SAMPLE_SIZE:
        raise ValueError("Incomplete fixed validation sample")
    tracemalloc.start()
    began = time.perf_counter()
    explanations = []
    for offset in range(0, SAMPLE_SIZE, 128):
        explanations.extend(service.explain(sample[offset : offset + 128]))
    elapsed = time.perf_counter() - began
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    if any(e["status"] != "EXPLAINED" for e in explanations):
        raise ValueError("Validation sample has unexplained rows")
    # Replay a fixed small subset without reselecting based on scores or findings.
    repeated = service.explain(sample[:16])
    previous = {e["source_row"]: e for e in explanations}
    if any(e != previous[e["source_row"]] for e in repeated):
        raise ValueError("Explanation replay mismatch")
    values = np.array(
        [[c["raw_contribution"] for c in e["contributions"]] for e in explanations]
    )
    importance = [
        {
            "feature": name,
            "mean_absolute_raw_shap": float(np.abs(values[:, i]).mean()),
            "mean_signed_raw_shap": float(values[:, i].mean()),
        }
        for i, name in enumerate(service.names)
    ]
    importance.sort(key=lambda x: (-x["mean_absolute_raw_shap"], x["feature"]))
    grouped_names = sorted(explanations[0]["grouped_contributions"])
    grouped = [
        {
            "feature": name,
            "mean_absolute_grouped_raw_shap": float(
                np.mean([abs(e["grouped_contributions"][name]) for e in explanations])
            ),
        }
        for name in grouped_names
    ]
    grouped.sort(key=lambda x: (-x["mean_absolute_grouped_raw_shap"], x["feature"]))
    case_path = root / "data/cases/v1/case-4.json"
    case = json.loads(case_path.read_text())
    # Availability-stratified demonstration, not a score-based or label-based search.
    selected = [t["source_row"] for t in case["transactions"] if t["score"] is None][
        :4
    ] + [t["source_row"] for t in case["transactions"] if t["score"] is not None][:12]
    began = time.perf_counter()
    annotated = service.annotate_case_report(case, selected)
    annotation_seconds = time.perf_counter() - began
    assert {
        k: v for k, v in annotated.items() if k != "transaction_explanations"
    } == case
    (output / "sample_explanations.json").write_text(
        json.dumps(explanations, indent=2) + "\n"
    )
    (output / "annotated_case.json").write_text(json.dumps(annotated, indent=2) + "\n")
    # Explicit missing-source and training checks, no new predictions for either.
    missing = service.explain([1, 99999999])
    report = {
        "version": "explanation-v1",
        "method": "LightGBM native TreeSHAP",
        "model": service.scores.model,
        "model_sha256": service.freeze["sources_sha256"]["stable"][
            "history_none/model.joblib"
        ],
        "feature_sha256": service.freeze["feature_sha256"],
        "uv_lock_sha256": sha256_file(root / "uv.lock"),
        "sample": {
            "split": "validation",
            "rows": SAMPLE_SIZE,
            "seed": SEED,
            "selection": "lowest SHA-256(seed + colon + decimal source_row)",
            "source_ids_sha256": hashlib.sha256(
                json.dumps(sample).encode()
            ).hexdigest(),
        },
        "encoded_features": len(service.names),
        "raw_baseline": explanations[0]["base_value"],
        "max_additivity_error": max(e["additivity_error"] for e in explanations),
        "max_saved_score_error": max(e["saved_score_error"] for e in explanations),
        "baseline_spread": max(e["base_value"] for e in explanations)
        - min(e["base_value"] for e in explanations),
        "initialization_seconds": initialization,
        "sample_seconds": elapsed,
        "sample_python_peak_bytes": peak,
        "replayed_rows": len(repeated),
        "annotation_seconds": annotation_seconds,
        "annotation_status_counts": {
            status: sum(
                e["status"] == status
                for e in annotated["transaction_explanations"]["items"]
            )
            for status in ("EXPLAINED", "UNSCORED_TRAINING_PERIOD")
        },
        "case_membership_scores_unchanged": True,
        "missing_checks": [e["status"] for e in missing],
        "encoded_importance": importance,
        "grouped_importance": grouped,
    }
    (output / "aggregate.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("encoded_importance", "grouped_importance")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
