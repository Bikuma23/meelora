const { test, expect, request } = require("@playwright/test");
const { login, CREDS } = require("./helpers");

const API = process.env.E2E_BASE_URL || process.env.REACT_APP_BACKEND_URL;

test.describe("Platform/company separation & security (P1.13D.2)", () => {
  test("a simple user never sees the platform context switch or platform nav", async ({ page }) => {
    await login(page, "julie");
    await expect(page.getByTestId("context-switcher")).toHaveCount(0);
    await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
    // She sees the financial app instead.
    await expect(page.getByTestId("nav-budget")).toBeVisible();
  });

  test("platform API is fail-closed for non-platform users (403)", async ({ page }) => {
    const ctx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
    const login = await ctx.post("/api/auth/login", { data: CREDS.julie });
    const token = (await login.json()).token;
    const res = await ctx.get("/api/platform/summary", { headers: { Authorization: `Bearer ${token}` } });
    expect(res.status()).toBe(403);
    await ctx.dispose();
  });

  test("platform staff has a workspace membership but NO automatic financial authority path in platform ctx", async ({ page }) => {
    await login(page, "platformAdmin");
    // In platform context there is no financial navigation (budget/accounting).
    await expect(page.getByTestId("nav-budget")).toHaveCount(0);
    await expect(page.getByTestId("nav-acct_dashboard")).toHaveCount(0);
    // Switching to the company context is an explicit, separate action.
    await page.getByTestId("context-company").click();
    await expect(page.getByTestId("nav-budget")).toBeVisible();
  });

  test("platform logs endpoint returns only platform-scoped events (never the tenant stream)", async ({ page }) => {
    const ctx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
    const login = await ctx.post("/api/auth/login", { data: CREDS.platformAdmin });
    const token = (await login.json()).token;
    const auth = { Authorization: `Bearer ${token}` };
    const plat = await (await ctx.get("/api/platform/logs", { headers: auth })).json();
    // Every entry is a platform-scoped event type.
    for (const e of plat) {
      expect(String(e.event_type)).toMatch(/^(platform\.|client\.|client_admin\.|support\.)/);
    }
    await ctx.dispose();
  });
});
