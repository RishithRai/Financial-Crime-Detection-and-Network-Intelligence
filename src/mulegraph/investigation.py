"""Bounded temporal pattern witnesses for review, never laundering determinations."""

import hashlib
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol

import networkx as nx

from mulegraph.graph import Account, GraphLimitExceeded, GraphReader, Transfer


@dataclass(frozen=True)
class PatternPolicy:
    fan_accounts: int = 3
    fan_seconds: int = 3600
    rapid_seconds: int = 300
    path_seconds: int = 86400
    max_path_edges: int = 4
    max_candidates: int = 50000
    max_findings: int = 1000
    max_references: int = 10000

    def __post_init__(self) -> None:
        for name, low, high in (
            ("fan_accounts", 2, 100),
            ("fan_seconds", 1, 86400),
            ("rapid_seconds", 1, 3600),
            ("path_seconds", 1, 604800),
            ("max_path_edges", 2, 6),
            ("max_candidates", 1, 200000),
            ("max_findings", 1, 5000),
            ("max_references", 1, 20000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Invalid pattern policy: {name}")


class ScoreSource(Protocol):
    def lookup(
        self, transfers: list[Transfer], fingerprint: str
    ) -> dict[int, float]: ...


def reference(t: Transfer) -> dict:
    result = asdict(t)
    result["occurred_at"] = t.occurred_at.isoformat()
    result["amount_paid"] = str(t.amount_paid)
    result["amount_received"] = str(t.amount_received)
    return result


def detect(
    graph: nx.MultiDiGraph, root: Account, policy: PatternPolicy | None = None
) -> tuple[list[dict], int]:
    """Enumerate bounded witnesses involving root; fail closed on work/output caps."""
    policy = policy or PatternPolicy()
    if root not in graph or len(graph) > 2000 or graph.number_of_edges() > 20000:
        raise GraphLimitExceeded("Invalid root or graph exceeds investigation limits")
    edges = []
    seen = set()
    for sender, receiver, key, data in graph.edges(keys=True, data=True):
        t = Transfer(**data)
        if (
            t.key != key
            or t.sender != sender
            or t.receiver != receiver
            or t.dataset_id != graph.graph["dataset_id"]
            or t.key in seen
            or not graph.graph["start"] <= t.occurred_at < graph.graph["cutoff"]
        ):
            raise ValueError("Invalid graph identity or historical boundary")
        seen.add(t.key)
        if t.sender != t.receiver and t.amount_paid > 0 and t.amount_received > 0:
            edges.append(t)
    edges.sort(key=lambda t: (t.occurred_at, t.source_row))
    findings, work, references = [], 0, 0

    def spend() -> None:
        nonlocal work
        work += 1
        if work > policy.max_candidates:
            raise GraphLimitExceeded("Pattern candidate budget exceeded")

    def emit(kind: str, path: list[Transfer], evidence: dict) -> None:
        nonlocal references
        accounts = sorted({a for t in path for a in (t.sender, t.receiver)})
        if root not in accounts:
            return
        if len(findings) >= policy.max_findings:
            raise GraphLimitExceeded("Pattern finding budget exceeded")
        references += len(path)
        if references > policy.max_references:
            raise GraphLimitExceeded("Evidence reference budget exceeded")
        identity = kind + repr([t.key for t in path])
        findings.append(
            {
                "id": hashlib.sha256(identity.encode()).hexdigest(),
                "pattern_type": kind,
                "accounts": accounts,
                "transactions": [reference(t) for t in path],
                "first_at": path[0].occurred_at.isoformat(),
                "last_at": path[-1].occurred_at.isoformat(),
                "evidence": evidence,
                "interpretation": "Pattern for review; not proof of laundering "
                "or movement of the same funds.",
            }
        )

    # One earliest qualifying witness per direction, center, and currency.
    for direction in ("fan_in", "fan_out"):
        groups = defaultdict(list)
        for t in edges:
            center, other, currency = (
                (t.receiver, t.sender, t.receiving_currency)
                if direction == "fan_in"
                else (t.sender, t.receiver, t.payment_currency)
            )
            groups[center, currency].append((t, other))
        for (center, currency), group in sorted(groups.items()):
            window, counts = deque(), Counter()
            for t, other in group:
                spend()
                while (
                    window
                    and (t.occurred_at - window[0][0].occurred_at).total_seconds()
                    > policy.fan_seconds
                ):
                    _, expired = window.popleft()
                    counts[expired] -= 1
                    if not counts[expired]:
                        del counts[expired]
                window.append((t, other))
                counts[other] += 1
                if len(counts) >= policy.fan_accounts and (
                    root == center or root in counts
                ):
                    emit(
                        direction,
                        [x[0] for x in window],
                        {
                            "center": center,
                            "currency": currency,
                            "distinct_counterparties": len(counts),
                            "window_seconds": policy.fan_seconds,
                            "ordered_flow_claim": False,
                        },
                    )
                    break
    outgoing = defaultdict(list)
    for t in edges:
        outgoing[t.sender].append(t)
    times = {a: [t.occurred_at for t in rows] for a, rows in outgoing.items()}

    def extend(path: list[Transfer], visited: set[Account]) -> None:
        last = path[-1]
        rows = outgoing[last.receiver]
        offset = bisect_right(times.get(last.receiver, []), last.occurred_at)
        for i in range(offset, len(rows)):
            spend()
            following = rows[i]
            elapsed = (following.occurred_at - path[0].occurred_at).total_seconds()
            if elapsed > policy.path_seconds:
                break
            if last.receiving_currency != following.payment_currency:
                continue
            closes = following.receiver == path[0].sender
            if following.receiver in visited and not closes:
                continue
            extended = [*path, following]
            evidence = {
                "elapsed_seconds": elapsed,
                "strictly_increasing_times": True,
                "handoff_currencies_match": True,
                "amount_matching_performed": False,
            }
            emit("circular_flow" if closes else "transaction_chain", extended, evidence)
            if len(extended) == 2 and elapsed <= policy.rapid_seconds:
                emit(
                    "rapid_movement",
                    extended,
                    {**evidence, "intermediary": last.receiver},
                )
            if not closes and len(extended) < policy.max_path_edges:
                extend(extended, visited | {following.receiver})

    for t in edges:
        spend()
        extend([t], {t.sender, t.receiver})
    return findings, work


def investigate(
    reader: GraphReader,
    start: datetime,
    cutoff: datetime,
    *,
    account: Account | None = None,
    focal_source_row: int | None = None,
    hops: int = 2,
    policy: PatternPolicy | None = None,
    scores: ScoreSource | None = None,
) -> dict:
    """Focal-only requests investigate its sender; focal stays separate from history."""
    policy = policy or PatternPolicy()
    if account is None:
        if focal_source_row is None:
            raise ValueError("Supply an account or focal transaction")
        account = reader.focal(focal_source_row, cutoff).sender
    result = reader.network(account, start, cutoff, hops, focal_source_row)
    findings, work = detect(result.graph, account, policy)
    transfers = [Transfer(**d) for _, _, d in result.graph.edges(data=True)]
    if result.focal:
        transfers.append(result.focal)
    priorities = scores.lookup(transfers, reader.fingerprint) if scores else {}
    for finding in findings:
        values = [
            priorities[t["source_row"]]
            for t in finding["transactions"]
            if t["source_row"] in priorities
        ]
        finding["priority"] = {
            "max_transaction_score": max(values) if values else None,
            "scored_transactions": len(values),
            "unscored_transactions": len(finding["transactions"]) - len(values),
            "meaning": "Frozen transaction review score; not account probability",
        }
    findings.sort(
        key=lambda f: (
            -(
                f["priority"]["max_transaction_score"]
                if f["priority"]["max_transaction_score"] is not None
                else -1
            ),
            f["id"],
        )
    )
    return {
        "version": "investigation-v1",
        "dataset_fingerprint": reader.fingerprint,
        "account": account,
        "start": start.isoformat(),
        "cutoff": cutoff.isoformat(),
        "policy": asdict(policy),
        "graph_scope": result.graph.graph["scope"],
        "nodes": len(result.graph),
        "edges": result.graph.number_of_edges(),
        "history_queries": result.history_queries,
        "candidate_checks": work,
        "focal": reference(result.focal) if result.focal else None,
        "score_model": getattr(scores, "model", None),
        "focal_score": priorities.get(result.focal.source_row)
        if result.focal
        else None,
        "findings": findings,
        "limitations": "Bounded event-time witnesses, not exhaustive global detection. "
        "Assumes immediate attribute availability. Focal excluded from "
        "patterns. Scores are retrospective, uncalibrated priorities.",
    }
