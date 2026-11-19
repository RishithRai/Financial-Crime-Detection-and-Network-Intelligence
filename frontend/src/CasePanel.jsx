import React, { useState } from "react";
import Network from "./Network";
import EvidenceQuality from "./EvidenceQuality";
import {
  caseEvidence,
  patternGroups,
  patternName,
  patternExplanation,
  when,
  money,
  accountName,
} from "./model";
function Witnesses({ findings, onFinding, quality }) {
  const groups = patternGroups(findings);
  const [type, setType] = useState(groups[0]?.type),
    [index, setIndex] = useState(0);
  const group = groups.find((g) => g.type === type) || groups[0];
  if (!group) return <p>No supporting witnesses in this group.</p>;
  const f = group.witnesses[Math.min(index, group.witnesses.length - 1)];
  return (
    <section
      className="panel"
      data-testid="case-evidence"
      data-total={findings.length}
    >
      <span className="eyebrow">REPEATED OBSERVATIONS, SUMMARIZED</span>
      <h2>Patterns within this group</h2>
      <p>
        Counts below are overlapping witnesses, not separate incidents. Each
        original witness remains inspectable.
      </p>
      <div className="pattern-tabs">
        {groups.map((g) => (
          <button
            key={g.type}
            aria-pressed={g.type === group.type}
            onClick={() => {
              setType(g.type);
              setIndex(0);
            }}
          >
            {patternName(g.type)}
            <small>
              {g.witnesses.length} witnesses · {g.transactions.length} distinct
              transfers
            </small>
          </button>
        ))}
      </div>
      <p>
        {when(group.first)} to {when(group.last)}
      </p>
      <div
        className="witness-detail"
        data-testid="witness-detail"
        data-id={f.id}
      >
        <div className="panel-heading">
          <h3>
            Witness {index + 1} of {group.witnesses.length}
          </h3>
          <div className="toolbar">
            <button disabled={!index} onClick={() => setIndex(index - 1)}>
              Previous witness
            </button>
            <label>
              Go to witness
              <input
                aria-label="Go to witness"
                type="number"
                min="1"
                max={group.witnesses.length}
                value={index + 1}
                onChange={(e) => {
                  const i = Number(e.target.value);
                  if (
                    Number.isInteger(i) &&
                    i >= 1 &&
                    i <= group.witnesses.length
                  )
                    setIndex(i - 1);
                }}
              />
            </label>
            <button
              disabled={index + 1 >= group.witnesses.length}
              onClick={() => setIndex(index + 1)}
            >
              Next witness
            </button>
          </div>
        </div>
        <p>{patternExplanation(f)}</p>
        <EvidenceQuality quality={quality?.findings[f.id]} />
        <p className="footnote">
          A reason to inspect timing and purpose, not a conclusion about
          wrongdoing. Fan observations may be simultaneous; only ordered paths
          imply increasing event times.
        </p>
        <ol className="sequence-preview">
          {[...f.transactions]
            .sort(
              (a, b) =>
                a.occurred_at.localeCompare(b.occurred_at) ||
                a.source_row - b.source_row,
            )
            .map((t) => (
              <li key={t.source_row}>
                <time>{when(t.occurred_at)}</time>
                <strong>{money(t.amount_paid, t.payment_currency)}</strong>
                <span>
                  {accountName(t.from_bank_id, t.from_account)} →{" "}
                  {accountName(t.to_bank_id, t.to_account)}
                </span>
              </li>
            ))}
        </ol>
        <button className="primary" onClick={() => onFinding(f)}>
          Show sequence on network →
        </button>
        <details>
          <summary>Original identifiers and supporting evidence</summary>
          <p>{f.accounts.map((a) => a.join(" / ")).join(" · ")}</p>
          <p>Witness ID: {f.id}</p>
          <p>Sources: {f.transactions.map((t) => t.source_row).join(", ")}</p>
          <pre>{JSON.stringify(f.evidence, null, 2)}</pre>
        </details>
      </div>
    </section>
  );
}
export default function CasePanel({
  report,
  quality,
  selectedCase,
  onCase,
  onFinding,
  onFullNetwork,
  onInspect,
}) {
  if (!report.cases.length)
    return (
      <section className="panel">
        <h2>No review groups in this scope</h2>
        <p>
          This is not evidence of low risk. Inspect individual transfers or
          explicitly widen the historical scope.
        </p>
        <button onClick={onFullNetwork}>Return to full network</button>
      </section>
    );
  const current = selectedCase || report.cases[0],
    findings = caseEvidence(report, current);
  return (
    <>
      <div className="section-heading">
        <h2>Choose a review group</h2>
        <span>
          {report.cases.length} groups · {report.findings.length} overlapping
          witnesses retained
        </span>
      </div>
      <div className="case-list" role="group" aria-label="Review groups">
        {report.cases.map((c, i) => (
          <button
            key={c.id}
            data-testid="review-group"
            data-id={c.id}
            aria-pressed={current.id === c.id}
            className={"case-card " + (current.id === c.id ? "selected" : "")}
            onClick={() => onCase(c)}
          >
            <span className="eyebrow">REVIEW GROUP {i + 1}</span>
            <h3>
              {Object.keys(c.pattern_counts).map(patternName).join(" · ")}
            </h3>
            <p>
              {c.accounts.length} accounts · {c.transaction_ids.length} distinct
              transfers
            </p>
            <small>{c.finding_count} overlapping witnesses</small>
            <small>
              {when(c.first_at)} → {when(c.last_at)}
            </small>
            <small>
              {c.ml_summary.scored_transactions}/
              {c.ml_summary.distinct_transactions} supporting transfers scored
            </small>
          </button>
        ))}
      </div>
      <section
        className="panel"
        data-testid="selected-case"
        data-id={current.id}
        data-witness-count={findings.length}
      >
        <div className="panel-heading">
          <h2>Selected group's evidence</h2>
          <button onClick={onFullNetwork}>Return to full network</button>
        </div>
        <div className="case-metrics">
          <div>
            <strong>{current.accounts.length}</strong> accounts
          </div>
          <div>
            <strong>{current.transaction_ids.length}</strong> distinct transfers
          </div>
          <div>
            <strong>{current.finding_count}</strong> overlapping witnesses
          </div>
        </div>
        <p>
          {when(current.first_at)} to {when(current.last_at)}. Evidence below is
          restricted to this group.
        </p>
        <div className="coverage-note">
          {current.ml_summary.scored_transactions} supporting transfers scored;{" "}
          {current.ml_summary.unscored_transactions} unscored. Missing scores
          are not low scores.
          {Object.entries(current.ml_summary.unscored_reasons).map(
            ([reason, n]) => (
              <span key={reason}>
                {" "}
                {n} {reason.replaceAll("_", " ").toLowerCase()}.
              </span>
            ),
          )}
        </div>
        <details>
          <summary>Accounts involved and original group details</summary>
          <ul>
            {current.accounts.map((a) => (
              <li key={JSON.stringify(a)}>
                Bank {a[0]} / Account {a[1]}
              </li>
            ))}
          </ul>
          <p>Group ID: {current.id}</p>
          <p>
            Supporting source references: {current.transaction_ids.join(", ")}
          </p>
          <p>
            {current.reason_codes
              .map((s) => s.replaceAll("_", " ").toLowerCase())
              .join(" · ")}
          </p>
        </details>
      </section>
      <Network
        report={report}
        selection={{ kind: "case", refs: current.transaction_ids }}
        onSelect={onInspect}
        onReset={onFullNetwork}
      />
      <Witnesses
        key={current.id}
        findings={findings}
        onFinding={onFinding}
        quality={quality}
      />
    </>
  );
}
