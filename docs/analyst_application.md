# analyst-first investigation application

React and Cytoscape.js provide a separate investigation frontend. A thin FastAPI
adapter delegates to `DashboardData`, `ExplanationService` and the existing
PostgreSQL graph/case services. The Streamlit application remains unchanged and
available as a fallback. No model, feature, threshold, graph rule, case grouping
logic, prediction or real database record was modified.

## Launch and workflow

From the repository root, after installing dependencies as described in the README:

```sh
uv sync --locked
npm ci --prefix frontend
npm run build --prefix frontend
uv run --locked --env-file .env uvicorn mulegraph.investigator_api:app \
  --host 127.0.0.1 --port 8000 --limit-concurrency 8
```

Open http://127.0.0.1:8000. PostgreSQL and the previous immutable local artifacts
must be available. Search source **2612189** in the primary-test period, select
**Review transfer**, read its model context, then **Explore connected accounts**.
Under Advanced scope, **Use wider history** extends the time window; **Expand to
two hops** is a separate, explicit expansion that may exceed existing limits.
Click graph accounts or arrows, inspect individual timeline entries, and select
**Review investigation cases**. Each pattern can highlight its exact supporting
transaction references on the full graph and filter the chronological timeline.

For frontend development, run `npm run dev --prefix frontend` alongside the API;
Vite proxies `/api` to localhost:8000. The built application shares the API origin
and needs no wildcard CORS configuration. The unchanged Streamlit fallback runs:

```sh
uv run --locked --env-file .env streamlit run streamlit_app.py
```

## Faithful visual representation

All historical nodes from the returned report are rendered, including isolated
accounts. Source identities, not transaction content, identify individual transfers.
Composite `(bank, account)` identities remain distinct. Arrows group transfers by
ordered endpoints and paid/received currency pair; reverse relationships and
self-transfers remain separate. Arrow counts and the timeline retain every distinct
source reference. Nothing is sampled away based on the selected account.

The graph begins centered on the requested root and fits the complete returned
neighborhood. Node/edge clicks, zoom buttons, wheel zoom, drag/pan and fit-to-screen
are supported. Selecting evidence changes highlighting, not graph membership.
A highlighted aggregate arrow can contain additional transfers: the timeline
restricts itself to the exact selected evidence references. Every pattern type
uses its original backend references; the frontend does not detect patterns.

The focal transfer is a separate dashed amber arrow. Its endpoints are added only
from that actual transaction, when absent from historical evidence, and identified
as focal-only accounts. Historical node/transfer counts are explicitly separate
from these additions. No focal or same-cutoff peer becomes historical evidence.
Sparse and empty states explain the scope without inferring safety.

A concentric layout and zoom-aware labels replaced an initially crowded force
layout after screenshot inspection. Full account identifiers remain accessible in
expandable summaries and the account/transfer inspector. Display formatting groups
digits and removes redundant decimal zeros without rounding meaningful digits;
exact original paid/received decimal strings remain available in transfer details.
Amounts are never pooled across currencies or converted.

## Interpretation and scope

The default scope is the preceding 24 hours, one hop, with a lower bound of
September 1, 2022. Wider history begins September 1 with the same one-hop scope.
Two-hop expansion is optional. Both use the existing maximum of 500 accounts and
5,000 transfers, five-second SQL timeouts per query, and unchanged candidate,
finding, evidence and case-link limits. An exceeded limit rejects the entire
investigation response; the UI clears stale results. No silent retry changes scope.

Case cards explain overlapping observations and distinct supporting transfers;
case counts are not independent incidents. Account summaries report their own
incident activity, available maximum transaction score and coverage. Training-period
transactions explicitly remain unscored. A lack of patterns is not low risk.

Explanation cards translate verified feature values and contribution directions
into plain language, relative to the frozen model background. Elapsed seconds may
be displayed as approximate minutes; exact observed values and original encoded
SHAP contributions remain in expandable technical details. The SHAP chart shows
the twelve strongest absolute contributions and the full table preserves all inputs.
These are raw-margin influences, not causal evidence or additive probabilities.
No calibrated probability, account label, live alert status or case lifecycle is
invented. Evaluation statistics remain in the Streamlit fallback documentation/UI.

## API and resource boundaries

All application endpoints are GET-only:

| Endpoint | Purpose |
| --- | --- |
| `/api/queue` | Ten saved-score rows with bounded pagination and optional exact source search |
| `/api/transactions/{source}/explanation` | One verified transaction and its explanation, or explicit missing-score status |
| `/api/transactions/{source}/investigation` | Existing case-service output plus separate focal explanation |
| `/api/health` | Local service health, not a database health assertion |

The investigation API derives the cutoff and sender from verified transaction
inputs; callers cannot supply a different focal timestamp. Optional start dates
must be timezone-naive source timestamps between September 1 and the focal time.
There is no write, training, label, arbitrary SQL or filesystem endpoint. Queue
queries retain the existing 256 MiB/two-thread DuckDB budget and ten-second query
interrupt; feature hashing is outside that timeout. Each explanation is one row.
Two concurrent heavy requests are admitted; additional requests receive 429, or
503 from the outer Uvicorn concurrency cap. Artifact checks are not bypassed by a
model cache. Responses have `Cache-Control: no-store`; hosts are restricted locally.

Frontend requests discard outdated responses, keep bounded investigation context
in component state, and clear old evidence on source/scope changes. Timeline and
finding lists paginate. Returned case objects, scores and evidence are never
mutated. The graph conversion rejects duplicate source identities, missing endpoints
and focal leakage instead of manufacturing a plausible graph.

## Verification

See [measured verification](analyst_application_verification.md). Tests include
Python API guards and core-only PostgreSQL integration, frontend graph accounting
and exact monetary formatting, and actual Chrome/Playwright interactions against
source 2612189. Screenshots and row-level browser outputs stay under ignored
`data/dashboard/6d/`, not in Git.

API references: [FastAPI static serving](https://fastapi.tiangolo.com/tutorial/static-files/),
[Cytoscape.js](https://js.cytoscape.org/), and
[Vite proxy configuration](https://vite.dev/config/server-options).

## Remaining limits

This is a local research application, without authentication, persistent analyst
notes, case lifecycle, multi-user authorization or cross-request reconciliation.
Keep the server bound to localhost. Browser tests cover Chrome on this machine,
not a full accessibility/cross-browser audit. Large networks can require zooming
or be rejected. Event-time availability assumptions, left-censored history,
uncalibrated scores and synthetic-data generalization remain unresolved. No
production-readiness or criminality claim is made.
