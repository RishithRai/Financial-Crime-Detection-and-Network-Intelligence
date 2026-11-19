import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const output = path.resolve("../data/dashboard/7a");
test("real source 2612189: complete network, real clicks, evidence, timeline and navigation", async ({
  page,
  request,
}) => {
  fs.mkdirSync(output, { recursive: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const defaults = await request.get("/api/transactions/2612189/investigation");
  expect(defaults.ok()).toBeTruthy();
  const day = await defaults.json();
  const wider = await request.get(
    "/api/transactions/2612189/investigation?scope=wide",
  );
  expect(wider.ok()).toBeTruthy();
  const wide = await wider.json();
  await page.goto("/");
  await expect(
    page.getByText("Prioritized transfers", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Transaction reference").fill("2612189");
  await page.getByRole("button", { name: "Find transactions" }).click();
  await expect(
    page.getByText("TRANSFER #2612189", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review transfer →" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Why this transfer deserves a closer look",
    }),
  ).toBeVisible({ timeout: 20000 });
  await page.screenshot({
    path: path.join(output, "review.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Explore connected accounts →" })
    .click();
  await expect(page.getByTestId("network")).toBeVisible({ timeout: 20000 });
  async function verifyGraph(r) {
    const actual = await page.getByTestId("network").evaluate((el) => {
      const cy = el._cyreg.cy;
      return {
        nodes: cy.nodes().map((n) => n.data()),
        edges: cy.edges().map((e) => e.data()),
      };
    });
    const historical = actual.edges
      .filter((e) => !e.focal)
      .flatMap((e) => e.refs)
      .sort((a, b) => a - b);
    expect(historical).toEqual(
      r.transactions.map((t) => t.source_row).sort((a, b) => a - b),
    );
    expect(new Set(actual.nodes.map((n) => n.id)).size).toBe(
      actual.nodes.length,
    );
    expect(actual.edges.filter((e) => e.focal).flatMap((e) => e.refs)).toEqual([
      2612189,
    ]);
    expect(actual.nodes.find((n) => n.root).id).toBe(JSON.stringify(r.root));
    expect(actual.edges.length).toBeGreaterThan(1);
    return {
      nodes: actual.nodes.length,
      arrows: actual.edges.length,
      transfers: historical.length,
    };
  }
  const dayCounts = await verifyGraph(day.report);
  const zoomBefore = await page
    .getByTestId("network")
    .evaluate((el) => el._cyreg.cy.zoom());
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  expect(
    await page.getByTestId("network").evaluate((el) => el._cyreg.cy.zoom()),
  ).toBeGreaterThan(zoomBefore);
  await page.getByRole("button", { name: "Zoom out", exact: true }).click();
  await page.getByTestId("network").scrollIntoViewIfNeeded();
  const panBox = await page.getByTestId("network").boundingBox();
  const panBefore = await page
    .getByTestId("network")
    .evaluate((el) => el._cyreg.cy.pan());
  await page.mouse.move(panBox.x + 30, panBox.y + 30);
  await page.mouse.down();
  await page.mouse.move(panBox.x + 75, panBox.y + 60, { steps: 5 });
  await page.mouse.up();
  expect(
    await page.getByTestId("network").evaluate((el) => el._cyreg.cy.pan()),
  ).not.toEqual(panBefore);

  await page.getByRole("button", { name: "Fit network", exact: true }).click();
  await page.screenshot({
    path: path.join(output, "network-default.png"),
    fullPage: true,
  });
  // Actual canvas node click using Cytoscape's rendered coordinates, not a mocked event.
  const node = await page.getByTestId("network").evaluate((el) => {
    const cy = el._cyreg.cy;
    const n = cy.nodes().filter((n) => !n.data("focalOnly"))[0];
    const p = n.renderedPosition();
    return { x: p.x, y: p.y, id: n.id() };
  });
  const box = await page.getByTestId("network").boundingBox();
  await page.mouse.click(box.x + node.x, box.y + node.y);
  await expect(page.getByLabel("Inspect account")).toHaveValue(node.id);
  await page
    .getByRole("button", { name: "Show all transfers", exact: true })
    .click();
  const edge = await page.getByTestId("network").evaluate((el) => {
    const e = el._cyreg.cy.edges().filter((e) => !e.data("focal"))[0];
    const p = e.renderedMidpoint();
    return { x: p.x, y: p.y };
  });
  await page.getByTestId("network").scrollIntoViewIfNeeded();
  const edgeBox = await page.getByTestId("network").boundingBox();
  await page.mouse.click(edgeBox.x + edge.x, edgeBox.y + edge.y);
  await expect(page.getByText(/This arrow represents/)).toBeVisible();
  await page.locator(".timeline-row").first().click();
  await expect(page.getByTestId("transfer-inspector")).toBeVisible();
  await page.getByText("Advanced scope", { exact: true }).click();
  await page
    .getByRole("button", { name: "Use wider history", exact: true })
    .click();
  await expect(page.getByTestId("network")).toBeVisible({ timeout: 20000 });
  const wideCounts = await verifyGraph(wide.report);
  await page
    .getByRole("button", { name: "Review investigation cases →" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Choose a review group" }),
  ).toBeVisible();
  if (wide.report.findings.length) {
    await page
      .getByRole("button", { name: "Show sequence on network →" })
      .first()
      .click();
    await expect(
      page.getByText(/supporting transfers highlighted in green/),
    ).toBeVisible();
    const highlighted = await page
      .getByTestId("network")
      .evaluate((el) => el._cyreg.cy.edges(".evidence").length);
    expect(highlighted).toBeGreaterThan(0);
  }
  await page.screenshot({
    path: path.join(output, "network-wide-evidence.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /04.*Investigation cases/ }).click();
  await page.screenshot({
    path: path.join(output, "cases.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /03.*Explore network/ }).click();
  await verifyGraph(wide.report);
  expect(errors).toEqual([]);
  fs.writeFileSync(
    path.join(output, "browser-verification.json"),
    JSON.stringify(
      {
        source: 2612189,
        default: dayCounts,
        wide: wideCounts,
        wideFindings: wide.report.findings.length,
        wideCases: wide.report.cases.length,
        canvasNodeClick: true,
        zoomAndPan: true,
        canvasEdgeClick: true,
        timelineInspection: true,
        navigation: true,
        errors,
      },
      null,
      2,
    ),
  );
});

test("two-hop limit is explicit and clearing scope does not retain a stale network", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Transaction reference").fill("2612189");
  await page.getByRole("button", { name: "Find transactions" }).click();
  await page.getByRole("button", { name: "Review transfer →" }).click();
  await page
    .getByRole("button", { name: "Explore connected accounts →" })
    .click();
  await expect(page.getByTestId("network")).toBeVisible({ timeout: 20000 });
  await page.getByText("Advanced scope", { exact: true }).click();
  await page.getByRole("button", { name: "Expand to two hops" }).click();
  await expect(page.getByRole("alert")).toContainText("No partial network");
  await expect(page.getByTestId("network")).toHaveCount(0);
  await page.getByRole("button", { name: "Try the 24-hour scope" }).click();
  await expect(page.getByTestId("network")).toBeVisible({ timeout: 20000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /02.*Review transfer/ }).click();
  await page.screenshot({
    path: path.join(output, "mobile-review.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
