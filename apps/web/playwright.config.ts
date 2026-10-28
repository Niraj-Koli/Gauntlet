import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the whole stack in demo mode, started separately:
//   ADMIN_API_TOKEN=e2e-admin-token docker compose up --build -d
//   E2E_ADMIN_TOKEN=e2e-admin-token npm run test:e2e
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // the tests share one trading floor
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /browse\.spec\.ts/ },
  ],
});
