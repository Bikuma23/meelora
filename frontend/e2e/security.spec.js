const { test, expect, request } = require("@playwright/test");
const { login, CREDS } = require("./helpers");

const API = process.env.E2E_BASE_URL || process.env.REACT_APP_BACKEND_URL;

test.describe("Platform/company separation & security (P1.13D.2)", () => {
  test("a simple user never sees the platform context switch or platform nav", async ({ page }) => {
    await login(page, "julie");
    await expect(page.getByTestId("context-switcher")).toHaveCount(0);
    await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
    // She sees the company sidebar (business modules gated by her effective access).
    await expect(page.getByTestId("company-nav")).toBeVisible();
  });

  test("platform API is fail-closed for non-platform users (403)", async ({ page }) => {
    const ctx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
    const login = await ctx.post("/api/auth/login", { data: CREDS.julie });
    const token = (await login.json()).token;
    const res = await ctx.get("/api/platform/summary", { headers: { Authorization: `Bearer ${token}` } });
    expect(res.status()).toBe(403);
    await ctx.dispose();
  });

  test("platform staff has a workspace membership but NO automatic financial authority path", async ({ page }) => {
    await login(page, "platformAdmin");
    // Platform sidebar shows no business module until "Société Meelora" is accessed.
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    // Accessing Société Meelora is an explicit action; platform_role grants NO
    // financial module -> the extension is empty (fail-closed).
    await page.getByTestId("nav-platform_meelora").click();
    await page.getByTestId("platform-meelora-access").click();
    await page.waitForTimeout(1000);
    await expect(page.getByTestId("platform-ext-empty")).toBeVisible();
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
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

  test("legacy business routes are gated by module (hidden menu != protection)", async ({ page }) => {
    // Separate request contexts to avoid auth-cookie contamination between users.
    const repCtx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
    await repCtx.post("/api/auth/login", { data: { email: "persona_reporting@accslegro.com", password: "persona123" } });
    const budCtx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
    await budCtx.post("/api/auth/login", { data: { email: "persona_budgets@accslegro.com", password: "persona123" } });
    // Reporting-only user must be refused Budgets & Accounting endpoints.
    expect((await repCtx.get("/api/budget")).status()).toBe(403);
    expect((await repCtx.get("/api/acct/periods")).status()).toBe(403);
    // Budgets-only user reaches Budgets but not Accounting.
    expect((await budCtx.get("/api/budget")).status()).toBe(200);
    expect((await budCtx.get("/api/acct/periods")).status()).toBe(403);
    await repCtx.dispose();
    await budCtx.dispose();
  });

  test("navigation endpoint is fail-closed (404 unknown company, 403 no access)", async ({ page }) => {
    const CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"; // 9434 — reporting has no access
    const ctx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
    await ctx.post("/api/auth/login", { data: { email: "persona_reporting@accslegro.com", password: "persona123" } });
    // Unknown / cross-workspace company => 404 (no enumeration).
    expect((await ctx.get("/api/companies/00000000-0000-0000-0000-000000000000/navigation")).status()).toBe(404);
    // Same workspace but no access => 403 (never 200 with empty modules).
    expect((await ctx.get(`/api/companies/${CB}/navigation`)).status()).toBe(403);
    await ctx.dispose();
  });
});
