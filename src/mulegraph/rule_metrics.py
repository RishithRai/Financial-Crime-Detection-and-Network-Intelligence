"""Tie-aware Average Precision and explicitly budgeted threshold selection."""


def summarize(
    bins: list[tuple[int, int, int]],
    top_labels: list[int],
    threshold: int,
    ks: tuple[int, ...] = (100, 1000, 10000),
) -> dict:
    """Bins are (score, count, positives); top_labels use a label-free tie order."""
    bins = sorted(bins, reverse=True)
    n = sum(count for _, count, _ in bins)
    positives = sum(p for _, _, p in bins)
    if not n:
        raise ValueError("Cannot evaluate an empty split")
    if any(count <= 0 or not 0 <= p <= count for _, count, p in bins):
        raise ValueError("Invalid score histogram")
    seen = found = alerts = true_alerts = 0
    ap = 0.0
    for score, count, p in bins:
        seen += count
        found += p
        if positives:
            ap += p / positives * found / seen
        if score >= threshold:
            alerts += count
            true_alerts += p
    at_k = []
    for k in ks:
        effective = min(k, n)
        if len(top_labels) < effective:
            raise ValueError("Insufficient ranked labels for Precision@K")
        tp = sum(top_labels[:effective])
        at_k.append(
            {
                "requested_k": k,
                "effective_k": effective,
                "true_positives": tp,
                "precision": tp / effective,
                "recall": tp / positives if positives else None,
            }
        )
    return {
        "rows": n,
        "positives": positives,
        "prevalence": positives / n,
        "average_precision": ap if positives else None,
        "at_k": at_k,
        "threshold": threshold,
        "alerts": alerts,
        "true_alerts": true_alerts,
        "false_alerts": alerts - true_alerts,
        "alert_rate": alerts / n,
        "precision": true_alerts / alerts if alerts else None,
        "recall": true_alerts / positives if positives else None,
        "score_bins": [list(row) for row in bins],
    }


def select_threshold(
    bins: list[tuple[int, int, int]], maximum_score: int, alert_cap: float = 0.01
) -> tuple[int, list[dict]]:
    """Maximize validation F2 within a predeclared cap; ties prefer higher cutoffs."""
    n = sum(count for _, count, _ in bins)
    positives = sum(p for _, _, p in bins)
    if n == 0 or positives == 0:
        raise ValueError("Threshold selection needs positive validation observations")
    candidates = []
    for threshold in range(1, maximum_score + 2):
        alerts = sum(count for score, count, _ in bins if score >= threshold)
        tp = sum(p for score, _, p in bins if score >= threshold)
        # F_beta = (1+beta^2)TP / ((1+beta^2)TP + beta^2 FN + FP).
        f2 = 5 * tp / (4 * positives + alerts)
        candidates.append(
            {
                "threshold": threshold,
                "alerts": alerts,
                "true_positives": tp,
                "f2": f2,
                "eligible": alerts / n <= alert_cap,
            }
        )
    selected = max(
        (row for row in candidates if row["eligible"]),
        key=lambda row: (row["f2"], row["threshold"]),
    )
    return selected["threshold"], candidates
