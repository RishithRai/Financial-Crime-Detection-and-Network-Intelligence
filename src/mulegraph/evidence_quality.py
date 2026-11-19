"""Bounded descriptive annotations; never alter detector or case membership."""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, localcontext

ORDERED = {"transaction_chain", "circular_flow", "rapid_movement"}


def assess_evidence(report: dict) -> dict:
    """Describe exact handoffs using existing local evidence, without queries."""
    rows = report["transactions"]
    findings = report["findings"]
    if len(rows) > 5000 or len(findings) > 1000:
        raise ValueError("Evidence assessment exceeds the bounded report budget")
    if sum(len(f["transactions"]) for f in findings) > 100000:
        raise ValueError("Too many supporting references")
    sources = {t["source_row"]: t for t in rows}
    if len(sources) != len(rows):
        raise ValueError("Duplicate source identity")
    start, cutoff = (datetime.fromisoformat(report[k]) for k in ("start", "cutoff"))
    activity: dict[tuple, list] = defaultdict(list)
    for t in rows:
        time = datetime.fromisoformat(t["occurred_at"])
        if not start <= time < cutoff:
            raise ValueError("Historical evidence outside cutoff")
        for account in {
            (t["from_bank_id"], t["from_account"]),
            (t["to_bank_id"], t["to_account"]),
        }:
            activity[account].append(time)
    for times in activity.values():
        times.sort()
    histories = {tuple(a["account"]): a["history"] for a in report["accounts"]}
    result = {}
    for f in findings:
        if f["id"] in result:
            raise ValueError("Duplicate finding identity")
        refs = f["transactions"]
        if len({t["source_row"] for t in refs}) != len(refs):
            raise ValueError("Repeated supporting source")
        for t in refs:
            source = sources.get(t["source_row"])
            if source is None or any(source.get(k) != v for k, v in t.items()):
                raise ValueError("Supporting evidence does not match history")
        ordered = sorted(refs, key=lambda t: (t["occurred_at"], t["source_row"]))
        handoffs = []
        descriptors = ["WINDOW_BOUNDED_HISTORY", "EVENT_TIME_AVAILABILITY_ASSUMED"]
        if any(
            not histories.get(tuple(a), {}).get("complete_for_account", False)
            for a in f["accounts"]
        ):
            descriptors.append("INCOMPLETE_ACCOUNT_HISTORY")
        missing = Counter(
            sources[t["source_row"]].get("score_status", "SCORE_UNAVAILABLE")
            for t in refs
            if sources[t["source_row"]].get("score") is None
        )
        if missing:
            descriptors.append("MISSING_REVIEW_SCORES")
        if f["pattern_type"] in ORDERED:
            for incoming, outgoing in zip(ordered, ordered[1:], strict=False):
                account = (incoming["to_bank_id"], incoming["to_account"])
                if account != (outgoing["from_bank_id"], outgoing["from_account"]):
                    raise ValueError("Disconnected ordered witness")
                before = datetime.fromisoformat(incoming["occurred_at"])
                after = datetime.fromisoformat(outgoing["occurred_at"])
                if after <= before:
                    raise ValueError("Nonchronological ordered witness")
                same = incoming["receiving_currency"] == outgoing["payment_currency"]
                item = {
                    "incoming_source": incoming["source_row"],
                    "outgoing_source": outgoing["source_row"],
                    "account": list(account),
                    "elapsed_seconds": (after - before).total_seconds(),
                    "incoming_received": incoming["amount_received"],
                    "incoming_currency": incoming["receiving_currency"],
                    "outgoing_paid": outgoing["amount_paid"],
                    "outgoing_currency": outgoing["payment_currency"],
                    "currency_continuity": same,
                    "outgoing_minus_incoming": None,
                    "amount_relation": "NOT_COMPARABLE_CURRENCY",
                    "other_local_transactions_between": (
                        bisect_left(activity[account], after)
                        - bisect_right(activity[account], before)
                    ),
                }
                if same:
                    a, b = (
                        Decimal(incoming["amount_received"]),
                        Decimal(outgoing["amount_paid"]),
                    )
                    if not a.is_finite() or not b.is_finite() or min(a, b) < 0:
                        raise ValueError("Invalid monetary evidence")
                    with localcontext() as context:
                        context.prec = (
                            max(len(a.as_tuple().digits), len(b.as_tuple().digits))
                            + abs(a.as_tuple().exponent - b.as_tuple().exponent)
                            + 10
                        )
                        item["outgoing_minus_incoming"] = format(b - a, "f")
                    item["amount_relation"] = (
                        "EQUAL_RECORDED_AMOUNTS" if a == b else "AMOUNT_MISMATCH"
                    )
                descriptors.append(item["amount_relation"])
                handoffs.append(item)
        else:
            descriptors.append("CONCENTRATION_NOT_ORDERED_FLOW")
        result[f["id"]] = {
            "descriptors": sorted(set(descriptors)),
            "handoffs": handoffs,
            "distinct_transactions": len(refs),
            "scored_transactions": len(refs) - sum(missing.values()),
            "missing_score_reasons": dict(sorted(missing.items())),
            "supports": (
                "A strictly chronological connection through "
                "matching account identities."
                if handoffs
                else (
                    "Concentration of recorded activity across counterparties; "
                    "not an ordered flow."
                )
            ),
            "uncertain": (
                "Timing and comparable amounts can support a hypothesis of "
                "related activity, but neither equality nor similarity identifies "
                "the same funds. Differences may reflect fees, splitting, pooling "
                "or unrelated activity; none is established here."
            ),
            "useful_next_evidence": [
                (
                    "Complete account statements and balances "
                    "before and between these transfers."
                ),
                (
                    "Payment references, purpose and independently verified "
                    "counterparty relationships."
                ),
                (
                    "Fee and currency-conversion records where applicable; "
                    "actual receipt/availability times."
                ),
            ],
        }
    return {"version": "evidence-quality-v1", "findings": result}
