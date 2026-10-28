import { expect, test } from "@playwright/test";

const TRADERS = ["Warren", "George", "Ray", "Cathie"];

test("pages run under a strict Content Security Policy without violating it", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) violations.push(message.text());
  });
  const response = await page.goto("/");
  const policy = response?.headers()["content-security-policy"] ?? "";
  expect(policy).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(policy).toContain("frame-ancestors 'none'");
  await expect(page.getByRole("heading", { name: "Standings" })).toBeVisible();
  await page.getByRole("link", { name: /Warren/ }).first().click();
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.getByRole("link", { name: "Arena" }).click();
  await expect(page.getByRole("heading", { name: "Model arena" })).toBeVisible();
  expect(violations).toEqual([]);
});

test("the floor shows every trader, live", async ({ page, isMobile }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "The floor" })).toBeVisible();
  // Phones drop the status badges from the header to make room.
  if (!isMobile) await expect(page.getByRole("banner").getByText("Demo mode")).toBeVisible();
  for (const name of TRADERS) {
    await expect(page.getByRole("link", { name: new RegExp(name) }).first()).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Where the money is" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Activity" })).toBeVisible();
});

test("a trader's page has its chart, trades and runs with their traces", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Warren/ }).first().click();
  await expect(page).toHaveURL(/\/traders\/warren$/);
  await expect(page.getByRole("heading", { name: "Warren", level: 1 })).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible(); // the equity curve

  const sections = page.getByRole("tablist", { name: "Sections" });
  await sections.getByRole("tab", { name: "Runs" }).click();
  // The demo floor runs every trader as soon as it starts, so a finished run is there.
  const run = page.getByRole("tabpanel").getByRole("button", { expanded: false }).first();
  await expect(run).toBeVisible();
  await run.click();
  await expect(page.getByRole("tabpanel").getByRole("button", { expanded: true }).first()).toBeVisible();

  await sections.getByRole("tab", { name: "Strategy" }).click();
  await expect(page.getByRole("tabpanel")).toContainText(/./);
});

test("the arena compares models", async ({ page }) => {
  await page.goto("/arena");
  await expect(page.getByRole("heading", { name: "Model arena" })).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Sharpe" })).toBeVisible();
  await expect(table.getByRole("row")).not.toHaveCount(1); // more than the header
  await expect(page.getByRole("heading", { name: "Return against cost" })).toBeVisible();
});

test("an unknown trader gets a helpful page", async ({ page }) => {
  await page.goto("/traders/nobody");
  await expect(page.getByText("Unknown trader nobody")).toBeVisible();
  await page.getByRole("link", { name: "Back to the floor" }).click();
  await expect(page.getByRole("heading", { name: "The floor" })).toBeVisible();
});
