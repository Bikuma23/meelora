const { test, expect, request } = require("@playwright/test");
const { login, CREDS } = require("./helpers");

const API = process.env.E2E_BASE_URL || process.env.REACT_APP_BACKEND_URL;

async function adminToken(pw) {
  const ctx = await request.newContext({ baseURL: API, ignoreHTTPSErrors: true });
  const r = await ctx.post("/api/auth/login", { data: CREDS.admin });
  const body = await r.json();
  await ctx.dispose();
  return body.token;
}

test.describe("Access administration & lifecycle (P1.13D)", () => {
  test("admin invitation wizard walks through the 4 steps", async ({ page }) => {
    await login(page, "admin");
    // Access console is admin-only (bottom nav).
    await page.getByTestId("nav-access").click();
    await expect(page.getByTestId("access-management")).toBeVisible();
    await page.getByTestId("invite-user-btn").click();
    await expect(page.getByTestId("invite-wizard")).toBeVisible();
    const email = `e2e_invite_${Date.now()}@example.com`;
    await page.getByTestId("invite-email").fill(email);
    await page.getByTestId("invite-next").click(); // -> step 2
    await page.locator('[data-testid^="invite-company-check-"]').first().check();
    await page.getByTestId("invite-next").click(); // -> step 3
    await expect(page.locator('[data-testid^="invite-access-"]').first()).toBeVisible();
    await page.getByTestId("invite-next").click(); // -> step 4 (summary)
    await expect(page.getByTestId("invite-summary")).toBeVisible();
    await page.getByTestId("invite-send").click();
    // Back on the list, the pending invitation count is visible.
    await expect(page.getByTestId("access-management")).toBeVisible();
  });

  test("one-time activation round-trip creates the account and lets the invitee set a password", async ({ page }) => {
    const token = await adminToken();
    const email = `e2e_activate_${Date.now()}@example.com`;
    // Create an invitation via API and capture the activation link (token).
    const ctx = await request.newContext({
      baseURL: API, ignoreHTTPSErrors: true,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    // Fetch a company to target.
    const companies = await (await ctx.get("/api/companies")).json();
    const cid = companies[0].id;
    const inv = await ctx.post("/api/workspace/invitations", {
      data: { email, name: "E2E Invitee", companies: [{ company_id: cid, role: "user" }], access: [], permissions: [] },
    });
    const invBody = await inv.json();
    await ctx.dispose();
    const link = invBody.activation_link;
    expect(link).toBeTruthy();
    const activationToken = new URL(link).searchParams.get("token");
    expect(activationToken).toBeTruthy();

    await page.goto(`/activate?token=${activationToken}`);
    await expect(page.getByTestId("activate-form")).toBeVisible();
    await expect(page.getByTestId("activate-email")).toContainText(email);
    await page.getByTestId("activate-password").fill("Passw0rd!e2e");
    await page.getByTestId("activate-confirm").fill("Passw0rd!e2e");
    await page.getByTestId("activate-submit").click();
    await expect(page.getByTestId("activate-success")).toBeVisible();
  });

  test("invalid activation token shows a safe invalid state", async ({ page }) => {
    await page.goto("/activate?token=obviously-not-a-valid-token");
    await expect(page.getByTestId("activate-invalid")).toBeVisible();
  });

  test("multi-company user sees more than one company in the accounting selector", async ({ page }) => {
    await login(page, { email: "persona_multi@accslegro.com", password: "persona123" });
    // persona_multi has ACCOUNTING on both companies -> accounting nav available.
    await expect(page.getByTestId("company-context-switcher")).toBeVisible();
    await page.getByTestId("company-context-select").click();
    await expect(page.locator('[data-testid^="company-ctx-option-"]')).toHaveCount(2);
  });
});
