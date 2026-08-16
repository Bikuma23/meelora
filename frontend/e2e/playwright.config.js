// P1.13D.2 — Permanent Playwright E2E suite for Meelora.
// Base URL is taken from the frontend .env (REACT_APP_BACKEND_URL serves the app).
const { defineConfig, devices } = require("@playwright/test");
require("dotenv").config({ path: require("path").resolve(__dirname, "../.env") });

const baseURL = process.env.E2E_BASE_URL || process.env.REACT_APP_BACKEND_URL;

module.exports = defineConfig({
  testDir: __dirname,
  globalTeardown: require.resolve("./global-teardown.js"),
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    actionTimeout: 15_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
