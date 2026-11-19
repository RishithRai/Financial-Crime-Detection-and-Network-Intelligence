# Analyst application verification

Verified October 15, 2026 (Asia/Kolkata). The React/Cytoscape interface and read-only
FastAPI adapter were exercised against the actual local database and saved
transaction **2612189**, as requested. No real laundering labels or pattern
annotations were retrieved. Existing Streamlit, graph, investigation, case, SHAP,
model, feature and threshold implementations remain unchanged.

## Actual network representation

| Scope | Historical accounts | Historical transfers | Historical grouped arrows | Pattern witnesses | Review groups |
| --- | ---: | ---: | ---: | ---: | ---: |
| Preceding 24 hours, one hop | 7 | 22 | 6 | 0 | 0 |
| September 1 to focal time, one hop | 15 | 197 | 16 | 706 | 5 |

Both visualizations additionally show the **one actual focal transfer** as a
separate dashed arrow and **one focal-only account**. Thus the rendered default
has eight nodes/seven arrows, and the wider view has sixteen nodes/seventeen
arrows. These are complete representations of the returned root neighborhoods,
not a visualization of one arbitrarily selected neighbor. Playwright compared
every historical source reference in Cytoscape's rendered edge data with the API
report and checked root identity, uniqueness and focal separation.

The two-hop, full-history graph probe contained 101 historical accounts and 689
transfers, but the unchanged investigation service exceeded its 1,000-finding
limit. The application reports that rejection, clears the earlier network and
returns no partial findings or misleading zero totals. Browser verification also
checks explicit recovery to the preceding-24-hour scope. No rules or caps were
increased, and no automatic fallback silently narrows a failed request.

The 706 witnesses overlap and reuse evidence. The five cases are organizational
review groups, not five independent incidents. Zero default-scope findings do not
establish safety. No graph structure or attribution is presented as proof of
laundering or verified movement of the same money.

## Completed checks

| Check | Actual result |
| --- | --- |
| `uv sync --locked` | Passed |
| Full PostgreSQL-enabled Pytest | **164 passed in 9.63 seconds**, no failures, skips or warnings |
| Ruff lint and format | Passed; 93 Python files checked by formatting |
| Frontend unit tests | **7 passed** |
| Frontend production build | Passed; vendor chunks split, no oversized-chunk warning in final build |
| Frontend formatting check | Passed |
| Real Chrome/Playwright workflows | **2 passed in 25.2 seconds** |
| Browser page errors | None in the recorded full workflow |
| Frozen source artifacts | All **66** original hashes match |
| Frozen implementation / feature / manifest | All saved hashes match |
| Validation and holdout predictions | All used saved hashes match |
| Pre-existing Python dependency versions | All unchanged |
| Streamlit fallback | Source unchanged; existing tests passed in full suite |

The browser checks exercise queue search, transfer review, verified focal
explanation, complete default and wider networks, zoom, pan, fit, real canvas
node/edge clicks, individual transfer inspection, pattern highlighting and navigation.
A separate check verifies the resource-limit failure/recovery and a 390-pixel
mobile review layout without horizontal page overflow. Screenshots were visually
inspected; these are actual rendered application screenshots, not mockups.

Saved locally under ignored `data/dashboard/6d/`:

- `review.png`: plain-language contribution cards and expandable technical details.
- `network-default.png`: complete default network and transfer timeline.
- `network-wide-evidence.png`: wider network with selected chain evidence highlighted.
- `cases.png`: grouped observations and source-backed evidence cards.
- `mobile-review.png`: responsive transfer review.
- `browser-verification.json` and `preservation.json`: aggregate checks.

Screenshots contain transaction/account evidence and are deliberately not committed.
The original force layout clustered labels; it was replaced with a root-centered
concentric layout and zoom-aware typography after visual inspection. Excess decimal
zeros were removed from display while original strings remain in details. A browser
probe initially clicked using stale scroll coordinates; it was corrected to use
current canvas coordinates and the actual node/edge clicks then passed.

The initial HTTP test client emitted a Starlette deprecation warning. The test-only
dependency was changed to its supported `httpx2` client; final Pytest emitted no
warnings. Playwright's runner emits a terminal `NO_COLOR`/`FORCE_COLOR` environment
warning, unrelated to application behavior. Early two-hop rejection was an expected
resource boundary, not grounds for changing the backend detector.

## Environment and reproduction

New packages include FastAPI 0.143.1, React/React DOM 19.3.1, Cytoscape.js 3.34.3,
Vite 7.3.7 and Playwright 1.64.1. Python dependencies use uv; frontend dependencies
use the committed npm lockfile. Previous Python dependency files were archived in
ignored `data/dashboard/6d/environment/`. All previous versions remain unchanged.
The new Python lock SHA-256 is
`1125a6c6883aaf54cfd63e169df5460ea9a81894a0afac5947d65d2e9f0b8384`.
The frozen explanation service still verifies its original model/preprocessing,
implementation and dependency fingerprints. Earlier exact-lock ML audits retain
their original environment requirement; no guard was relaxed.

With the app running on localhost:8000 and dependencies installed:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
npm test --prefix frontend
npm run check --prefix frontend
npm run build --prefix frontend
npm run test:browser --prefix frontend
```

The browser configuration uses installed macOS Chrome by default. Set `CHROME_PATH`
for another installed Chrome/Chromium executable. Browser tests require the real
local artifacts, database and API; Python integration tests use disposable synthetic
`mg_test_*` schemas. They never alter the real dataset.

## Remaining issues

The wider two-hop investigation for this example remains correctly rejected by
existing finding limits. Scope coverage is local and time-bounded. The new interface
has no authentication, persistent annotations, case lifecycle or multi-user controls;
it remains localhost-only. No comprehensive accessibility/cross-browser audit or
production load test was conducted. Source availability assumptions, missing training
scores, model calibration and synthetic-data generalization remain unresolved.

See [launch instructions, architecture and semantics](analyst_application.md).
