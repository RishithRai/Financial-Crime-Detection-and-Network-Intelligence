"""Deterministic review cases and distinct-transaction account summaries."""

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime

import networkx as nx

from mulegraph.graph import (
    Account,
    GraphLimitExceeded,
    GraphReader,
    Transfer,
    validate_window,
)
from mulegraph.investigation import PatternPolicy, ScoreSource, detect, reference

PATTERN_REASONS = {
    "fan_in": "MULTIPLE_SENDERS_OBSERVED",
    "fan_out": "MULTIPLE_RECIPIENTS_OBSERVED",
    "transaction_chain": "ORDERED_TRANSFER_CHAIN",
    "circular_flow": "ORDERED_RETURN_SEQUENCE",
    "rapid_movement": "RAPID_INCOMING_OUTGOING_PAIR",
}


@dataclass(frozen=True)
class CasePolicy:
    account_link_seconds: int = 3600
    max_link_checks: int = 100000

    def __post_init__(self) -> None:
        for value, ceiling in (
            (self.account_link_seconds, 86400),
            (self.max_link_checks, 500000),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Invalid case policy")


def missing_reason(t: Transfer) -> str:
    if datetime(2022, 9, 1) <= t.occurred_at < datetime(2022, 9, 7):
        return "UNSCORED_TRAINING_PERIOD"
    if datetime(2022, 9, 7) <= t.occurred_at < datetime(2022, 9, 19):
        return "SAVED_SCORE_UNAVAILABLE"
    return "OUTSIDE_SAVED_SCORE_PERIODS"


def risk_summary(rows: list[Transfer], scores: dict[int, float]) -> dict:
    """Caller supplies distinct source rows; no score imputation or sums."""
    values = [scores[t.source_row] for t in rows if t.source_row in scores]
    missing = Counter(missing_reason(t) for t in rows if t.source_row not in scores)
    return {
        "distinct_transactions": len(rows),
        "scored_transactions": len(values),
        "unscored_transactions": len(rows) - len(values),
        "score_coverage": len(values) / len(rows) if rows else None,
        "max_transaction_score": max(values) if values else None,
        "unscored_reasons": dict(sorted(missing.items())),
    }


def ranking(item: dict) -> tuple:
    value = item["ml_summary"]["max_transaction_score"]
    return (
        -(value if value is not None else -1),
        str(item.get("id", item.get("account"))),
    )


def summarize(
    graph: nx.MultiDiGraph,
    root: Account,
    findings: list[dict],
    scores: dict[int, float],
    *,
    policy: CasePolicy | None = None,
    search_complete: bool = False,
) -> dict:
    """Group local witnesses; case counts are organizational, never incident counts."""
    policy = policy or CasePolicy()
    validate_window(graph.graph["start"], graph.graph["cutoff"])
    if root not in graph or len(graph) > 2000 or graph.number_of_edges() > 20000:
        raise GraphLimitExceeded("Case graph budget exceeded or invalid root")
    if len(findings) > 5000 or sum(len(f["transactions"]) for f in findings) > 20000:
        raise GraphLimitExceeded("Case evidence budget exceeded")
    rows, incident = {}, defaultdict(set)
    for u, v, key, data in graph.edges(keys=True, data=True):
        t = Transfer(**data)
        if (
            t.key != key
            or t.sender != u
            or t.receiver != v
            or t.dataset_id != graph.graph["dataset_id"]
            or t.source_row in rows
            or not graph.graph["start"] <= t.occurred_at < graph.graph["cutoff"]
        ):
            raise ValueError("Invalid graph identity or temporal boundary")
        rows[t.source_row] = t
        for a in {u, v}:
            incident[a].add(t.source_row)
    for row, score in scores.items():
        if row not in rows or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Unknown transaction or invalid score")
        if missing_reason(rows[row]) == "UNSCORED_TRAINING_PERIOD":
            raise ValueError("Training-period scores are not authorized")
        if missing_reason(rows[row]) == "OUTSIDE_SAVED_SCORE_PERIODS":
            raise ValueError("Scores outside saved periods are not authorized")
    catalog = {}
    references = {}
    for f in findings:
        canonical = json.loads(json.dumps(f, sort_keys=True))
        if f["id"] in catalog:
            if catalog[f["id"]] != canonical:
                raise ValueError("Conflicting finding identity")
            continue
        if f["pattern_type"] not in PATTERN_REASONS or not f["transactions"]:
            raise ValueError("Unknown or empty finding")
        ids = set()
        for record in f["transactions"]:
            row = record["source_row"]
            if row not in rows or record != reference(rows[row]):
                raise ValueError("Finding evidence does not match historical graph")
            ids.add(row)
        actual_accounts = {
            a for row in ids for a in (rows[row].sender, rows[row].receiver)
        }
        if actual_accounts != {tuple(a) for a in f["accounts"]}:
            raise ValueError("Finding accounts disagree with evidence")
        catalog[f["id"]] = canonical
        references[f["id"]] = ids
    names = sorted(catalog)
    parent = {name: name for name in names}
    links = []

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def join(a: str, b: str, evidence: dict) -> None:
        x, y = find(a), find(b)
        if x != y:
            parent[max(x, y)] = min(x, y)
            links.append({"findings": [a, b], **evidence})

    transaction_owner = {}
    buckets = defaultdict(list)
    for name in names:
        evidence = [rows[r] for r in sorted(references[name])]
        tokens = defaultdict(list)
        for t in evidence:
            if t.source_row in transaction_owner:
                join(
                    transaction_owner[t.source_row],
                    name,
                    {"reason": "SHARED_TRANSACTION", "source_row": t.source_row},
                )
            else:
                transaction_owner[t.source_row] = name
            tokens[t.sender, t.payment_currency].append(t.occurred_at)
            tokens[t.receiver, t.receiving_currency].append(t.occurred_at)
        for account, currency in sorted(tokens):
            if account != root:
                buckets[account, currency].append(
                    (
                        name,
                        min(tokens[account, currency]),
                        max(tokens[account, currency]),
                    )
                )
    checks = 0
    for (account, currency), bucket in sorted(buckets.items()):
        ordered = sorted(bucket, key=lambda item: (item[1], item[0]))
        for i, (a, _, end_a) in enumerate(ordered):
            for b, start_b, _ in ordered[i + 1 :]:
                checks += 1
                if checks > policy.max_link_checks:
                    raise GraphLimitExceeded("Case linkage budget exceeded")
                gap = max(0, (start_b - end_a).total_seconds())
                if gap > policy.account_link_seconds:
                    break
                join(
                    a,
                    b,
                    {
                        "reason": "SHARED_ACCOUNT_CURRENCY_NEAR_TIME",
                        "account": account,
                        "currency": currency,
                        "gap_seconds": gap,
                    },
                )
    groups = defaultdict(list)
    for name in names:
        groups[find(name)].append(name)
    fingerprint = graph.graph.get("dataset_fingerprint", "")
    cases = []
    for members in groups.values():
        ids = set().union(*(references[n] for n in members))
        evidence = [rows[r] for r in sorted(ids)]
        patterns = Counter(catalog[n]["pattern_type"] for n in members)
        reasons = sorted(PATTERN_REASONS[p] for p in patterns)
        if len(members) > 1:
            reasons.append("OVERLAPPING_FINDINGS_GROUPED")
        identity = json.dumps(
            [
                fingerprint,
                graph.graph["dataset_id"],
                root,
                graph.graph["start"].isoformat(),
                graph.graph["cutoff"].isoformat(),
                asdict(policy),
                members,
            ],
            sort_keys=True,
        )
        cases.append(
            {
                "id": hashlib.sha256(identity.encode()).hexdigest(),
                "finding_ids": members,
                "finding_count": len(members),
                "pattern_counts": dict(sorted(patterns.items())),
                "transaction_ids": sorted(ids),
                "accounts": sorted(
                    {a for t in evidence for a in (t.sender, t.receiver)}
                ),
                "first_at": min(t.occurred_at for t in evidence).isoformat(),
                "last_at": max(t.occurred_at for t in evidence).isoformat(),
                "ml_summary": risk_summary(evidence, scores),
                "reason_codes": reasons,
                "grouping_evidence": [
                    link
                    for link in links
                    if find(link["findings"][0]) == find(members[0])
                ],
                "meaning": "Review case, not an independent incident or account label",
            }
        )
    supporting = set().union(*references.values()) if references else set()
    account_findings = defaultdict(list)
    for name in names:
        for a in catalog[name]["accounts"]:
            account_findings[tuple(a)].append(name)
    summaries = []
    hours = (graph.graph["cutoff"] - graph.graph["start"]).total_seconds() / 3600
    for account in sorted(graph):
        history = [rows[r] for r in sorted(incident[account])]
        support = [t for t in history if t.source_row in supporting]
        ml = risk_summary(history, scores)
        reasons = ["LOCAL_GRAPH_SCOPE"]
        if ml["scored_transactions"]:
            reasons.append("FROZEN_TRANSACTION_SCORES_AVAILABLE")
        if ml["unscored_transactions"]:
            reasons.append("INCOMPLETE_SCORE_COVERAGE")
        if ml["unscored_reasons"].get("UNSCORED_TRAINING_PERIOD"):
            reasons.append("UNSCORED_TRAINING_TRANSACTIONS")
        if account != root:
            reasons.append("ACCOUNT_HISTORY_NOT_CERTIFIED_COMPLETE")
        fs = account_findings[account]
        reasons.extend(
            sorted({PATTERN_REASONS[catalog[n]["pattern_type"]] for n in fs})
        )
        if not fs:
            reasons.append("NO_NETWORK_PATTERN_WITNESS")
        summaries.append(
            {
                "account": account,
                "ml_summary": ml,
                "supporting_ml_summary": risk_summary(support, scores),
                "finding_ids": fs,
                "reason_codes": reasons,
                "history": {
                    "scope": "requested window in returned graph",
                    "complete_for_account": account == root
                    and graph.graph.get("root") == root,
                    "transaction_ids": sorted(incident[account]),
                    "incoming": sum(t.receiver == account for t in history),
                    "outgoing": sum(t.sender == account for t in history),
                    "self_transfers": sum(t.sender == t.receiver for t in history),
                    "unique_counterparties": len(
                        {a for t in history for a in (t.sender, t.receiver)} - {account}
                    ),
                    "transactions_per_hour": len(history) / hours,
                    "first_at": min(
                        (t.occurred_at for t in history), default=None
                    ).isoformat()
                    if history
                    else None,
                    "last_at": max(
                        (t.occurred_at for t in history), default=None
                    ).isoformat()
                    if history
                    else None,
                },
            }
        )
    cases.sort(key=ranking)
    summaries.sort(key=ranking)
    return {
        "version": "case-intelligence-v1",
        "dataset_fingerprint": fingerprint,
        "dataset_id": graph.graph["dataset_id"],
        "root": root,
        "start": graph.graph["start"].isoformat(),
        "cutoff": graph.graph["cutoff"].isoformat(),
        "case_policy": asdict(policy),
        "link_checks": checks,
        "findings": [catalog[n] for n in names],
        "cases": cases,
        "accounts": summaries,
        "transactions": [
            {
                **reference(rows[r]),
                "score": scores.get(r),
                "score_status": "SCORED" if r in scores else missing_reason(rows[r]),
            }
            for r in sorted(rows)
        ],
        "counts": {
            "input_finding_records": len(findings),
            "distinct_findings": len(names),
            "duplicate_finding_records": len(findings) - len(names),
            "cases": len(cases),
            "distinct_supporting_transactions": len(supporting),
            "distinct_historical_transactions": len(rows),
        },
        "completeness": {
            "search_completed_within_limits": search_complete,
            "global_evidence_complete": False,
            "root_window_history_complete": graph.graph.get("root") == root,
        },
        "interpretation": "ML maxima rank review; network evidence is descriptive. "
        "No combined probability, incident count or criminal-account label.",
    }


def investigate_cases(
    reader: GraphReader,
    start: datetime,
    cutoff: datetime,
    *,
    account: Account | None = None,
    focal_source_row: int | None = None,
    hops: int = 2,
    pattern_policy: PatternPolicy | None = None,
    case_policy: CasePolicy | None = None,
    scores: ScoreSource | None = None,
) -> dict:
    if account is None:
        if focal_source_row is None:
            raise ValueError("Supply account or focal transaction")
        account = reader.focal(focal_source_row, cutoff).sender
    result = reader.network(account, start, cutoff, hops, focal_source_row)
    findings, work = detect(result.graph, account, pattern_policy)
    transfers = [Transfer(**d) for _, _, d in result.graph.edges(data=True)]
    values = scores.lookup(transfers, reader.fingerprint) if scores else {}
    report = summarize(
        result.graph,
        account,
        findings,
        values,
        policy=case_policy,
        search_complete=True,
    )
    report.update(
        pattern_policy=asdict(pattern_policy or PatternPolicy()),
        candidate_checks=work,
        history_queries=result.history_queries,
        score_model=getattr(scores, "model", None),
        focal=reference(result.focal) if result.focal else None,
        focal_included_in_aggregation=False,
    )
    return report
