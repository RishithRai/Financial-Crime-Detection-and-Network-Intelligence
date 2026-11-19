export const accountId = (bank, account) => JSON.stringify([bank, account]);
export const accountName = (bank, account) =>
  `Bank ${bank} · …${account.slice(-6)}`;
export function money(value, currency, exact = false) {
  const [whole, raw] = String(value).split(".");
  const fraction =
    raw === undefined || exact ? raw : raw.replace(/0+$/, "").padEnd(2, "0");
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${fraction === undefined ? "" : "." + fraction} ${currency}`;
}
export const when = (value) => String(value).replace("T", " ");
export const patternNames = {
  fan_in: "Several senders, one recipient",
  fan_out: "One sender, several recipients",
  transaction_chain: "Time-ordered transfer chain",
  circular_flow: "Time-ordered return path",
  rapid_movement: "Closely timed incoming and outgoing transfers",
};
export const patternName = (type) =>
  patternNames[type] || type.replaceAll("_", " ");
export function networkElements(report) {
  const nodes = new Map(
    report.accounts.map((a) => {
      const [bank, account] = a.account;
      return [
        accountId(bank, account),
        {
          data: {
            id: accountId(bank, account),
            bank,
            account,
            label: `Bank ${bank}\n…${account.slice(-6)}`,
            root: accountId(bank, account) === JSON.stringify(report.root),
            focalOnly: false,
          },
        },
      ];
    }),
  );
  const groups = new Map();
  const seen = new Set();
  for (const t of report.transactions) {
    if (seen.has(t.source_row)) throw new Error("Duplicate source transaction");
    seen.add(t.source_row);
    const source = accountId(t.from_bank_id, t.from_account),
      target = accountId(t.to_bank_id, t.to_account);
    if (!nodes.has(source) || !nodes.has(target))
      throw new Error("Missing historical account");
    const id = JSON.stringify([
      source,
      target,
      t.payment_currency,
      t.receiving_currency,
    ]);
    if (!groups.has(id))
      groups.set(id, {
        data: { id: "history:" + id, source, target, refs: [], focal: false },
      });
    groups.get(id).data.refs.push(t.source_row);
  }
  const edges = [...groups.values()];
  for (const edge of edges)
    edge.data.label = `${edge.data.refs.length} transfer${edge.data.refs.length === 1 ? "" : "s"}`;
  if (report.focal) {
    const t = report.focal;
    if (seen.has(t.source_row))
      throw new Error("Focal leaked into historical network");
    for (const [bank, account] of [
      [t.from_bank_id, t.from_account],
      [t.to_bank_id, t.to_account],
    ]) {
      const id = accountId(bank, account);
      if (!nodes.has(id))
        nodes.set(id, {
          data: {
            id,
            bank,
            account,
            label: `Bank ${bank}\n…${account.slice(-6)}`,
            focalOnly: true,
            root: id === JSON.stringify(report.root),
          },
        });
    }
    edges.push({
      data: {
        id: "focal:" + t.source_row,
        source: accountId(t.from_bank_id, t.from_account),
        target: accountId(t.to_bank_id, t.to_account),
        refs: [t.source_row],
        label: "Selected transfer",
        focal: true,
      },
    });
  }
  return {
    elements: [...nodes.values(), ...edges],
    historicalNodes: report.accounts.length,
    historicalTransfers: seen.size,
    relationships: groups.size,
    focalOnlyNodes: [...nodes.values()].filter((n) => n.data.focalOnly).length,
  };
}
export function selectedTransfers(report, selection) {
  const rows = [...report.transactions];
  if (report.focal)
    rows.push({ ...report.focal, score_status: "SELECTED_FOCAL" });
  const filtered = !selection
    ? rows
    : rows.filter((t) =>
        selection.kind === "node"
          ? accountId(t.from_bank_id, t.from_account) === selection.id ||
            accountId(t.to_bank_id, t.to_account) === selection.id
          : selection.refs.includes(t.source_row),
      );
  return filtered.sort(
    (a, b) =>
      a.occurred_at.localeCompare(b.occurred_at) || a.source_row - b.source_row,
  );
}

export function observation(c) {
  const value = c.observed_value;
  if (value === null) return "Earlier history was unavailable for this input.";
  const name = c.source_feature;
  const role = name.startsWith("receiver") ? "recipient" : "sender";
  if (name === "payment_format") return `The payment method was ${value}.`;
  if (name === "sender_sent_count")
    return `The sender had ${value} earlier outgoing transfers.`;
  if (name === "sender_currency_history_count")
    return `The sender had ${value} earlier outgoing transfers in the payment currency.`;
  if (name === "sender_count_1h" || name === "receiver_count_1h")
    return `The ${role} had ${value} recorded transactions in the preceding hour.`;
  if (name.endsWith("mean_gap_seconds"))
    return `The ${role}'s earlier activity was about ${(Number(value) / 60).toFixed(1)} minutes apart on average.`;
  if (name.endsWith("seconds_since_last"))
    return `The ${role}'s preceding activity was about ${(Number(value) / 60).toFixed(1)} minutes earlier.`;
  return `${c.description}: ${value}.`;
}

// Display aggregation only: original case and witness membership never changes.
export function caseEvidence(report, reviewCase) {
  if (!reviewCase) return [];
  const ids = new Set(reviewCase.finding_ids);
  return report.findings.filter((f) => ids.has(f.id));
}
export function patternGroups(findings) {
  const groups = new Map();
  for (const f of findings) {
    if (!groups.has(f.pattern_type)) groups.set(f.pattern_type, []);
    groups.get(f.pattern_type).push(f);
  }
  return [...groups]
    .map(([type, witnesses]) => ({
      type,
      witnesses,
      transactions: [
        ...new Set(
          witnesses.flatMap((f) => f.transactions.map((t) => t.source_row)),
        ),
      ],
      first: witnesses.reduce(
        (a, f) => (a < f.first_at ? a : f.first_at),
        witnesses[0].first_at,
      ),
      last: witnesses.reduce(
        (a, f) => (a > f.last_at ? a : f.last_at),
        witnesses[0].last_at,
      ),
    }))
    .sort((a, b) => a.type.localeCompare(b.type));
}
export function patternExplanation(f) {
  const n = f.transactions.length,
    accounts = f.accounts.length;
  const gap = f.evidence?.elapsed_seconds;
  switch (f.pattern_type) {
    case "fan_in":
      return `${f.evidence.distinct_counterparties} different accounts sent to one recipient within a ${f.evidence.window_seconds / 60}-minute window. This is concentration of incoming activity, not an ordered flow.`;
    case "fan_out":
      return `One account sent to ${f.evidence.distinct_counterparties} different recipients within a ${f.evidence.window_seconds / 60}-minute window. This is distribution of outgoing activity, not an ordered flow.`;
    case "transaction_chain":
      return `${n} transfers link ${accounts} accounts in strictly increasing time${gap === undefined ? "" : `, spanning ${gap} seconds`}. The handoff currencies match; the records do not establish that the same funds moved.`;
    case "circular_flow":
      return `${n} strictly time-ordered transfers return to an earlier account${gap === undefined ? "" : ` over ${gap} seconds`}. This return path is an observation, not proof of a laundering cycle.`;
    case "rapid_movement":
      return `An incoming transfer was followed by an outgoing transfer ${gap} seconds later at the intermediary account. Compatible currencies do not establish that the received money was forwarded.`;
    default:
      return f.interpretation;
  }
}
export function summaryFacts(report, detail) {
  const root = report.accounts.find(
    (a) => accountId(...a.account) === accountId(...report.root),
  );
  const supporting = new Set(report.cases.flatMap((c) => c.transaction_ids));
  const scored = report.transactions.filter(
    (t) => t.score !== null && t.score !== undefined,
  ).length;
  return {
    focal: `Transfer #${detail.source_row} paid ${money(detail.transaction.amount_paid, detail.transaction.payment_currency)} at ${when(detail.occurred_at)}. It is separate from the earlier history below.`,
    activity: root
      ? `The sender has ${root.history.incoming} incoming and ${root.history.outgoing} outgoing transfers in this window, involving ${root.history.unique_counterparties} distinct counterparties. Self-transfers count in both directions.`
      : "No historical account summary is available for the sender.",
    evidence: `${report.findings.length} overlapping pattern witnesses are organized into ${report.cases.length} review groups, using ${supporting.size} distinct supporting transfers. These groups are not independent incidents.`,
    coverage: `${scored} of ${report.transactions.length} historical transfers have saved scores. Unscored evidence is unknown to this ranking, not low risk.`,
    scored,
    supporting: supporting.size,
  };
}

export function elapsedLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "Unknown time gap";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return (
    [
      [days, "d"],
      [hours, "h"],
      [minutes, "min"],
      [rest, "s"],
    ]
      .filter(([n]) => n > 0)
      .map(([n, unit]) => `${n} ${unit}`)
      .join(" ") || "0 s"
  );
}
