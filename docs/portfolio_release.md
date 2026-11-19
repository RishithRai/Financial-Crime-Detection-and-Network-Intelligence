# Historical verification record — October 15, 2026

Recorded against private development revision `ee067a8` (not a public checkout
target). This record describes the October presentation and CI verification. No model, threshold, prediction,
feature, pattern definition, grouping, application service or database record changed.
No real labels or pattern annotations were retrieved; no real-data training or
model evaluation was repeated. Synthetic tests fit tiny disposable models.

## Verification scope

The implementation covers ingestion, historical features, frozen supervised models,
bounded network investigation, case grouping, explanations and the local analyst UI.
The separate pair-feature experiment is validation-only and does not replace the
application model. See the [documentation guide](README.md) for engineering contracts.
A clean-room full-data rebuild remains unverified.

## Actual final verification

| Check | Result |
| --- | --- |
| Existing-workspace PostgreSQL-enabled full suite | **184 passed in 10.54s**, no skips/failures/warnings |
| Tracked-source-only reviewer copy, new Python environment | `uv sync --locked --offline` passed using local cache; **154 passed, 30 expected PostgreSQL skips in 67.44s** |
| Same reviewer copy with synthetic PostgreSQL integration | **184 passed in 12.50s**, no test warnings/failures/skips |
| Ruff in both workspaces | Lint and format passed; final workspace format check reported 118 files |
| Fresh reviewer frontend install | `npm ci --offline --no-audit --no-fund` passed using local npm cache |
| Frontend unit tests | **11 passed** in each workspace |
| Frontend formatting and production builds | Passed in each workspace |
| Local Chrome/Playwright | **3 passed in 43.8s**; workflow assertions recorded no application page errors |
| App health | Local `/api/health` returned `ok`, `local-read-only` |
| Original artifact preservation | All **66** source hashes match; frozen implementation, historical file/manifest and used prediction hashes match |
| 7C audit | All **73** protected originals and graph artifact hashes match; **1,931,048** validation scores reproduced exactly; training-only preprocessing exact |
| 7C label-free audit time | **61.738s**; no new PostgreSQL sample requested (the 7C independent SQL sample is prior evidence) |
| Dependencies | Original Python/frontend manifests and locks unchanged |
| Publication | No push, remote configuration, release tag or public server exposure |

The reviewer copy was made from tracked files only, under ignored
`data/release/7d/reviewer/`. It had no `.env`, datasets, saved models, existing venv
or node_modules. It used this machine's Python/OpenMP installation and caches;
therefore package download availability, another OS and a completely fresh machine
were not verified. Its PostgreSQL suite used only synthetic disposable schemas on
the existing local service, not a newly installed database. The new GitHub workflow
was inspected and its component commands tested locally; hosted CI is not yet run.

Browser tests were copied unchanged apart from screenshot paths into ignored
`frontend/test-results/release-browser/`, with a separate Playwright configuration
and results directory. They exercised actual saved transaction 2612189: default
22-transfer scope, wider 197-transfer network, all five groups/706 witnesses, exact
highlighted references, node/edge selection, chronological evidence, explanations,
navigation and two-hop failure/recovery. New screenshots under
`data/release/7d/browser/` preserve previous stage images. Desktop case and
mobile case screenshots were visually inspected: no new rendering blocker was
found, but dense mobile graph labels and lengthy scrolling remain limitations.
The images contain evidence and were not committed.

The underlying preservation and reload logs are local and are not distributed.
The figures above are historical execution records, not independently downloadable
proof or newly repeated checks. No exact-environment guard was relaxed.

### Execution issues recorded honestly

The initial sandboxed database test attempt could not connect; it reported 19
failures and 29 setup/cleanup errors, with 154 passing tests. Rerunning with local
socket/network access produced the passing full suite above. An initial label-free
audit command mistyped the feature-directory fingerprint and stopped before audit;
the corrected path passed. Neither issue required code changes. The nested reviewer
uv command warned that the parent VIRTUAL_ENV differed and correctly used the
reviewer's own environment. Arrow emitted restricted CPU-cache discovery diagnostics;
Playwright emitted the existing NO_COLOR/FORCE_COLOR terminal warning. Neither
prevented checks. These are not hidden skipped checks or extra experiments.

## Interpretation

These October results are historical evidence, not a claim that every check was
repeated for this snapshot. A clean-room full-data rebuild and hosted CI remain
unverified. See [reproducibility](reproducibility.md) for available reviewer checks
and the boundary imposed by omitted historical environments.
