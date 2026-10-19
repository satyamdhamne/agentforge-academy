import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against a full stack (API + sandbox + frontend).
 * Start it with `docker compose up` (frontend on :8080) or the dev servers (:5173), then:
 *   E2E_BASE_URL=http://localhost:5173 npm run e2e
 * PW_CHROMIUM_PATH lets you reuse an existing Chromium instead of `npx playwright install chromium`.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } }],
});
