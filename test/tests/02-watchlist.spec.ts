import { test, expect } from "@playwright/test";

test("add and remove a watchlist ticker", async ({ page }) => {
  await page.goto("/");
  const watchlist = page.locator("section", { has: page.getByRole("heading", { name: "Watchlist" }) });

  // Add a real NSE symbol so validate_ticker passes (PLAN.md section 6).
  await page.getByPlaceholder("Add ticker…").fill("WIPRO");
  await watchlist.getByRole("button", { name: "Add" }).click();
  await expect(watchlist.getByText("WIPRO", { exact: true })).toBeVisible();

  // Remove it again via the per-row aria-labelled control.
  await watchlist.getByRole("button", { name: "Remove WIPRO" }).click();
  await expect(watchlist.getByText("WIPRO", { exact: true })).toHaveCount(0);
});
