import test from "node:test";
import assert from "node:assert/strict";
import cytoscape from "cytoscape";
import {
  networkElements,
  selectedTransfers,
  money,
  accountId,
  elapsedLabel,
  caseEvidence,
  patternGroups,
  patternExplanation,
  summaryFacts,
} from "../src/model.js";
const t = (id, from = "A", to = "B") => ({
  source_row: id,
  from_bank_id: "1",
  from_account: from,
  to_bank_id: "2",
  to_account: to,
  payment_currency: "USD",
  receiving_currency: "USD",
  occurred_at: `2022-09-09T0${id}:00:00`,
});
const report = {
  root: ["1", "A"],
  accounts: [
    { account: ["1", "A"] },
    { account: ["2", "B"] },
    { account: ["3", "A"] },
  ],
  transactions: [t(1), t(2)],
  focal: { ...t(3), to_bank_id: "4", to_account: "C" },
};
test("complete graph preserves isolated nodes, repeated rows, composite identity and separate focal", () => {
  const g = networkElements(report);
  assert.equal(g.historicalNodes, 3);
  assert.equal(g.historicalTransfers, 2);
  assert.equal(g.relationships, 1);
  assert.equal(g.focalOnlyNodes, 1);
  const cy = cytoscape({ headless: true, elements: g.elements });
  assert.equal(cy.nodes().length, 4);
  assert.equal(cy.edges().length, 2);
  assert.deepEqual(cy.edges()[0].data("refs"), [1, 2]);
  assert.notEqual(accountId("1", "A"), accountId("3", "A"));
  cy.destroy();
});
test("no selected-neighbor truncation: all relationships are included", () => {
  const r = {
    ...report,
    transactions: [
      ...report.transactions,
      { ...t(4), from_bank_id: "3", to_account: "B" },
    ],
  };
  assert.equal(networkElements(r).relationships, 2);
});
test("timeline linked to exact source identities and strict event ordering", () => {
  assert.deepEqual(
    selectedTransfers(report, { kind: "pattern", refs: [2, 1] }).map(
      (t) => t.source_row,
    ),
    [1, 2],
  );
  assert.deepEqual(
    selectedTransfers(report, { kind: "node", id: accountId("4", "C") }).map(
      (t) => t.source_row,
    ),
    [3],
  );
});
test("duplicates and focal leakage fail instead of fabricating a graph", () => {
  assert.throws(() =>
    networkElements({ ...report, transactions: [t(1), t(1)] }),
  );
  assert.throws(() => networkElements({ ...report, focal: t(1) }));
});
test("exact decimal strings are grouped without floating point rounding", () => {
  assert.equal(
    money("12345678901234567890.00100", "USD", true),
    "12,345,678,901,234,567,890.00100 USD",
  );
});
test("self transfer and reverse edge retain direction and individual references", () => {
  const a = t(1);
  const b = {
    ...t(2),
    from_bank_id: "2",
    from_account: "B",
    to_bank_id: "1",
    to_account: "A",
  };
  const c = { ...t(3), to_bank_id: "1", to_account: "A" };
  const g = networkElements({
    ...report,
    transactions: [a, b, c],
    focal: null,
  });
  assert.equal(g.relationships, 3);
  assert.equal(g.historicalTransfers, 3);
});

test("display removes redundant zeros without rounding meaningful decimals", () => {
  assert.equal(money("11558.68000000", "Euro"), "11,558.68 Euro");
  assert.equal(money("0.00000100", "Bitcoin"), "0.000001 Bitcoin");
});

test("case display retains exact witnesses and deduplicates only supporting references", () => {
  const f = (id, type, rows) => ({
    id,
    pattern_type: type,
    transactions: rows,
    first_at: rows[0].occurred_at,
    last_at: rows.at(-1).occurred_at,
  });
  const findings = [
    f("a", "transaction_chain", [t(1), t(2)]),
    f("b", "transaction_chain", [t(1), t(3)]),
    f("c", "fan_in", [t(4)]),
  ];
  const before = JSON.stringify(findings);
  const selected = caseEvidence({ findings }, { finding_ids: ["a", "b"] });
  assert.deepEqual(
    selected.map((f) => f.id),
    ["a", "b"],
  );
  const groups = patternGroups(selected);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].transactions, [1, 2, 3]);
  assert.equal(groups[0].witnesses.length, 2);
  assert.equal(groups[0].first, t(1).occurred_at);
  assert.equal(groups[0].last, t(3).occurred_at);
  assert.equal(JSON.stringify(findings), before);
});
test("summary keeps zero scores and unknown coverage distinct and supporting counts unique", () => {
  const r = {
    ...report,
    accounts: [],
    transactions: [
      { ...t(1), score: 0 },
      { ...t(2), score: null },
    ],
    findings: [],
    cases: [{ transaction_ids: [1, 2] }, { transaction_ids: [2] }],
  };
  const facts = summaryFacts(r, {
    source_row: 3,
    occurred_at: t(3).occurred_at,
    transaction: { amount_paid: "1.00", payment_currency: "USD" },
  });
  assert.equal(facts.scored, 1);
  assert.equal(facts.supporting, 2);
  assert.match(facts.coverage, /not low risk/);
  assert.match(facts.activity, /No historical/);
});
test("pattern explanations distinguish ordered paths from concentration and avoid money-flow claims", () => {
  const f = {
    transactions: [t(1), t(2)],
    accounts: [
      ["1", "A"],
      ["2", "B"],
    ],
    evidence: {
      elapsed_seconds: 60,
      distinct_counterparties: 3,
      window_seconds: 3600,
    },
  };
  for (const type of [
    "fan_in",
    "fan_out",
    "transaction_chain",
    "circular_flow",
    "rapid_movement",
  ]) {
    const text = patternExplanation({ ...f, pattern_type: type });
    assert.ok(text.length > 40);
    assert.ok(!text.includes("undefined"));
  }
  assert.match(
    patternExplanation({ ...f, pattern_type: "fan_in" }),
    /not an ordered flow/,
  );
  assert.match(
    patternExplanation({ ...f, pattern_type: "transaction_chain" }),
    /do not establish/,
  );
});

test("analyst timing labels retain exact duration without inventing speed categories", () => {
  assert.equal(elapsedLabel(65760), "18 h 16 min");
  assert.equal(elapsedLabel(0), "0 s");
  assert.equal(elapsedLabel(86401.5), "1 d 1.5 s");
  assert.equal(elapsedLabel(NaN), "Unknown time gap");
  assert.equal(money("-0.00000001", "USD", true), "-0.00000001 USD");
});
