import { test, expect } from "@playwright/test";

test("sell shares: cash increases, position updates or disappears", async ({ page }) => {
  await page.goto("/");

  // Establish a known position to sell from (independent of other tests).
  await page.getByPlaceholder("Ticker", { exact: true }).fill("TCS");
  await page.getByPlaceholder("Qty").fill("3");
  await page.getByRole("button", { name: "Buy" }).click();

  const positions = page.locator("section", { has: page.getByRole("heading", { name: "Positions" }) });
  await expect(positions.getByText("TCS", { exact: true })).toBeVisible();
  const afterBuy = await (await page.request.get("/api/portfolio")).json();

  // Sell the whole position; cash rises and the row disappears (sold to zero).
  await page.getByPlaceholder("Ticker", { exact: true }).fill("TCS");
  await page.getByPlaceholder("Qty").fill("3");
  await page.getByRole("button", { name: "Sell" }).click();

  await expect(positions.getByText("TCS", { exact: true })).toHaveCount(0);
  await expect
    .poll(async () => (await (await page.request.get("/api/portfolio")).json()).cash_balance)
    .toBeGreaterThan(afterBuy.cash_balance);
});
