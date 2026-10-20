import { test, expect } from "@playwright/test";

test("SSE resilience: prices keep updating over time", async ({ page }) => {
  await page.goto("/");

  const watchlist = page.locator("section", { has: page.getByRole("heading", { name: "Watchlist" }) });
  const priceCell = watchlist
    .locator("tr", { has: page.getByText("RELIANCE", { exact: true }) })
    .locator("td")
    .nth(1);

  // Sample the streamed price, wait through a brief interruption window, then
  // confirm it is still moving (continued updates, per PLAN.md section 12).
  await expect(priceCell).not.toHaveText("—", { timeout: 10_000 });
  const sample1 = await priceCell.textContent();
  await page.waitForTimeout(3_000);
  await expect
    .poll(async () => priceCell.textContent(), { timeout: 15_000, intervals: [500] })
    .not.toBe(sample1);
});
