import { test, expect } from "@playwright/test";

test("buy shares: cash decreases, position appears, totals update", async ({ page }) => {
  await page.goto("/");

  const before = await (await page.request.get("/api/portfolio")).json();

  // Market buy of 2 INFY via the trade bar.
  await page.getByPlaceholder("Ticker", { exact: true }).fill("INFY");
  await page.getByPlaceholder("Qty").fill("2");
  await page.getByRole("button", { name: "Buy" }).click();

  // Position row surfaces in the Positions table.
  const positions = page.locator("section", { has: page.getByRole("heading", { name: "Positions" }) });
  await expect(positions.getByText("INFY", { exact: true })).toBeVisible();

  // Cash dropped by the fill cost; a position now exists.
  await expect
    .poll(async () => (await (await page.request.get("/api/portfolio")).json()).cash_balance)
    .toBeLessThan(before.cash_balance);
  const after = await (await page.request.get("/api/portfolio")).json();
  expect(after.positions.find((p: { ticker: string }) => p.ticker === "INFY").quantity).toBe(2);
});
