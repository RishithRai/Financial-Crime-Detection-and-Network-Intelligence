# Dashboard verification

Verified October 15, 2026 (Asia/Kolkata), using Python 3.12.15, Streamlit 1.66.0
and Plotly 6.9.0. The four-section local dashboard reuses frozen scores, the
historical graph/case service and native TreeSHAP. No real labels or pattern
annotations were accessed. No model, threshold, feature or database record changed.
Overview renders existing aggregate evaluation statistics only.

| Check | Actual result |
| --- | --- |
| `uv sync --locked` | Passed |
| Complete PostgreSQL-enabled Pytest | **153 passed in 7.93 seconds**, no skips, failures or warnings |
| Ruff lint / format | Passed; 88 files formatted |
| New tests | 11 unit/UI cases and one PostgreSQL integration case |
| Streamlit AppTest with real artifacts | All four sections rendered without app errors |
| Real explanation actions | Queue SHAP and case/network unscored paths passed |
| Application server | Launched on 127.0.0.1:8501; health endpoint returned `ok` |
| Original frozen artifacts | All 66 source hashes match |
| Frozen implementation | All holdout-freeze hashes match |
| Historical features / manifest | Both hashes match |
| Saved validation / holdout predictions | All used saved hashes match |
| Previous dependency versions | All unchanged |

The fixed prior focal example reproduced its entire prior case report exactly
(after canonical JSON conversion): 473 historical transfers and 16 review groups.
The first request took 0.304 seconds; the final repeated check took 0.169 seconds.
A 25-row real primary-test queue query took 1.135 seconds. Initializing the
explanation service and explaining one saved transaction took 0.857 seconds.
These are small local wall-time probes, include cache effects, exclude browser
rendering, and are not production latency or memory guarantees. No examples were
selected using labels. Aggregate audit evidence and the verification script remain
under ignored `data/dashboard/`.

Tests cover deterministic queue ties/pagination, exact composite identities,
parameterized filters, invalid resource limits/sorts, artifact corruption,
Streamlit navigation, sanitized failures, stale-evidence removal after a rejected
request and directed plot construction. PostgreSQL adapter tests use a disposable
core-only schema with no labels table and verify temporal exclusion, explicit
training missingness and reproducibility. Existing SHAP, model, graph and case
tests also passed; any label fixtures are synthetic.

The first AppTest run exposed relative script-path resolution, which was fixed.
A real-data comparison initially compared tuples with JSON lists; canonical JSON
comparison confirmed unchanged output. Earlier navigation and case annotation
wiring were corrected before the passing checks. AppTest's standalone real-data
probe logs missing ScriptRunContext diagnostics from its harness; application
checks passed and the Pytest suite emitted no warnings.

Browser automation was unavailable during this verification run,
so screenshots and pixel-level layout/accessibility inspection remain outstanding.
Streamlit AppTest is not a replacement for browser visual review. The actual
server was launched and its HTTP health endpoint checked successfully.

## Environment preservation

Streamlit and Plotly add dependencies and change the lockfile; no existing package
version changed. The preceding dependency files are retained locally under
`data/dashboard/environment-before-6b/`. The new lock SHA-256 is
`d8496cb6bc58f23af994674a788aad7ee11b672d33d563aaab157a5c69a55e20`.
The frozen explanation service's dependency and implementation integrity checks
pass. Earlier exact-lock ML audits remain unchanged and still require their original
source/environment. No guard was weakened to accommodate the UI.

## Reproduction and remaining limits

From the repository root, after installing dependencies as described in the README:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked --env-file .env sh -c \
  'MULEGRAPH_TEST_DATABASE_URL="$DATABASE_URL" uv run --locked pytest'
uv run --locked --env-file .env streamlit run streamlit_app.py
```

The application is local and single-user, without authentication, persistent
annotations, case lifecycle or cross-request reconciliation. Graph displays are
account-focused relationship views; original transfers and time-ordered witnesses
remain inspectable. Resource limits may reject busy accounts, with unknown totals
and no partial result. Training transactions stay unscored. Scores and account
maxima are not calibrated probabilities; SHAP is not causal evidence. Historical
availability and synthetic-data generalization limitations remain unresolved.

See [architecture and workflow](dashboard.md).
