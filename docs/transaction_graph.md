# financial transaction graph foundation

`mulegraph.graph` provides bounded, read-only account histories and local directed
transaction networks. It reads only the completed dataset's ID/fingerprint/status
and explicit core transaction columns. It never queries laundering labels,
label-bearing hashes, pattern annotations, account/entity metadata, or ML scores.
No criminal-account classification, predictive graph features, UI, or model
updates are implemented.

## Representation and identity

Each graph belongs to one dataset. A node is the tuple `(canonical_bank_id,
unchanged_account_number)`; accounts with identical strings at different banks
remain distinct. Callers must supply canonical bank IDs (e.g. `"1"`, not `"001"`);
account strings, including leading zeros, are preserved. Never merge these
node keys across datasets without adding dataset identity to the node key.
The graph records the dataset fingerprint for portable provenance.

Each transaction is a directed sender-to-receiver edge in a NetworkX
`MultiDiGraph`, keyed by `(dataset_id, source_row)`. Identical content at different
source rows remains separate. Reverse transfers are separate directed edges;
self-transfers remain loops. Retrieving the same source transaction from both
endpoints does not duplicate it. Edge attributes include timestamp, endpoints,
both exact `Decimal` monetary values, their separate currencies, and payment
format. Monetary values are never pooled across currencies or converted to floats.

NetworkX's [MultiDiGraph contract](https://networkx.org/documentation/stable/reference/classes/multidigraph.html)
supports parallel directed edges and self-loops. The returned graph is structurally
frozen to prevent accidental edge/node additions. NetworkX attribute dictionaries
remain mutable; this is an in-memory investigation result, not an immutable audit
artifact. No graph or account-level output is committed to Git.

## Historical semantics

Every request requires naive source timestamps `start < cutoff`. All historical
queries use **`start <= occurred_at < cutoff`**. Source time has no declared
timezone; timezone-aware inputs are rejected rather than silently converted.
All transactions exactly at cutoff are excluded regardless of source-row order.
Earlier timestamp peers are legitimate history and are retained individually.

An optional focal source row must belong to the dataset, touch the requested
account, and occur **exactly at cutoff**. It is returned separately as
`Investigation.focal`, never inserted into the historical graph, counted in its
statistics, or used to expand the neighborhood. Other peers and later events
remain excluded. A missing, unrelated, earlier or later focal row is rejected.

The source contains no actual availability timestamps. This is an offline
**event-time replay assuming event time equals availability**, not proof of what
an investigator could have known at that time. Late arrivals, later corrections,
and delayed receiving-side attributes require a future availability-aware
contract. No synthetic availability time is invented. Dataset-start history is
left-censored. An isolated root means no observed transactions within the window;
it does not establish account existence, opening date, or real inactivity.

## Query architecture and resource limits

`graph_session()` owns a repeatable-read, read-only PostgreSQL transaction. All
histories, neighborhood expansion and focal lookup within that context share the
same snapshot. Close the context promptly; long-lived snapshots can delay database
maintenance. Database records, indexes and schema definitions are unchanged.

`GraphReader.history()` uses two parameterized indexed branches: outgoing and
incoming. The incoming branch excludes self-transfers already present in outgoing.
Each branch and the outer merge have `LIMIT max_edges + 1`, ordered by timestamp
and source row. Source row breaks serialization ties, never the historical cutoff.
Existing sender/time and receiver/time indexes serve these predicates. Safe
Psycopg schema quoting and value parameters keep identifiers separate from data.
The SQL is available as `HISTORY_SQL` in `src/mulegraph/graph.py`.

`GraphReader.network()` performs deterministic breadth-first expansion in either
edge direction, preserving edge direction in the returned graph. It retrieves
all incident historical transactions of nodes at distance **less than hops**.
Boundary nodes are included but not expanded: this is an incident neighborhood,
**not an induced subgraph**. Edges between boundary nodes can therefore be absent.
For example, one hop gives the root's complete bounded history, not every transfer
between its counterparties. Nodes are queried at most once per request.

| Resource | Default | Hard ceiling |
| --- | ---: | ---: |
| Nodes | 500 | 2,000 |
| Distinct transactions | 5,000 | 20,000 |
| Hops | 2 allowed; request defaults to 1 | 3 |
| SQL statement timeout | 5 seconds | 30 seconds |

At most `max_nodes` history queries are issued, each returning at most
`max_edges + 1` rows. One optional focal query uses the transaction primary key.
A history, edge or node overflow raises `GraphLimitExceeded`; no partial graph
is returned as if complete. Narrow the window or hop count explicitly. PostgreSQL
query cancellation propagates as an error. There is no automatic expansion of
limits or silent sampling. Limits are positive integers; booleans are rejected.

Python stores the bounded graph and one bounded history response, with O(nodes +
edges) retained graph storage. Rows may be fetched from both endpoints across
queries. Caps bound row/object counts, not exact bytes for arbitrary text fields.
PostgreSQL uses local `work_mem=8MB` per operation and no query parallel workers;
this is not a server-total memory limit. The timeout is per statement, not a total
request deadline. Large timestamp ties or many filtered self-transfers can still
require server scanning/sorting; the timeout remains necessary. The complete
5,078,345-transaction dataset is never loaded into NetworkX or Python memory.

## Descriptive statistics

`statistics(graph, account)` returns graph node/edge counts, graph self-transfer
count, account in/out degrees (transaction multiplicity retained), account incident
transaction count, distinct other counterparties, and transaction frequency.
A self-transfer contributes one to each in/out degree but only one to incident
activity; the account itself is excluded from unique counterparties. Frequency
is incident transactions divided by the **full requested window hours**, including
inactive time, matching the earlier fixed-window convention.

Weak/strong component counts and distinct inward/outward reachable accounts
summarize directed connectivity of the returned window. Reachability excludes the
root. These are static directed paths, not chronologically ordered money flows:
a path may combine edges in reverse time order. They do not establish movement
of the same money, beneficial ownership, collusion, or criminality. Boundary-node
statistics and reachability are local-window quantities, not global degrees or
full-network connectivity. No centrality or all-pairs path computation is used.

## Python usage

```python
import os
from datetime import datetime
from mulegraph.graph import Limits, graph_session, statistics

with graph_session(
    os.environ["DATABASE_URL"],
    dataset_id=1,
    limits=Limits(max_nodes=500, max_edges=5000),
) as reader:
    # Illustrative identifiers, not a published real account sample.
    account = ("1", "EXAMPLE_ACCOUNT")
    start = datetime(2022, 9, 1)
    cutoff = datetime(2022, 9, 9)
    transfers = reader.history(account, start, cutoff)
    investigation = reader.network(account, start, cutoff, hops=2)
    summary = statistics(investigation.graph, account)
    # For a known focal transaction, pass focal_source_row=<row at cutoff>.
```

After dependency installation, a reproducible benchmark samples three
fixed transaction positions and the most frequent sender in the first 10,000
source rows, without labels. It runs one/two-hop requests three times, exercises
an over-budget case, and records sanitized query-plan shapes. Its ignored output
contains no account IDs or transaction records. It is a local diagnostic sample,
not a representative population estimate or service-level guarantee.

```sh
uv run --locked --env-file .env python -m mulegraph.graph_benchmark \
  --output data/graph/benchmark-new.json
```

See [measured performance and verification](graph_verification.md).

## Frozen ML environment compatibility

At the graph-foundation stage, NetworkX 3.7 was the only added package; existing dependency versions and frozen
ML/feature source files are unchanged. `pyproject.toml` and `uv.lock` were updated
together through uv. The old files are retained locally under ignored
`data/graph/environment-before-5a/` and in Git commit `e9e9568`.

The frozen ML holdout validator intentionally checks the exact old lock hash.
It will reject this newer graph lock even though model bytes are unchanged.
Those historical files and the private revision are not included in this snapshot.
An exact old audit requires a separately supplied matching source/environment bundle;
see [the environment boundary](reproducibility.md#historical-environment-boundary).
With such a bundle, use an isolated checkout and preserved artifacts; do not edit freeze manifests
or weaken their integrity checks. Aggregate report rendering needs no label
access and remains available. No ML or holdout evaluation was rerun for 5A.
