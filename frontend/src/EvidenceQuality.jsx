import React from "react";
import { money, elapsedLabel } from "./model";
export default function EvidenceQuality({ quality }) {
  if (!quality)
    return (
      <p>
        Evidence assessment is unavailable; no quality conclusion can be drawn.
      </p>
    );
  return (
    <section className="evidence-quality" data-testid="evidence-quality">
      <h3>How much does this observation tell us?</h3>
      <p>
        <strong>Supported by the records:</strong> {quality.supports}
      </p>
      <p>
        {quality.scored_transactions}/{quality.distinct_transactions} supporting
        transfers have saved review scores. Missing scores are unknown, not low
        risk.
      </p>
      {quality.descriptors.includes("INCOMPLETE_ACCOUNT_HISTORY") && (
        <p className="coverage-note">
          Some account histories are incomplete outside the returned
          neighborhood. These counts are local context, not complete statements.
        </p>
      )}
      {quality.handoffs.map((h) => (
        <article
          className="handoff"
          key={`${h.incoming_source}:${h.outgoing_source}`}
        >
          <h4>
            Transfer #{h.incoming_source} → #{h.outgoing_source}
          </h4>
          <p>
            {elapsedLabel(h.elapsed_seconds)} apart (
            {h.elapsed_seconds.toLocaleString()} seconds) ·{" "}
            {h.other_local_transactions_between} other local transactions at
            this account strictly between these times.
          </p>
          <dl>
            <dt>Received at the intermediary</dt>
            <dd>{money(h.incoming_received, h.incoming_currency, true)}</dd>
            <dt>Then paid by the intermediary</dt>
            <dd>{money(h.outgoing_paid, h.outgoing_currency, true)}</dd>
          </dl>
          <p>
            {!h.currency_continuity
              ? "Different currencies: amounts cannot be compared. No conversion is inferred."
              : h.amount_relation === "EQUAL_RECORDED_AMOUNTS"
                ? "The recorded amounts are equal. This does not identify the same funds."
                : `Amounts differ. Outgoing minus incoming: ${money(h.outgoing_minus_incoming, h.incoming_currency, true)}. This difference is not a traced balance or loss.`}
          </p>
        </article>
      ))}
      <p>
        <strong>Still uncertain:</strong> {quality.uncertain}
      </p>
      <details>
        <summary>What would help an analyst assess this?</summary>
        <ul>
          {quality.useful_next_evidence.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
        <p>
          History is time-bounded; event-time availability is assumed. Scores do
          not measure evidence quality.
        </p>
        <p>
          {Object.entries(quality.missing_score_reasons)
            .map(([k, v]) => `${v} ${k.replaceAll("_", " ").toLowerCase()}`)
            .join(" · ")}
        </p>
      </details>
    </section>
  );
}
