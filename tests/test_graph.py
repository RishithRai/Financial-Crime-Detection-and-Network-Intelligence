"""Small hand-worked directed multigraphs and resource bounds."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from mulegraph.graph import (
    GraphLimitExceeded,
    Limits,
    Transfer,
    build_network,
    statistics,
    validate_account,
    validate_window,
)

START = datetime(2022, 9, 1)
CUTOFF = START + timedelta(hours=2)
A, B, C, D = ("1", "000A"), ("2", "000A"), ("1", "B"), ("1", "C")


def transfer(row: int, sender=A, receiver=B, time=START) -> Transfer:
    return Transfer(
        1,
        row,
        time,
        *sender,
        *receiver,
        Decimal("1.10"),
        "USD",
        Decimal("0.000001"),
        "Bitcoin",
        "ACH",
    )


class MemoryReader:
    dataset_id = 1
    fingerprint = "synthetic"

    def __init__(self, rows, limits=None):
        self.rows = rows
        self.limits = limits or Limits()
        self.calls = []

    def history(self, account, start, cutoff):
        self.calls.append(account)
        return [
            r
            for r in self.rows
            if start <= r.occurred_at < cutoff and account in (r.sender, r.receiver)
        ]

    def focal(self, row, cutoff):
        return next(
            r for r in self.rows if r.source_row == row and r.occurred_at == cutoff
        )


def test_parallel_edges_self_transfers_and_composite_identity():
    rows = [
        transfer(1),
        transfer(2),
        transfer(3, B, A),
        transfer(4, A, A),
        transfer(5, B, C),
        transfer(6, C, D),
    ]
    result = build_network(MemoryReader(rows), A, START, CUTOFF, hops=2)
    g = result.graph
    assert set(g) == {A, B, C}
    assert g.number_of_edges(A, B) == 2
    assert g.number_of_edges(B, A) == 1
    assert g[A][B][(1, 1)]["amount_paid"] == Decimal("1.10")
    assert set(g[A][B][(1, 1)]) == set(Transfer.__dataclass_fields__)
    stats = statistics(g, A)
    assert stats == {
        "nodes": 3,
        "transactions": 5,
        "self_transfers": 1,
        "in_degree": 2,
        "out_degree": 3,
        "account_transactions": 4,
        "unique_counterparties": 1,
        "transactions_per_hour": 2,
        "weak_components": 1,
        "strong_components": 2,
        "reachable_out": 2,
        "reachable_in": 1,
    }
    assert result.expanded_accounts == 2
    with pytest.raises(Exception, match="Frozen graph"):
        g.add_edge(A, D)


def test_future_peer_invariance_focal_separation_and_lower_bound():
    rows = [transfer(1), transfer(2, time=START - timedelta(seconds=1))]
    before = build_network(MemoryReader(rows), A, START, CUTOFF)
    rows += [
        transfer(3, A, D, CUTOFF),
        transfer(4, A, C, CUTOFF),
        transfer(5, A, C, CUTOFF + timedelta(seconds=1)),
    ]
    after = build_network(MemoryReader(rows), A, START, CUTOFF, focal_source_row=3)
    assert list(before.graph.edges(keys=True, data=True)) == list(
        after.graph.edges(keys=True, data=True)
    )
    assert after.focal.source_row == 3 and D not in after.graph
    assert statistics(after.graph, A) == statistics(before.graph, A)


def test_bounded_expansion_fails_instead_of_partial_statistics():
    rows = [transfer(i, A, ("1", str(i))) for i in range(1, 101)]
    for limits in (Limits(max_nodes=4), Limits(max_edges=4)):
        reader = MemoryReader(rows, limits)
        with pytest.raises(GraphLimitExceeded):
            build_network(reader, A, START, CUTOFF)
        assert reader.calls == [A]
    reader = MemoryReader([transfer(1), transfer(2, B, C), transfer(3, C, D)])
    result = build_network(reader, A, START, CUTOFF, hops=1)
    assert set(result.graph) == {A, B} and reader.calls == [A]


def test_isolate_and_invalid_inputs():
    g = build_network(MemoryReader([]), A, START, CUTOFF).graph
    assert statistics(g, A)["transactions_per_hour"] == 0
    for account in (("001", "A"), (1, "A"), ("1", ""), ("١", "A")):
        with pytest.raises(ValueError):
            validate_account(account)
    for args in ((START, START), (CUTOFF, START), (START.astimezone(), CUTOFF)):
        with pytest.raises(ValueError):
            validate_window(*args)
    for kwargs in (
        {"max_edges": 20001},
        {"max_hops": 4},
        {"max_nodes": 0},
        {"max_edges": True},
        {"statement_timeout_ms": 30001},
    ):
        with pytest.raises(ValueError):
            Limits(**kwargs)
    with pytest.raises(ValueError):
        build_network(MemoryReader([]), A, START, CUTOFF, hops=3)
    with pytest.raises(ValueError, match="temporal"):
        reader = MemoryReader([])
        reader.history = lambda *args: [transfer(1, time=CUTOFF)]
        build_network(reader, A, START, CUTOFF)
