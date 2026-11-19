"""Bounded, label-free event-time investigation graphs (not predictive features)."""

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

import networkx as nx
import psycopg
from psycopg.rows import dict_row

from mulegraph.schema import statement

Account = tuple[str, str]
COLUMNS = """dataset_id, source_row, occurred_at, from_bank_id, from_account,
    to_bank_id, to_account, amount_paid, payment_currency, amount_received,
    receiving_currency, payment_format"""
# Each branch can use its existing endpoint/time index. Incoming self-transfers
# are excluded because the outgoing branch already returns them once.
HISTORY_SQL = (
    """
SELECT * FROM (
 (SELECT """
    + COLUMNS
    + """ FROM {core}.transactions
  WHERE dataset_id=%(dataset)s AND from_bank_id=%(bank)s
    AND from_account=%(account)s AND occurred_at >= %(start)s
    AND occurred_at < %(cutoff)s
  ORDER BY occurred_at,source_row LIMIT %(limit)s)
 UNION ALL
 (SELECT """
    + COLUMNS
    + """ FROM {core}.transactions
  WHERE dataset_id=%(dataset)s AND to_bank_id=%(bank)s
    AND to_account=%(account)s AND occurred_at >= %(start)s
    AND occurred_at < %(cutoff)s
    AND NOT (from_bank_id=%(bank)s AND from_account=%(account)s)
  ORDER BY occurred_at,source_row LIMIT %(limit)s)
) history ORDER BY occurred_at,source_row LIMIT %(limit)s
"""
)


class GraphLimitExceeded(ValueError):
    """The complete requested neighborhood exceeds its resource budget."""


@dataclass(frozen=True)
class Limits:
    max_nodes: int = 500
    max_edges: int = 5000
    max_hops: int = 2
    statement_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        for value, ceiling in (
            (self.max_nodes, 2000),
            (self.max_edges, 20000),
            (self.max_hops, 3),
            (self.statement_timeout_ms, 30000),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Resource limits must be positive bounded integers")


def validate_account(account: Account) -> None:
    if (
        not isinstance(account, tuple)
        or len(account) != 2
        or any(not isinstance(x, str) or not x for x in account)
        or not account[0].isascii()
        or not account[0].isdigit()
        or (len(account[0]) > 1 and account[0].startswith("0"))
    ):
        raise ValueError("Use (canonical bank ID, unchanged account string)")


def validate_window(start: datetime, cutoff: datetime) -> None:
    if (
        not isinstance(start, datetime)
        or not isinstance(cutoff, datetime)
        or start.tzinfo is not None
        or cutoff.tzinfo is not None
        or start >= cutoff
    ):
        raise ValueError("Require naive source timestamps with start < cutoff")


@dataclass(frozen=True)
class Transfer:
    dataset_id: int
    source_row: int
    occurred_at: datetime
    from_bank_id: str
    from_account: str
    to_bank_id: str
    to_account: str
    amount_paid: Decimal
    payment_currency: str
    amount_received: Decimal
    receiving_currency: str
    payment_format: str

    @property
    def sender(self) -> Account:
        return self.from_bank_id, self.from_account

    @property
    def receiver(self) -> Account:
        return self.to_bank_id, self.to_account

    @property
    def key(self) -> tuple[int, int]:
        return self.dataset_id, self.source_row


@dataclass
class Investigation:
    graph: nx.MultiDiGraph
    focal: Transfer | None
    expanded_accounts: int
    history_queries: int


def build_network(
    store: "GraphReader",
    account: Account,
    start: datetime,
    cutoff: datetime,
    hops: int = 1,
    focal_source_row: int | None = None,
) -> Investigation:
    """Expand incident edges of nodes at distance < hops, in either direction.

    Boundary-node edges are not induced. Overflow raises instead of returning
    a silently sampled graph. The focal transaction never expands the frontier.
    """
    validate_account(account)
    validate_window(start, cutoff)
    if type(hops) is not int or not 1 <= hops <= store.limits.max_hops:
        raise ValueError("Hops exceed the configured limit")
    focal = None
    if focal_source_row is not None:
        focal = store.focal(focal_source_row, cutoff)
        if account not in (focal.sender, focal.receiver):
            raise ValueError("Focal transaction must touch the investigated account")
    graph = nx.MultiDiGraph(
        dataset_id=store.dataset_id,
        dataset_fingerprint=store.fingerprint,
        start=start,
        cutoff=cutoff,
        hops=hops,
        root=account,
        scope="incident expansion; boundary not induced",
    )
    graph.add_node(account)
    queue = deque([(account, 0)])
    discovered = {account}
    seen_edges: set[tuple[int, int]] = set()
    expanded = 0
    while queue:
        node, depth = queue.popleft()
        if depth == hops:
            continue
        transfers = store.history(node, start, cutoff)
        expanded += 1
        for transfer in transfers:
            if (
                transfer.dataset_id != store.dataset_id
                or not start <= transfer.occurred_at < cutoff
                or node not in (transfer.sender, transfer.receiver)
            ):
                raise ValueError("Invalid history row or temporal boundary")
            if transfer.key in seen_edges:
                continue
            endpoints = {transfer.sender, transfer.receiver}
            if len(discovered | endpoints) > store.limits.max_nodes:
                raise GraphLimitExceeded("Node budget exceeded; narrow the window/hops")
            if len(seen_edges) >= store.limits.max_edges:
                raise GraphLimitExceeded("Edge budget exceeded; narrow the window/hops")
            seen_edges.add(transfer.key)
            graph.add_edge(
                transfer.sender, transfer.receiver, key=transfer.key, **asdict(transfer)
            )
            for neighbor in sorted(endpoints - discovered):
                discovered.add(neighbor)
                queue.append((neighbor, depth + 1))
    return Investigation(nx.freeze(graph), focal, expanded, expanded)


def statistics(graph: nx.MultiDiGraph, account: Account) -> dict:
    """Statistics describe only returned edges; connectivity is not time-respecting."""
    if account not in graph:
        raise ValueError("Account is absent from graph")
    hours = (graph.graph["cutoff"] - graph.graph["start"]).total_seconds() / 3600
    incoming, outgoing = graph.in_degree(account), graph.out_degree(account)
    loops = graph.number_of_edges(account, account)
    counterparties = set(graph.predecessors(account)) | set(graph.successors(account))
    counterparties.discard(account)
    return {
        "nodes": graph.number_of_nodes(),
        "transactions": graph.number_of_edges(),
        "self_transfers": nx.number_of_selfloops(graph),
        "in_degree": incoming,
        "out_degree": outgoing,
        "account_transactions": incoming + outgoing - loops,
        "unique_counterparties": len(counterparties),
        "transactions_per_hour": (incoming + outgoing - loops) / hours,
        "weak_components": nx.number_weakly_connected_components(graph),
        "strong_components": nx.number_strongly_connected_components(graph),
        "reachable_out": len(nx.descendants(graph, account)),
        "reachable_in": len(nx.ancestors(graph, account)),
    }


class GraphReader:
    """Use via graph_session; all operations share one read-only snapshot."""

    def __init__(
        self,
        connection: psycopg.Connection,
        dataset_id: int,
        schema: str,
        limits: Limits,
    ) -> None:
        if type(dataset_id) is not int or dataset_id < 1:
            raise ValueError("Dataset ID must be a positive integer")
        self.connection = connection
        self.dataset_id = dataset_id
        self.schema = schema
        self.limits = limits
        row = connection.execute(
            statement(
                "SELECT fingerprint, status FROM {core}.datasets WHERE dataset_id=%s",
                schema,
            ),
            (dataset_id,),
        ).fetchone()
        if row is None or row["status"] != "complete":
            raise ValueError("Dataset must exist and be complete")
        self.fingerprint = row["fingerprint"]

    def history(
        self, account: Account, start: datetime, cutoff: datetime
    ) -> list[Transfer]:
        validate_account(account)
        validate_window(start, cutoff)
        rows = self.connection.execute(
            statement(HISTORY_SQL, self.schema),
            {
                "dataset": self.dataset_id,
                "bank": account[0],
                "account": account[1],
                "start": start,
                "cutoff": cutoff,
                "limit": self.limits.max_edges + 1,
            },
        ).fetchall()
        if len(rows) > self.limits.max_edges:
            raise GraphLimitExceeded("Account history exceeds edge budget")
        return [Transfer(**row) for row in rows]

    def focal(self, source_row: int, cutoff: datetime) -> Transfer:
        if type(source_row) is not int or source_row < 1:
            raise ValueError("Focal source row must be positive")
        if not isinstance(cutoff, datetime) or cutoff.tzinfo is not None:
            raise ValueError("Use a naive source timestamp")
        row = self.connection.execute(
            statement(
                "SELECT " + COLUMNS + " FROM {core}.transactions "
                "WHERE dataset_id=%s AND source_row=%s AND occurred_at=%s",
                self.schema,
            ),
            (self.dataset_id, source_row, cutoff),
        ).fetchone()
        if row is None:
            raise ValueError("Focal transaction must exist exactly at cutoff")
        return Transfer(**row)

    def network(
        self,
        account: Account,
        start: datetime,
        cutoff: datetime,
        hops: int = 1,
        focal_source_row: int | None = None,
    ) -> Investigation:
        return build_network(self, account, start, cutoff, hops, focal_source_row)


@contextmanager
def graph_session(
    database_url: str,
    dataset_id: int,
    *,
    schema: str = "mulegraph",
    limits: Limits | None = None,
) -> Iterator[GraphReader]:
    """Never query labels, account/entity metadata, or write database records."""
    with psycopg.connect(
        database_url, connect_timeout=5, row_factory=dict_row
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (str((limits or Limits()).statement_timeout_ms),),
        )
        connection.execute("SET LOCAL work_mem='8MB'")
        connection.execute("SET LOCAL max_parallel_workers_per_gather=0")
        yield GraphReader(connection, dataset_id, schema, limits or Limits())
