"""Reproducible label-free assessment of existing saved investigation reports."""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from mulegraph.evidence_quality import assess_evidence


def run(paths: list[Path], output: Path) -> dict:
    """Assess saved reports without database, model, or label access."""
    if not 1 <= len(paths) <= 10:
        raise ValueError("Use one to ten bounded example reports")
    results = []
    for path in paths:
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Saved report exceeds 32 MiB")
        raw = path.read_bytes()
        report = json.loads(raw)
        before = json.dumps(report, sort_keys=True)
        began = time.perf_counter()
        assessed = assess_evidence(report)
        elapsed = time.perf_counter() - began
        assert assessed == assess_evidence(report)
        assert before == json.dumps(report, sort_keys=True)
        quality = list(assessed["findings"].values())
        handoffs = [h for q in quality for h in q["handoffs"]]
        results.append(
            {
                "example": path.name,
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "transactions": len(report["transactions"]),
                "cases": len(report["cases"]),
                "witnesses": len(quality),
                "patterns": dict(
                    Counter(f["pattern_type"] for f in report["findings"])
                ),
                "descriptors": dict(
                    Counter(d for q in quality for d in q["descriptors"])
                ),
                "handoff_observations": len(handoffs),
                "distinct_handoff_pairs": len(
                    {(h["incoming_source"], h["outgoing_source"]) for h in handoffs}
                ),
                "amount_relations": dict(
                    Counter(h["amount_relation"] for h in handoffs)
                ),
                "gap_seconds_min": min(
                    (h["elapsed_seconds"] for h in handoffs), default=None
                ),
                "gap_seconds_max": max(
                    (h["elapsed_seconds"] for h in handoffs), default=None
                ),
                "seconds": elapsed,
                "deterministic": True,
                "original_unchanged": True,
            }
        )
    result = {
        "version": "evidence-quality-v1",
        "examples": results,
        "selection": (
            "Caller-supplied saved reports; document the selection protocol separately"
        ),
        "counts_note": (
            "Handoff observations overlap across witnesses; not independent incidents."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.reports, args.output), indent=2))


if __name__ == "__main__":
    main()
