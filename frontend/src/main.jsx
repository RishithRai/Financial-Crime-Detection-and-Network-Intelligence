import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Network from "./Network";
import CasePanel from "./CasePanel";
import EvidenceQuality from "./EvidenceQuality";
import InvestigationSummary from "./InvestigationSummary";
import {
  accountId,
  accountName,
  money,
  patternName,
  selectedTransfers,
  when,
  observation,
} from "./model";
import "./style.css";
async function get(path) {
  const response = await fetch("/api" + path);
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Check your source reference or date settings and try again.",
    );
  return data;
}
function Account({ bank, account }) {
  return (
    <details className="identifier">
      <summary>{accountName(bank, account)}</summary>
      <span>
        Bank {bank} / Account {account}
      </span>
    </details>
  );
}
function Explain({ detail }) {
  if (!detail) return null;
  if (detail.status !== "EXPLAINED")
    return (
      <div className="notice">
        <h3>No saved review score</h3>
        <p>
          {detail.status.replaceAll("_", " ").toLowerCase()}. No in-sample
          prediction has been substituted.
        </p>
      </div>
    );
  const contributions = [
    ...detail.top_increasing.slice(0, 3),
    ...detail.top_decreasing.slice(0, 2),
  ];
  const top = [...detail.contributions]
    .sort((a, b) => Math.abs(b.raw_contribution) - Math.abs(a.raw_contribution))
    .slice(0, 12);
  const max = Math.max(...top.map((c) => Math.abs(c.raw_contribution)));
  return (
    <section className="panel why">
      <div className="eyebrow">
        MODEL CONTEXT · TRANSFER #{detail.source_row}
      </div>
      <h2>Why this transfer deserves a closer look</h2>
      <p>
        These are the strongest influences on the model's review score, not
        reasons to conclude wrongdoing.
      </p>
      <div className="reasons">
        {contributions.map((c) => (
          <div key={c.feature} className="reason">
            <span className={c.raw_contribution > 0 ? "amber" : "blue"}>
              {c.raw_contribution > 0
                ? "↑ Raises the score"
                : "↓ Lowers the score"}
            </span>
            <h3>{observation(c)}</h3>
          </div>
        ))}
      </div>
      <p className="footnote">
        Influences are relative to the frozen model's training background.
        Correlated inputs share attribution. They do not prove a cause or
        explain an account's intent.
      </p>
      <details>
        <summary>Technical details · SHAP contributions</summary>
        <p>
          Raw margin {detail.raw_margin.toFixed(6)} = baseline{" "}
          {detail.base_value.toFixed(6)} + all feature contributions. Additivity
          error {detail.additivity_error.toExponential(2)}.
        </p>
        <div className="shap-chart">
          {top.map((c) => (
            <div className="shap-row" key={c.feature}>
              <span>{c.description}</span>
              <div className="shap-track">
                <i
                  style={{
                    width: `${(50 * Math.abs(c.raw_contribution)) / max}%`,
                    left:
                      c.raw_contribution < 0
                        ? `${50 - (50 * Math.abs(c.raw_contribution)) / max}%`
                        : "50%",
                    background: c.raw_contribution < 0 ? "#83a7ee" : "#edbb69",
                  }}
                />
              </div>
              <code>{c.raw_contribution.toFixed(4)}</code>
            </div>
          ))}
        </div>
        <p>
          Top 12 by magnitude, in raw-margin units, not probability changes. All
          values are available below.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Encoded feature</th>
                <th>Observed value</th>
                <th>Contribution</th>
              </tr>
            </thead>
            <tbody>
              {detail.contributions.map((c) => (
                <tr key={c.feature}>
                  <td>{c.feature}</td>
                  <td>{String(c.observed_value)}</td>
                  <td>{c.raw_contribution.toPrecision(8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
function App() {
  const [page, setPage] = useState("Review queue"),
    [queue, setQueue] = useState(null),
    [queuePage, setQueuePage] = useState(0),
    [search, setSearch] = useState(""),
    [split, setSplit] = useState("test");
  const [detail, setDetail] = useState(null),
    [investigation, setInvestigation] = useState(null),
    [scope, setScope] = useState("day"),
    [selection, setSelection] = useState(null),
    [transfer, setTransfer] = useState(null),
    [finding, setFinding] = useState(null),
    [caseId, setCaseId] = useState(null),
    [timelinePage, setTimelinePage] = useState(0);
  const [evidenceExplanation, setEvidenceExplanation] = useState(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const request = useRef(0);
  async function action(label, fn) {
    const token = ++request.current;
    setBusy(label);
    setError("");
    try {
      await fn(() => token === request.current);
    } catch (e) {
      if (token === request.current) setError(e.message);
    } finally {
      if (token === request.current) setBusy("");
    }
  }
  function loadQueue(index = 0) {
    setQueue(null);
    action("Loading saved review priorities…", async (current) => {
      const q = await get(
        `/queue?split=${split}&page=${index}&alerts_only=${search ? "false" : "true"}${search ? "&source=" + encodeURIComponent(search) : ""}`,
      );
      if (current()) {
        setQueue(q);
        setQueuePage(index);
      }
    });
  }
  useEffect(() => {
    loadQueue();
  }, []);
  function review(source) {
    setEvidenceExplanation(null);
    setDetail(null);
    setInvestigation(null);
    setSelection(null);
    setTransfer(null);
    setFinding(null);
    setCaseId(null);
    setPage("Review transfer");
    action(
      "Checking the frozen score and its explanation…",
      async (current) => {
        const d = await get(`/transactions/${source}/explanation`);
        if (current()) setDetail(d);
      },
    );
  }
  function explore(nextScope = scope, hops = 1) {
    setEvidenceExplanation(null);
    if (!detail) return;
    setScope(nextScope);
    setInvestigation(null);
    setSelection(null);
    setTransfer(null);
    setFinding(null);
    setCaseId(null);
    setPage("Explore network");
    action("Retrieving bounded earlier history…", async (current) => {
      const r = await get(
        `/transactions/${detail.source_row}/investigation?scope=${nextScope}&hops=${hops}`,
      );
      if (current()) {
        setInvestigation(r);
        setDetail(r.focal_explanation);
      }
    });
  }
  function choose(value) {
    setEvidenceExplanation(null);
    setSelection(value);
    setTimelinePage(0);
    setTransfer(null);
  }
  const report = investigation?.report;
  const timeline = report ? selectedTransfers(report, selection) : [];
  const currentCase = report?.cases.find((c) => c.id === caseId);
  function showFinding(f) {
    setFinding(f);
    choose({ kind: "pattern", refs: f.transactions.map((t) => t.source_row) });
    setPage("Explore network");
  }
  const activeAccount =
    selection?.kind === "node"
      ? report?.accounts.find((a) => accountId(...a.account) === selection.id)
      : null;
  return (
    <div className="app">
      <aside>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Review queue");
          }}
        >
          <span className="brand-icon">M</span>MuleGraph
        </a>
        <span className="eyebrow">INVESTIGATION WORKSPACE</span>
        <nav>
          {[
            "Review queue",
            "Review transfer",
            "Explore network",
            "Investigation cases",
          ].map((name, i) => (
            <button
              key={name}
              disabled={!!busy || (i > 0 && !detail)}
              className={page === name ? "active" : ""}
              onClick={() => setPage(name)}
            >
              <span>0{i + 1}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Local, read-only workspace
          <p>
            Historical saved scores.
            <br />
            No live alerts or account verdicts.
          </p>
          <details>
            <summary>What is a review score?</summary>
            <p>
              A model ranking aid, not a calibrated probability. Review the
              underlying activity and score coverage.
            </p>
          </details>
        </div>
      </aside>
      <main>
        <header>
          <span>
            INVESTIGATE / <b>{page.toUpperCase()}</b>
          </span>
          <span className="pill">Frozen model · history_none</span>
        </header>
        {busy && (
          <div role="status" className="notice loading">
            {busy}
          </div>
        )}
        {error && (
          <div role="alert" className="notice error">
            <strong>We couldn't complete this request</strong>
            <p>{error}</p>
            <button
              onClick={() => {
                setError("");
                setPage("Review queue");
              }}
            >
              Return to review queue
            </button>
            {detail && (
              <button disabled={!!busy} onClick={() => explore("day")}>
                Try the 24-hour scope
              </button>
            )}
          </div>
        )}
        {page === "Review queue" && (
          <>
            <div className="hero">
              <div className="eyebrow">START WITH THE ACTIVITY</div>
              <h1>Find the context behind a flagged transfer.</h1>
              <p>
                Review saved transaction priorities. Follow the connections.
                Check the evidence.
              </p>
            </div>
            <form
              className="searchbar"
              onSubmit={(e) => {
                e.preventDefault();
                loadQueue(0);
              }}
            >
              <label>
                Transaction reference
                <input
                  aria-label="Transaction reference"
                  placeholder="e.g. 2612189"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  pattern="[1-9][0-9]*"
                />
              </label>
              <label>
                Saved-score period
                <select
                  value={split}
                  onChange={(e) => setSplit(e.target.value)}
                >
                  <option value="test">September 9–10 · primary test</option>
                  <option value="validation">September 7–8 · validation</option>
                  <option value="stress">September 11–18 · stress</option>
                </select>
              </label>
              <button className="primary" disabled={!!busy}>
                Find transactions
              </button>
            </form>
            <div className="section-heading">
              <h2>Prioritized transfers</h2>
              <span>
                Highest review score first · {queue?.split || split} · Page{" "}
                {queuePage + 1}
              </span>
            </div>
            <p className="footnote">
              {search
                ? "Exact-source search includes scores below threshold."
                : "Above the original validation-selected threshold."}{" "}
              This is historical review, not a real-time alert feed.
            </p>
            {queue?.transactions.map((t) => (
              <article className="transfer-card" key={t.source_row}>
                <div>
                  <span className="eyebrow">TRANSFER #{t.source_row}</span>
                  <h3>{money(t.amount_paid, t.payment_currency)}</h3>
                  <span>
                    {t.payment_format} · {when(t.occurred_at)}
                  </span>
                </div>
                <div className="route">
                  <Account bank={t.from_bank_id} account={t.from_account} />
                  <span>→</span>
                  <Account bank={t.to_bank_id} account={t.to_account} />
                </div>
                <div className="score">
                  <strong>{t.score.toFixed(4)}</strong>
                  <span>Review score</span>
                </div>
                <button
                  className="primary"
                  disabled={!!busy}
                  onClick={() => review(t.source_row)}
                >
                  Review transfer →
                </button>
              </article>
            ))}
            {queue && !queue.transactions.length && (
              <div className="notice">
                No saved transactions match. Check the period and reference.
                Training-period transactions have no saved predictions.
              </div>
            )}
            <div className="pagination">
              <button
                disabled={!!busy || !queuePage}
                onClick={() => loadQueue(queuePage - 1)}
              >
                ← Previous
              </button>
              <button
                disabled={!!busy || !queue?.more || queuePage >= 1000}
                onClick={() => loadQueue(queuePage + 1)}
              >
                Next page →
              </button>
            </div>
          </>
        )}
        {detail && page !== "Review queue" && (
          <section className="context">
            <div>
              <span className="eyebrow">
                SELECTED TRANSFER #{detail.source_row}
              </span>
              <h1>
                {money(
                  detail.transaction.amount_paid,
                  detail.transaction.payment_currency,
                )}
              </h1>
              <p>
                {when(detail.occurred_at)} · {detail.transaction.payment_format}
              </p>
            </div>
            <div className="route">
              <Account
                bank={detail.transaction.from_bank_id}
                account={detail.transaction.from_account}
              />
              <span>→</span>
              <Account
                bank={detail.transaction.to_bank_id}
                account={detail.transaction.to_account}
              />
            </div>
            <div className="score">
              <strong>
                {detail.saved_review_score?.toFixed(4) ?? "Unscored"}
              </strong>
              <span>Uncalibrated review score</span>
            </div>
          </section>
        )}
        {page === "Review transfer" && detail && (
          <>
            <div className="next-step">
              <p>
                Received:{" "}
                {money(
                  detail.transaction.amount_received,
                  detail.transaction.receiving_currency,
                )}
                .<br />
                Amounts retain original currencies; no conversion or inferred
                matching.
              </p>
              <button
                className="primary"
                disabled={!!busy}
                onClick={() => explore("day")}
              >
                Explore connected accounts →
              </button>
            </div>
            <details className="exact-values">
              <summary>Exact original amounts</summary>
              <p>
                Paid: {detail.transaction.amount_paid}{" "}
                {detail.transaction.payment_currency}
                <br />
                Received: {detail.transaction.amount_received}{" "}
                {detail.transaction.receiving_currency}
              </p>
            </details>
            <Explain detail={detail} />
          </>
        )}
        {(page === "Explore network" || page === "Investigation cases") &&
          detail && (
            <>
              <div className="scopebar">
                <div>
                  <strong>
                    {report ? "Earlier history" : "Choose a historical scope"}
                  </strong>
                  <p>
                    {report
                      ? `${when(report.start)} → strictly before ${when(report.cutoff)}`
                      : "The selected transfer stays separate from earlier evidence."}
                  </p>
                </div>
                <details>
                  <summary>Advanced scope</summary>
                  <p>
                    Default: preceding 24 hours. Wider history: September 1 to
                    the focal time. Both start with the complete one-hop root
                    neighborhood. An optional two-hop search may exceed limits.
                    Caps: 500 accounts, 5,000 transfers, 1,000 findings.
                  </p>
                  <button disabled={!!busy} onClick={() => explore("day")}>
                    Use preceding 24 hours
                  </button>
                  <button disabled={!!busy} onClick={() => explore("wide")}>
                    Use wider history
                  </button>
                  <button disabled={!!busy} onClick={() => explore("wide", 2)}>
                    Expand to two hops
                  </button>
                </details>
                {!report && (
                  <button
                    disabled={!!busy}
                    className="primary"
                    onClick={() => explore("day")}
                  >
                    Load earlier network
                  </button>
                )}
              </div>
              {report && (
                <>
                  <div className="scope-note">
                    Complete returned neighborhood, not the entire dataset.
                    Boundary-account histories may be incomplete. No future or
                    same-cutoff transactions enter historical findings.
                  </div>
                  <InvestigationSummary
                    report={report}
                    detail={detail}
                    onCases={() => setPage("Investigation cases")}
                  />
                  {page === "Explore network" && (
                    <>
                      <Network
                        report={report}
                        selection={selection}
                        onSelect={choose}
                        onReset={() => {
                          setFinding(null);
                          setCaseId(null);
                          choose(null);
                        }}
                      />
                      <div className="workspace-grid">
                        <section className="panel">
                          <div className="panel-heading">
                            <h2>Inspect connections</h2>
                            <button
                              onClick={() => {
                                setSelection(null);
                                setFinding(null);
                                setTimelinePage(0);
                              }}
                            >
                              Show all transfers
                            </button>
                          </div>
                          <label>
                            Account
                            <select
                              aria-label="Inspect account"
                              value={
                                selection?.kind === "node" ? selection.id : ""
                              }
                              onChange={(e) => {
                                if (e.target.value)
                                  choose({
                                    kind: "node",
                                    id: e.target.value,
                                    account: JSON.parse(e.target.value),
                                  });
                              }}
                            >
                              <option value="">
                                Select an account or click a node
                              </option>
                              {report.accounts.map((a) => (
                                <option
                                  key={accountId(...a.account)}
                                  value={accountId(...a.account)}
                                >
                                  {accountName(...a.account)}
                                </option>
                              ))}
                            </select>
                          </label>
                          {activeAccount && (
                            <>
                              <h3>
                                Bank {activeAccount.account[0]} /{" "}
                                {activeAccount.account[1]}
                              </h3>
                              <p>
                                {activeAccount.history.incoming} incoming ·{" "}
                                {activeAccount.history.outgoing} outgoing
                              </p>
                              <p>
                                {activeAccount.ml_summary.scored_transactions}{" "}
                                of{" "}
                                {activeAccount.ml_summary.distinct_transactions}{" "}
                                local transactions have saved scores.
                              </p>
                              <p>
                                Highest available score:{" "}
                                {activeAccount.ml_summary.max_transaction_score?.toFixed(
                                  4,
                                ) ?? "None"}
                              </p>
                              <p className="footnote">
                                {activeAccount.history.complete_for_account
                                  ? "Root history covers the selected window."
                                  : "Partial neighbor history; this is not lifetime activity."}{" "}
                                A maximum transaction score is not an account
                                probability.
                              </p>
                            </>
                          )}
                          {selection?.kind === "edge" && (
                            <p>
                              This arrow represents {selection.refs.length}{" "}
                              individual transfer(s). Inspect each in the
                              timeline.
                            </p>
                          )}
                          {selection?.kind === "node" && !activeAccount && (
                            <p>
                              This account appears only in the focal transfer,
                              with no returned historical account summary.
                            </p>
                          )}
                        </section>
                        <section className="panel">
                          <div className="eyebrow">DESCRIPTIVE EVIDENCE</div>
                          <h2>
                            {report.findings.length} pattern witnesses ·{" "}
                            {report.cases.length} review groups
                          </h2>
                          <p>
                            Patterns may reuse the same transfers. These are
                            overlapping observations, not independent incidents
                            or proof of laundering.
                          </p>
                          <button
                            className="primary"
                            onClick={() => {
                              setCaseId(null);

                              setPage("Investigation cases");
                            }}
                          >
                            Review investigation cases →
                          </button>
                          {finding && (
                            <div className="selected-evidence">
                              <h3>{patternName(finding.pattern_type)}</h3>
                              <p>{finding.interpretation}</p>
                              <EvidenceQuality
                                quality={
                                  investigation.evidence_quality?.findings[
                                    finding.id
                                  ]
                                }
                              />
                              <p>
                                {finding.transactions.length} supporting
                                transfers highlighted in green.
                              </p>
                            </div>
                          )}
                        </section>
                      </div>
                      <section className="panel">
                        <div className="panel-heading">
                          <div>
                            <h2>Chronological transfer timeline</h2>
                            <p>
                              {selection
                                ? "Selected account, relationship or evidence"
                                : "All returned transfers"}{" "}
                              · {timeline.length} transfers · source event time
                            </p>
                          </div>
                        </div>
                        {timeline
                          .slice(timelinePage * 20, (timelinePage + 1) * 20)
                          .map((t) => (
                            <button
                              key={t.source_row}
                              className={
                                "timeline-row " +
                                (t.source_row === detail.source_row
                                  ? "focal"
                                  : "")
                              }
                              onClick={() => {
                                setTransfer(t);
                                setEvidenceExplanation(null);
                              }}
                            >
                              <span className="timeline-dot" />
                              <time>{when(t.occurred_at)}</time>
                              <span>
                                <strong>
                                  {money(t.amount_paid, t.payment_currency)}
                                </strong>
                                <small>
                                  {accountName(t.from_bank_id, t.from_account)}{" "}
                                  → {accountName(t.to_bank_id, t.to_account)}
                                </small>
                              </span>
                              <span>
                                #{t.source_row}
                                <small>
                                  {t.source_row === detail.source_row
                                    ? "Selected focal · separate"
                                    : "Historical transfer"}
                                </small>
                              </span>
                            </button>
                          ))}
                        {!timeline.length && (
                          <p>No transfers for this selection.</p>
                        )}
                        <div className="pagination">
                          <button
                            disabled={!timelinePage}
                            onClick={() => setTimelinePage(timelinePage - 1)}
                          >
                            Earlier page
                          </button>
                          <button
                            disabled={
                              (timelinePage + 1) * 20 >= timeline.length
                            }
                            onClick={() => setTimelinePage(timelinePage + 1)}
                          >
                            Later page
                          </button>
                        </div>
                        {transfer && (
                          <div
                            className="transfer-inspector"
                            data-testid="transfer-inspector"
                          >
                            <h3>Transfer #{transfer.source_row}</h3>
                            <details>
                              <summary>Exact original amounts</summary>
                              <p>
                                {transfer.amount_paid}{" "}
                                {transfer.payment_currency} paid;{" "}
                                {transfer.amount_received}{" "}
                                {transfer.receiving_currency} received.
                              </p>
                            </details>
                            <p>
                              {transfer.from_bank_id} / {transfer.from_account}{" "}
                              → {transfer.to_bank_id} / {transfer.to_account}
                            </p>
                            <p>
                              Paid{" "}
                              {money(
                                transfer.amount_paid,
                                transfer.payment_currency,
                              )}{" "}
                              · Received{" "}
                              {money(
                                transfer.amount_received,
                                transfer.receiving_currency,
                              )}
                            </p>
                            <p>
                              {when(transfer.occurred_at)} ·{" "}
                              {transfer.payment_format}
                            </p>
                            <p>
                              {transfer.source_row === detail.source_row
                                ? "Selected focal transfer; excluded from historical patterns."
                                : (
                                    transfer.score_status ||
                                    "Saved score unavailable"
                                  )
                                    .replaceAll("_", " ")
                                    .toLowerCase()}
                            </p>
                            <button
                              onClick={() =>
                                choose({
                                  kind: "transfer",
                                  refs: [transfer.source_row],
                                })
                              }
                            >
                              Highlight this transfer
                            </button>
                            <button
                              disabled={!!busy}
                              onClick={() =>
                                action(
                                  "Checking explanation…",
                                  async (current) => {
                                    const d = await get(
                                      `/transactions/${transfer.source_row}/explanation`,
                                    );
                                    if (current()) setEvidenceExplanation(d);
                                  },
                                )
                              }
                            >
                              Explain this transfer
                            </button>
                          </div>
                        )}
                      </section>
                      {evidenceExplanation && (
                        <Explain detail={evidenceExplanation} />
                      )}
                    </>
                  )}
                  {page === "Investigation cases" && (
                    <CasePanel
                      quality={investigation.evidence_quality}
                      report={report}
                      selectedCase={currentCase}
                      onCase={(c) => {
                        setCaseId(c.id);
                        setFinding(null);
                        choose({ kind: "case", refs: c.transaction_ids });
                      }}
                      onFinding={showFinding}
                      onInspect={(value) => {
                        choose(value);
                        setPage("Explore network");
                      }}
                      onFullNetwork={() => {
                        setCaseId(null);
                        setFinding(null);
                        choose(null);
                        setPage("Explore network");
                      }}
                    />
                  )}
                </>
              )}
            </>
          )}
        <footer>
          <details>
            <summary>How to interpret this evidence</summary>
            <p>
              A transfer chain is a sequence with strictly increasing times and
              compatible handoff currencies. Graph connections alone do not
              establish such a sequence or that the same funds moved.
              Training-period transactions have no saved scores; coverage gaps
              are visible and never filled with in-sample predictions. All
              results are bounded, retrospective and subject to source
              availability assumptions.
            </p>
          </details>
          <span>
            MuleGraph · Local research workspace · No account verdicts
          </span>
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
