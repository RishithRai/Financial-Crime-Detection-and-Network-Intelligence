"""Exact, noncausal annotations preserve original evidence and temporal rules."""

from copy import deepcopy

import pytest

from mulegraph.evidence_quality import assess_evidence


def report() -> dict:
    def tx(source: int, sender: str, receiver: str, minute: int) -> dict:
        return dict(
            source_row=source,
            from_bank_id="1",
            from_account=sender,
            to_bank_id="1",
            to_account=receiver,
            occurred_at=f"2022-09-07T00:{minute:02}:00",
            amount_received="100.00000001",
            amount_paid="100.00000002",
            receiving_currency="USD",
            payment_currency="USD",
        )

    a, b, c = tx(1, "A", "B", 1), tx(2, "B", "C", 3), tx(3, "B", "D", 2)
    return {
        "start": "2022-09-07T00:00:00",
        "cutoff": "2022-09-08T00:00:00",
        "transactions": [
            dict(a, score=0),
            dict(b, score=None, score_status="UNSCORED_TRAINING_PERIOD"),
            dict(c, score=None),
        ],
        "accounts": [
            {"account": ["1", "B"], "history": {"complete_for_account": False}}
        ],
        "findings": [
            {
                "id": "f",
                "pattern_type": "transaction_chain",
                "accounts": [["1", "A"], ["1", "B"], ["1", "C"]],
                "transactions": [a, b],
            }
        ],
    }


def test_exact_difference_context_missingness_and_immutability() -> None:
    r = report()
    before = deepcopy(r)
    q = assess_evidence(r)["findings"]["f"]
    assert q["handoffs"][0]["outgoing_minus_incoming"] == "0.00000001"
    assert q["handoffs"][0]["elapsed_seconds"] == 120
    assert q["handoffs"][0]["other_local_transactions_between"] == 1
    assert q["scored_transactions"] == 1  # Zero is scored.
    assert q["missing_score_reasons"] == {"UNSCORED_TRAINING_PERIOD": 1}
    assert "INCOMPLETE_ACCOUNT_HISTORY" in q["descriptors"]
    assert r == before
    assert assess_evidence(r) == assess_evidence(deepcopy(r))


@pytest.mark.parametrize(
    "kind", ["transaction_chain", "circular_flow", "rapid_movement"]
)
def test_ordered_types_have_no_amount_similarity_threshold(kind: str) -> None:
    r = report()
    r["findings"][0]["pattern_type"] = kind
    for row in (r["transactions"][1], r["findings"][0]["transactions"][1]):
        row["amount_paid"] = "100.00000001"
    assert (
        assess_evidence(r)["findings"]["f"]["handoffs"][0]["amount_relation"]
        == "EQUAL_RECORDED_AMOUNTS"
    )


def test_currency_mismatch_not_compared_and_fans_not_ordered() -> None:
    r = report()
    for row in (r["transactions"][1], r["findings"][0]["transactions"][1]):
        row["payment_currency"] = "EUR"
    h = assess_evidence(r)["findings"]["f"]["handoffs"][0]
    assert h["outgoing_minus_incoming"] is None
    assert h["amount_relation"] == "NOT_COMPARABLE_CURRENCY"
    for kind in ("fan_in", "fan_out"):
        r["findings"][0]["pattern_type"] = kind
        assert assess_evidence(r)["findings"]["f"]["handoffs"] == []


@pytest.mark.parametrize("fault", ["peer", "future", "corrupt", "duplicate", "limit"])
def test_invalid_or_unbounded_evidence_rejected(fault: str) -> None:
    r = report()
    if fault == "peer":
        for row in (r["transactions"][1], r["findings"][0]["transactions"][1]):
            row["occurred_at"] = r["transactions"][0]["occurred_at"]
    elif fault == "future":
        r["transactions"][2]["occurred_at"] = r["cutoff"]
    elif fault == "corrupt":
        r["findings"][0]["transactions"][0]["amount_received"] = "7"
    elif fault == "duplicate":
        r["transactions"].append(r["transactions"][0])
    else:
        r["findings"] *= 1001
    with pytest.raises(ValueError):
        assess_evidence(r)


def test_empty_report_and_exact_large_amounts() -> None:
    r = report()
    for row in (r["transactions"][0], r["findings"][0]["transactions"][0]):
        row["amount_received"] = "123456789012345678901234567890.00000001"
    for row in (r["transactions"][1], r["findings"][0]["transactions"][1]):
        row["amount_paid"] = "123456789012345678901234567890.00000002"
    assert (
        assess_evidence(r)["findings"]["f"]["handoffs"][0]["outgoing_minus_incoming"]
        == "0.00000001"
    )
    r["findings"] = []
    assert assess_evidence(r)["findings"] == {}


def test_report_replay_and_no_overwrite(tmp_path) -> None:
    import json

    from mulegraph.evidence_quality_report import run

    r = report()
    r["cases"] = []
    source = tmp_path / "example.json"
    source.write_text(json.dumps(r))
    output = tmp_path / "audit.json"
    result = run([source], output)
    assert result["examples"][0]["distinct_handoff_pairs"] == 1
    assert result["examples"][0]["original_unchanged"]
    with pytest.raises(FileExistsError):
        run([source], output)
    with pytest.raises(ValueError):
        run([source] * 11, tmp_path / "other.json")
