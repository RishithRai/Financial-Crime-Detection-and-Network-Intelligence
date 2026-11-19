import React from "react";
import { summaryFacts } from "./model";
export default function InvestigationSummary({ report, detail, onCases }) {
  const facts = summaryFacts(report, detail);
  return (
    <section
      className="panel investigation-summary"
      data-testid="investigation-summary"
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">YOUR INVESTIGATION AT A GLANCE</span>
          <h2>What the evidence tells us</h2>
        </div>
        <button onClick={onCases}>
          Review the {report.cases.length} groups →
        </button>
      </div>
      <p>{facts.focal}</p>
      <div className="summary-columns">
        <div>
          <h3>Model review priority</h3>
          <p>
            {detail.saved_review_score === null ||
            detail.saved_review_score === undefined
              ? "No saved review score is available."
              : `The frozen transaction review score is ${detail.saved_review_score.toFixed(4)}. It prioritizes review; it is not a probability or a judgment about an account.`}
          </p>
        </div>
        <div>
          <h3>Observed activity</h3>
          <p>{facts.activity}</p>
          <p>{facts.evidence}</p>
        </div>
      </div>
      <details>
        <summary>
          Coverage and limits · {facts.scored}/{report.transactions.length}{" "}
          historical transfers scored
        </summary>
        <p>{facts.coverage}</p>
        <p>
          Only the returned time-bounded neighborhood is covered. Neighbor
          histories may be incomplete. Future events and same-cutoff peers are
          excluded. Event-time availability is assumed, not independently
          established.
        </p>
      </details>
      <p className="footnote">
        {report.findings.length
          ? "Review timing, counterparties and transaction purpose using independent records. The patterns do not establish intent or movement of the same money."
          : "No patterns were detected within this scope. This does not establish low risk."}{" "}
        Summary statements use fixed templates and existing evidence only.
      </p>
    </section>
  );
}
