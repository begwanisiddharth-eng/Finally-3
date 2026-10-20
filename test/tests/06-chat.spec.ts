import { test, expect } from "@playwright/test";

test("AI chat (mocked): buy executes inline and portfolio refetches", async ({ page }) => {
  await page.goto("/");

  const before = await (await page.request.get("/api/portfolio")).json();
  const chat = page.locator("section", { has: page.getByRole("heading", { name: "AI Assistant" }) });

  // Mock LLM: "buy" + a watchlist ticker -> trade qty 1 (PLAN.md section 9).
  await chat.getByPlaceholder("Message FinAlly…").fill("buy 1 INFY");
  await chat.getByRole("button", { name: "Send" }).click();

  // Assistant reply arrives with an inline executed-action line for INFY.
  await expect(chat.getByText("INFY").last()).toBeVisible();
  await expect(chat.getByText(/✓.*INFY/).first()).toBeVisible();

  // Post-turn refetch: a position row surfaces and cash drops.
  const positions = page.locator("section", { has: page.getByRole("heading", { name: "Positions" }) });
  await expect(positions.getByText("INFY", { exact: true })).toBeVisible();
  await expect
    .poll(async () => (await (await page.request.get("/api/portfolio")).json()).cash_balance)
    .toBeLessThan(before.cash_balance);
});
