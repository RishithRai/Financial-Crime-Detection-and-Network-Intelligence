"""Explicit, train-fitted inputs and validation metrics for supervised baselines."""

import hashlib
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
from sklearn.metrics import average_precision_score, roc_auc_score

from mulegraph.rules import TIE_SALT

VERSION = "supervised-v1"
CURRENT = ("amount_paid", "amount_received", "self_transfer", "cross_currency")
HISTORY = tuple(
    f"{role}_{name}"
    for role in ("sender", "receiver")
    for name in (
        "history_count",
        "sent_count",
        "received_count",
        "count_1h",
        "count_24h",
        "unique_counterparties",
        "currency_history_count",
        "currency_count_1h",
        "currency_count_24h",
        "seconds_since_last",
        "history_age_seconds",
        "mean_gap_seconds",
        "frequency_1h",
        "frequency_24h",
        "currency_history_sum",
        "currency_sum_1h",
        "currency_sum_24h",
    )
)
CATEGORIES = ("payment_currency", "receiving_currency", "payment_format")
VARIANTS = ("current", "current_no_format", "history", "history_no_format")
NULLABLE = tuple(
    f"{r}_{n}"
    for r in ("sender", "receiver")
    for n in ("seconds_since_last", "history_age_seconds", "mean_gap_seconds")
)


def allowlist(variant: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if variant not in VARIANTS:
        raise ValueError("Unknown feature variant")
    return (
        CURRENT + (HISTORY if variant.startswith("history") else ()),
        CATEGORIES[:2] if variant.endswith("no_format") else CATEGORIES,
    )


def numeric(table: pa.Table, names: tuple[str, ...]) -> np.ndarray:
    values = np.column_stack(
        [table[n].cast(pa.float64()).to_numpy(zero_copy_only=False) for n in names]
    )
    if np.isinf(values).any() or (values < 0).any():
        raise ValueError("Expected finite, nonnegative feature values")
    for i, name in enumerate(names):
        if name not in NULLABLE and np.isnan(values[:, i]).any():
            raise ValueError(f"Unexpected missing feature: {name}")
    return values


@dataclass
class Preprocessor:
    """Train-only log1p/standardization, fixed missing flags, one-hot vocabulary."""

    variant: str
    mean: np.ndarray
    scale: np.ndarray
    categories: dict[str, list[str]]
    training_rows: int

    @classmethod
    def fit(cls, batches, variant: str) -> "Preprocessor":
        nums, cats = allowlist(variant)
        total = np.zeros(len(nums))
        squares = total.copy()
        vocab = {name: set() for name in cats}
        count = 0
        for batch in batches:
            # Caller must supply split for this guard; it is never a predictor.
            if set(batch["split"].to_pylist()) != {"train"}:
                raise ValueError("Preprocessing can only fit on training rows")
            x = np.log1p(np.nan_to_num(numeric(batch, nums), nan=0))
            total += x.sum(axis=0)
            squares += np.square(x).sum(axis=0)
            count += len(batch)
            for name in cats:
                values = batch[name].to_pylist()
                if any(v is None for v in values):
                    raise ValueError("Missing category")
                vocab[name].update(values)
        if not count:
            raise ValueError("Empty training data")
        mean = total / count
        scale = np.sqrt(np.maximum(squares / count - mean**2, 0))
        scale[scale < 1e-8] = 1
        return cls(
            variant, mean, scale, {k: sorted(v) for k, v in vocab.items()}, count
        )

    @property
    def names(self) -> list[str]:
        nums, cats = allowlist(self.variant)
        return (
            list(nums)
            + [n + "__missing" for n in nums if n in NULLABLE]
            + [f"{n}={v}" for n in cats for v in self.categories[n] + ["<UNKNOWN>"]]
        )

    def transform(self, table: pa.Table) -> np.ndarray:
        nums, cats = allowlist(self.variant)
        raw = numeric(table, nums)
        columns = [(np.log1p(np.nan_to_num(raw, nan=0)) - self.mean) / self.scale]
        columns.extend(
            np.isnan(raw[:, i : i + 1]) for i, n in enumerate(nums) if n in NULLABLE
        )
        for name in cats:
            values = np.asarray(table[name].to_pylist(), dtype=object)
            known = self.categories[name]
            columns.extend((values == v)[:, None] for v in known)
            columns.append((~np.isin(values, known))[:, None])
        result = np.concatenate(columns, axis=1).astype(np.float32)
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite model input")
        return result


def tie_keys(rows: np.ndarray, fingerprint: str) -> np.ndarray:
    return np.array(
        [
            hashlib.sha256(f"{fingerprint}:{int(r)}:{TIE_SALT}".encode()).hexdigest()
            for r in rows
        ]
    )


def evaluate(y: np.ndarray, scores: np.ndarray, ties: np.ndarray) -> dict:
    """Grouped-score AP/AUC; deterministic exact-budget ranking, whole-tier cutoff."""
    if len(y) == 0 or len(y) != len(scores) or len(y) != len(ties):
        raise ValueError("Evaluation alignment mismatch")
    if not np.isin(y, [0, 1]).all() or not np.isfinite(scores).all():
        raise ValueError("Invalid labels/scores")
    scores = np.asarray(scores, dtype=np.float64)
    order = np.lexsort((ties, -scores))
    ranked = y[order]
    positives = int(y.sum())
    budget = int(len(y) * 0.01)

    def at(k: int) -> dict:
        k = min(k, len(y))
        tp = int(ranked[:k].sum())
        return {
            "k": k,
            "true_positives": tp,
            "precision": tp / k if k else None,
            "recall": tp / positives if positives else None,
        }

    # A deployment threshold must not split score ties. Use the largest whole
    # prefix within the 1% cap. Ranking budget is separately and explicitly tied.
    cutoff = float(scores[order[budget]]) if budget < len(y) else float("inf")
    threshold = float(np.nextafter(cutoff, np.inf))
    alerted = scores >= threshold
    tp = int(y[alerted].sum())
    alerts = int(alerted.sum())
    return {
        "rows": len(y),
        "positives": positives,
        "prevalence": positives / len(y),
        "average_precision": float(average_precision_score(y, scores))
        if positives
        else None,
        "roc_auc": float(roc_auc_score(y, scores)) if 0 < positives < len(y) else None,
        "at_k": [at(k) for k in (100, 1000, 10000)],
        "budget_1pct": at(budget),
        "threshold": threshold,
        "alerts": alerts,
        "true_alerts": tp,
        "alert_precision": tp / alerts if alerts else None,
        "alert_recall": tp / positives if positives else None,
    }
