import { test, expect } from "@playwright/test";

test("portfolio visualization: heatmap cells render, P&L chart has data", async ({ page }) => {
  await page.goto("/");

  // Ensure a position exists so the heatmap has at least one cell.
  await page.getByPlaceholder("Ticker", { exact: true }).fill("RELIANCE");
  await page.getByPlaceholder("Qty").fill("1");
  await page.getByRole("button", { name: "Buy" }).click();

  // Heatmap renders a tinted cell (title carries "% of positions"), not the empty state.
  const heatmap = page.locator("section", { has: page.getByRole("heading", { name: "Portfolio Heatmap" }) });
  const cell = heatmap.locator('div[title*="% of positions"]').first();
  await expect(cell).toBeVisible();
  const bg = await cell.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).toMatch(/rgba?\(/); // colored, not transparent

  // Portfolio Value (P&L) chart has data: startup snapshot guarantees >=1 point,
  // so the empty "No data yet." state is gone and the chart canvas is present.
  const pnl = page.locator("section", { has: page.getByRole("heading", { name: "Portfolio Value" }) });
  await expect(pnl.getByText("No data yet.")).toHaveCount(0);
  await expect(pnl.locator("canvas").first()).toBeVisible();
});
