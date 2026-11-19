import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
test("all five real groups retain 706 witnesses and exact highlighted evidence", async ({
  page,
  request,
}) => {
  const output = path.resolve("../data/dashboard/7a");
  fs.mkdirSync(output, { recursive: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const response = await request.get(
    "/api/transactions/2612189/investigation?scope=wide",
  );
  expect(response.ok()).toBeTruthy();
  const { report, evidence_quality } = await response.json();
  expect(Object.keys(evidence_quality.findings)).toHaveLength(706);
  expect(report.cases).toHaveLength(5);
  expect(report.findings).toHaveLength(706);
  await page.goto("/");
  await page.getByLabel("Transaction reference").fill("2612189");
  await page.getByRole("button", { name: "Find transactions" }).click();
  await page.getByRole("button", { name: "Review transfer →" }).click();
  await page
    .getByRole("button", { name: "Explore connected accounts →" })
    .click();
  await expect(page.getByTestId("network")).toBeVisible({ timeout: 20000 });
  await page.getByText("Advanced scope", { exact: true }).click();
  await page
    .getByRole("button", { name: "Use wider history", exact: true })
    .click();
  await expect(page.getByTestId("investigation-summary")).toContainText(
    "706 overlapping",
  );
  await page.screenshot({
    path: path.join(output, "summary.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Review the 5 groups →" }).click();
  await expect(page.getByTestId("review-group")).toHaveCount(5);
  let total = 0;
  for (const c of report.cases) {
    await page
      .locator(`[data-testid="review-group"][data-id="${c.id}"]`)
      .click();
    await expect(page.getByTestId("selected-case")).toHaveAttribute(
      "data-id",
      c.id,
    );
    await expect(page.getByTestId("case-evidence")).toHaveAttribute(
      "data-total",
      String(c.finding_ids.length),
    );
    total += c.finding_ids.length;
    const actual = await page.getByTestId("network").evaluate((el) => {
      const cy = el._cyreg.cy;
      return {
        all: cy
          .edges()
          .filter((e) => !e.data("focal"))
          .flatMap((e) => e.data("refs")),
        selected: cy.edges(".evidence").map((e) => e.data("refs")),
        nodes: cy.nodes(".evidence").map((n) => n.id()),
      };
    });
    expect(actual.all.sort((a, b) => a - b)).toEqual(
      report.transactions.map((t) => t.source_row).sort((a, b) => a - b),
    );
    const ids = new Set(c.transaction_ids);
    const highlighted = actual.selected.flatMap((refs) =>
      refs.filter((id) => ids.has(id)),
    );
    expect([...new Set(highlighted)].sort((a, b) => a - b)).toEqual(
      [...ids].sort((a, b) => a - b),
    );
    expect(
      actual.selected.every((refs) => refs.some((id) => ids.has(id))),
    ).toBeTruthy();
    expect(actual.nodes.sort()).toEqual(
      c.accounts.map((a) => JSON.stringify(a)).sort(),
    );
    const findings = report.findings.filter((f) =>
      c.finding_ids.includes(f.id),
    );
    for (const type of [
      ...new Set(findings.map((f) => f.pattern_type)),
    ].sort()) {
      const types = [...new Set(findings.map((f) => f.pattern_type))].sort();
      await page
        .locator(".pattern-tabs button")
        .nth(types.indexOf(type))
        .click();
      const group = findings.filter((f) => f.pattern_type === type);
      await page.getByLabel("Go to witness").fill(String(group.length));
      await expect(page.getByTestId("witness-detail")).toHaveAttribute(
        "data-id",
        group.at(-1).id,
      );
      const quality = evidence_quality.findings[group.at(-1).id];
      await expect(page.getByTestId("evidence-quality")).toContainText(
        quality.supports,
      );
      await expect(page.getByTestId("evidence-quality")).toContainText(
        "Missing scores are unknown",
      );
      await expect(page.locator(".handoff")).toHaveCount(
        quality.handoffs.length,
      );
    }
  }
  expect(total).toBe(706);
  await page.screenshot({
    path: path.join(output, "case-summary.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Show sequence on network →" })
    .click();
  await expect(page.getByTestId("network")).toBeVisible();
  await page.screenshot({
    path: path.join(output, "sequence.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Return to full network", exact: true })
    .click();
  expect(
    await page
      .getByTestId("network")
      .evaluate((el) => el._cyreg.cy.edges(".evidence").length),
  ).toBe(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /04.*Investigation cases/ }).click();
  await page.screenshot({
    path: path.join(output, "mobile-cases.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
  fs.writeFileSync(
    path.join(output, "intelligence-verification.json"),
    JSON.stringify(
      { groups: 5, witnesses: total, exactHighlights: true, errors },
      null,
      2,
    ),
  );
});
