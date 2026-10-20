import { test, expect } from "@playwright/test";

const DEFAULT_WATCHLIST = [
  "HEROMOTOCO", "BEL", "PIDILITIND", "LTF", "HDFCBANK",
  "INFY", "RELIANCE", "TCS", "ICICIBANK", "TATAMOTORS",
];

test("fresh start: default watchlist, Rs 10 lakh cash, prices streaming", async ({ page }) => {
  await page.goto("/");

  // All 10 default tickers appear in the watchlist (first cell of each row).
  const watchlist = page.locator("section", { has: page.getByRole("heading", { name: "Watchlist" }) });
  for (const t of DEFAULT_WATCHLIST) {
    await expect(watchlist.getByText(t, { exact: true })).toBeVisible();
  }

  // Cash balance shows Rs 10 lakh. formatMoney renders an Indian-grouped string.
  await expect(page.getByText(/10,00,000/).first()).toBeVisible();

  // Prices are streaming: HDFCBANK's price cell is populated and then changes.
  const priceCell = watchlist
    .locator("tr", { has: page.getByText("HDFCBANK", { exact: true }) })
    .locator("td")
    .nth(1);
  await expect(priceCell).not.toHaveText("—", { timeout: 10_000 });
  const first = await priceCell.textContent();
  await expect
    .poll(async () => priceCell.textContent(), { timeout: 15_000, intervals: [500] })
    .not.toBe(first);
});
