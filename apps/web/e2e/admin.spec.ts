import { expect, test, type Page } from "@playwright/test";

// The API's ADMIN_API_TOKEN; the stack runs without Supabase, so admin signs in with it.
const token = process.env.E2E_ADMIN_TOKEN ?? "e2e-admin-token";

// Each test starts from a running floor, whatever the one before it left behind.
test.beforeEach(async ({ request }) => {
  const resumed = await request.post("/api/v1/floor/resume", { headers: { Authorization: `Bearer ${token}` } });
  expect(resumed.ok()).toBeTruthy();
});

/** A toast: the confirmation an admin action shows, in the action's own words. */
const toast = (page: Page, text: string) => page.getByRole("region", { name: /Notifications/ }).getByText(text);

async function signIn(page: Page) {
  await page.goto("/admin");
  await page.getByLabel("Admin token").fill(token);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Admin", level: 1, exact: true })).toBeVisible();
}

test("a wrong token is turned away", async ({ page }) => {
  await page.goto("/admin");
  await page.getByLabel("Admin token").fill("not-the-token");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "That token wasn't accepted" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Admin", level: 1, exact: true })).toHaveCount(0);
});

test("pause and resume the floor", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Pause floor" }).click();
  await expect(toast(page, "Floor paused")).toBeVisible();
  await page.getByRole("button", { name: "Resume floor" }).click();
  await expect(toast(page, "Floor resumed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause floor" })).toBeVisible();
});

test("queue a run for one trader", async ({ page }) => {
  await signIn(page);
  const warren = page.getByRole("listitem").filter({ hasText: "Warren" });
  await expect(warren.getByRole("button", { name: "Run now" })).toBeEnabled({ timeout: 30_000 });
  await warren.getByRole("button", { name: "Run now" }).click();
  await expect(toast(page, "Run queued for Warren")).toBeVisible();
});

test("add a trader, see it on the floor, then delete it", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Add trader" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a trader" });
  await dialog.getByLabel("Name").fill("Ellie");
  await dialog.getByLabel("Style").fill("Dividends");
  await dialog.getByLabel("Strategy").fill("Buy steady dividend payers and hold them.");
  await dialog.getByRole("button", { name: "Add trader" }).click();
  await expect(page.getByText(/Ellie/).first()).toBeVisible();

  await page.goto("/traders/ellie");
  await expect(page.getByRole("heading", { name: "Ellie", level: 1 })).toBeVisible();

  await page.goto("/admin");
  await page.getByRole("button", { name: "Delete Ellie" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete trader" }).click();
  await expect(toast(page, "Ellie deleted")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete Ellie" })).toHaveCount(0);
});
