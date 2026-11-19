"""Bounded native TreeSHAP explanations of the frozen selected LightGBM."""

import copy
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
from scipy.special import expit
from threadpoolctl import threadpool_limits

from mulegraph.cases import missing_reason
from mulegraph.features import definition, sha256_file
from mulegraph.graph import COLUMNS, Transfer
from mulegraph.investigation import reference
from mulegraph.investigation_scores import FrozenScores
from mulegraph.ml import allowlist
from mulegraph.ml_stabilization import dependencies
from mulegraph.ml_training import load_artifact

MAX_ROWS = 128
RAW_TOLERANCE = 1e-8
SCORE_TOLERANCE = 1e-12


def checked_contributions(
    model, matrix: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """LightGBM's exact path-dependent TreeSHAP; last column is the baseline."""
    with threadpool_limits(limits=2):
        booster = model.booster_
        shap = np.asarray(booster.predict(matrix, pred_contrib=True, num_threads=2))
        raw = np.asarray(booster.predict(matrix, raw_score=True, num_threads=2))
        scores = np.asarray(model.predict_proba(matrix))[:, 1]
    verify_additivity(shap, raw, scores, matrix.shape[1])
    return shap, raw, scores


def verify_additivity(
    shap: np.ndarray, raw: np.ndarray, scores: np.ndarray, width: int
) -> None:
    if (
        shap.shape != (len(raw), width + 1)
        or scores.shape != raw.shape
        or not all(np.isfinite(a).all() for a in (shap, raw, scores))
    ):
        raise ValueError("Invalid SHAP dimensions or nonfinite output")
    if not np.allclose(shap.sum(axis=1), raw, rtol=0, atol=RAW_TOLERANCE):
        raise ValueError("SHAP raw-margin additivity failed")
    if not np.allclose(expit(raw), scores, rtol=0, atol=SCORE_TOLERANCE):
        raise ValueError("Raw margin and review score disagree")


def feature_description(name: str, row: dict) -> tuple[str, str, object]:
    """Decode feature identity without inventing causal/counterfactual effects."""
    if "=" in name:
        base, category = name.split("=", 1)
        return base, f"{base.replace('_', ' ')} indicator for {category}", row[base]
    if name.endswith("__missing"):
        base = name.removesuffix("__missing")
        return base, f"Missing-history indicator: {base.replace('_', ' ')}", row[base]
    descriptions = {
        "amount_paid": f"Amount paid in {row['payment_currency']}",
        "amount_received": f"Amount received in {row['receiving_currency']}",
        "self_transfer": "Sender and receiver are the same composite account",
        "cross_currency": "Payment and receiving currencies differ",
    }
    if name in descriptions:
        return name, descriptions[name], row[name]
    role, metric = name.split("_", 1)
    terms = {
        "history_count": "all earlier incident transactions",
        "sent_count": "earlier outgoing transactions",
        "received_count": "earlier incoming transactions",
        "count_1h": "incident transactions in the preceding hour",
        "count_24h": "incident transactions in the preceding 24 hours",
        "unique_counterparties": "distinct earlier counterparties",
        "seconds_since_last": "seconds since preceding activity",
        "history_age_seconds": "seconds of observed history (not account age)",
        "mean_gap_seconds": "mean seconds between earlier events",
        "frequency_1h": "incident transactions per hour over the preceding hour",
        "frequency_24h": "incident transactions per hour over the preceding 24 hours",
    }
    if metric.startswith("currency_"):
        direction = "outgoing" if role == "sender" else "incoming"
        currency = row["payment_currency" if role == "sender" else "receiving_currency"]
        terms.update(
            {
                "currency_history_count": f"earlier {direction} "
                f"transactions in {currency}",
                "currency_count_1h": f"{direction} transactions in {currency} "
                "in the preceding hour",
                "currency_count_24h": f"{direction} transactions in {currency} "
                "in the preceding 24 hours",
                "currency_history_sum": f"earlier {direction} amount in {currency}",
                "currency_sum_1h": f"{direction} amount in {currency} "
                "in the preceding hour",
                "currency_sum_24h": f"{direction} amount in {currency} "
                "in the preceding 24 hours",
            }
        )
    return name, f"{role.title()}: {terms[metric]}", row[name]


def format_explanation(
    row: dict,
    names: list[str],
    encoded: np.ndarray,
    shap: np.ndarray,
    raw: float,
    score: float,
    saved: float,
) -> dict:
    contributions = []
    grouped = defaultdict(float)
    for name, x, value in zip(names, encoded, shap[:-1], strict=True):
        base, label, observed = feature_description(name, row)
        value = float(value)
        grouped[base] += value
        direction = (
            "increases" if value > 0 else "decreases" if value < 0 else "neutral"
        )
        contributions.append(
            {
                "feature": name,
                "source_feature": base,
                "description": label,
                "observed_value": None if observed is None else str(observed),
                "encoded_value": float(x),
                "raw_contribution": value,
                "direction": direction,
                "explanation": f"{label}: {direction} the raw model margin "
                f"relative to the TreeSHAP baseline ({value:+.6f}).",
            }
        )
    ordered = sorted(
        contributions, key=lambda c: (-abs(c["raw_contribution"]), c["feature"])
    )
    return {
        "source_row": row["source_row"],
        "occurred_at": row["occurred_at"].isoformat(),
        "status": "EXPLAINED",
        "saved_review_score": saved,
        "recomputed_review_score": score,
        "raw_margin": raw,
        "base_value": float(shap[-1]),
        "additivity_error": abs(float(shap.sum()) - raw),
        "saved_score_error": abs(score - saved),
        "contributions": contributions,
        "grouped_contributions": dict(sorted(grouped.items())),
        "top_increasing": [c for c in ordered if c["raw_contribution"] > 0][:5],
        "top_decreasing": [c for c in ordered if c["raw_contribution"] < 0][:5],
    }


class ExplanationService:
    """Trusted local frozen artifact reader; no labels and no fitting paths."""

    def __init__(self, root: Path = Path(".")) -> None:
        self.root = root
        self.freeze = json.loads((root / "docs/ml_holdout_freeze_v1.json").read_text())
        self.scores = FrozenScores.saved(root)
        self.features = root / "data/features/historical-v1" / self.scores.fingerprint
        if dependencies() != self.freeze["dependencies"]:
            raise ValueError("Frozen scoring dependency versions changed")
        for name, digest in self.freeze["implementation"].items():
            if sha256_file(root / "src/mulegraph" / name) != digest:
                raise ValueError("Frozen scoring implementation changed")
        self.verify_features()
        directory = root / "data/ml/lightgbm-stable-v1/history_none"
        self.artifact = load_artifact(directory)
        meta = json.loads((directory / "metadata.json").read_text())
        prep = self.artifact["preprocessor"]
        if (
            prep.variant != "history"
            or self.artifact["model"].get_params() != meta["model_parameters"]
            or self.artifact["threshold"] != self.freeze["thresholds"]["lightgbm"]
            or self.artifact["model"].n_features_in_ != len(prep.names)
        ):
            raise ValueError("Frozen model/preprocessor/threshold mismatch")
        self.names = prep.names

    def verify_features(self) -> None:
        if (
            sha256_file(self.features / "manifest.json")
            != self.freeze["feature_manifest_sha256"]
            or sha256_file(self.features / "features.parquet")
            != self.freeze["feature_sha256"]
        ):
            raise ValueError("Historical feature checksum mismatch")
        manifest = json.loads((self.features / "manifest.json").read_text())
        if json.loads(json.dumps(definition())) != manifest["definition"]:
            raise ValueError("Historical feature implementation/dependencies changed")

    def explain(
        self, source_ids: list[int], *, cutoff: datetime | None = None
    ) -> list[dict]:
        if (
            not source_ids
            or len(source_ids) > MAX_ROWS
            or len(set(source_ids)) != len(source_ids)
            or any(type(i) is not int or i < 1 for i in source_ids)
        ):
            raise ValueError("Require 1–128 distinct positive source IDs")
        if cutoff is not None and (
            not isinstance(cutoff, datetime) or cutoff.tzinfo is not None
        ):
            raise ValueError("Cutoff must be a naive source timestamp")
        # Rehash immutable inputs per request; no stale-cache assumption.
        self.verify_features()
        nums, cats = allowlist("history")
        columns = list(
            dict.fromkeys(
                [
                    *nums,
                    *cats,
                    *[x.strip() for x in COLUMNS.split(",")],
                    "dataset_fingerprint",
                ]
            )
        )
        with duckdb.connect(config={"threads": 2, "memory_limit": "128MB"}) as db:
            db.register("requested", pa.table({"source_row": source_ids}))
            query = "SELECT " + ",".join('f."' + c + '"' for c in columns)
            table = db.execute(
                query + " FROM read_parquet(?) f JOIN requested r "
                "USING(source_row) ORDER BY f.source_row LIMIT 129",
                [str(self.features / "features.parquet")],
            ).to_arrow_table()
        records = table.to_pylist()
        if len({r["source_row"] for r in records}) != len(records):
            raise ValueError("Duplicate feature identities")
        transfers = []
        for r in records:
            if (
                r["dataset_id"] != self.scores.dataset_id
                or r["dataset_fingerprint"] != self.scores.fingerprint
            ):
                raise ValueError("Feature dataset mismatch")
            if cutoff is not None and r["occurred_at"] >= cutoff:
                raise ValueError("Transaction is not strictly before cutoff")
            transfers.append(
                Transfer(**{k: r[k] for k in Transfer.__dataclass_fields__})
            )
        saved = self.scores.lookup(transfers, self.scores.fingerprint)
        eligible = [i for i, r in enumerate(records) if r["source_row"] in saved]
        result = {
            i: {"source_row": i, "status": "SOURCE_NOT_FOUND"} for i in source_ids
        }
        for t in transfers:
            result[t.source_row] = {
                "source_row": t.source_row,
                "occurred_at": t.occurred_at.isoformat(),
                "status": missing_reason(t),
                "saved_review_score": None,
            }
        if eligible:
            subset = table.take(pa.array(eligible))
            matrix = self.artifact["preprocessor"].transform(subset)
            shap, raw, scores = checked_contributions(self.artifact["model"], matrix)
            for j, i in enumerate(eligible):
                row = records[i]
                score = float(scores[j])
                prior = saved[row["source_row"]]
                if abs(score - prior) > SCORE_TOLERANCE:
                    raise ValueError("Reloaded score disagrees with saved prediction")
                result[row["source_row"]] = format_explanation(
                    row, self.names, matrix[j], shap[j], float(raw[j]), score, prior
                )
        for t in transfers:
            result[t.source_row]["transaction"] = reference(t)
        return [result[i] for i in sorted(result)]

    def annotate_case_report(self, report: dict, source_ids: list[int]) -> dict:
        if (
            report["dataset_fingerprint"] != self.scores.fingerprint
            or report["dataset_id"] != self.scores.dataset_id
        ):
            raise ValueError("Case dataset mismatch")
        if "transaction_explanations" in report:
            raise ValueError("Case report already has explanations")
        historical = {t["source_row"]: t for t in report["transactions"]}
        if not set(source_ids) <= set(historical):
            raise ValueError("Explain only historical case-context transactions")
        explanations = self.explain(
            source_ids, cutoff=datetime.fromisoformat(report["cutoff"])
        )
        for e in explanations:
            t = historical[e["source_row"]]
            if (
                e["status"] == "SOURCE_NOT_FOUND"
                or e.get("occurred_at") != t["occurred_at"]
            ):
                raise ValueError("Case transaction time/input mismatch")
            for key, value in e["transaction"].items():
                actual = t[key]
                if key in ("amount_paid", "amount_received"):
                    actual, value = Decimal(actual), Decimal(value)
                if actual != value:
                    raise ValueError("Case transaction attributes mismatch")
            if e.get("saved_review_score") != t["score"]:
                raise ValueError("Case score disagrees with saved prediction")
        result = copy.deepcopy(report)
        result["transaction_explanations"] = {
            "method": "LightGBM native TreeSHAP, raw output, tree-path-dependent",
            "model": self.scores.model,
            "selected_source_ids": sorted(source_ids),
            "unrequested_transactions": len(historical) - len(source_ids),
            "items": explanations,
            "causal": False,
        }
        return result
