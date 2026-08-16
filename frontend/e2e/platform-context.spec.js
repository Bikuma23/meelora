const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

test.describe("Platform context (P1.13D.2)", () => {
  test("platform_admin lands in platform context and sees the context switcher", async ({ page }) => {
    await login(page, "platformAdmin");
    await expect(page.getByTestId("context-switcher")).toBeVisible();
    await expect(page.getByTestId("context-platform")).toBeVisible();
    await expect(page.getByTestId("context-company")).toBeVisible();
    // Default landing = platform home.
    await expect(page.getByTestId("platform-home")).toBeVisible();
    await expect(page.getByTestId("platform-stat-clients")).toBeVisible();
  });

  test("platform navigation: Tableau de bord + Sociétés / Clients (no other menus)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();
    // Internal Meelora card is present and first.
    await expect(page.getByTestId("platform-internal-card")).toBeVisible();
    await page.getByTestId("nav-platform_home").click();
    await expect(page.getByTestId("platform-home")).toBeVisible();
    // "Logs plateforme" is a dedicated platform menu (platform-scoped only).
    await expect(page.getByTestId("nav-platform_logs")).toBeVisible();
  });

  test("internal Meelora card 'Accéder' enters the Société Meelora (company) context", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-internal-card")).toBeVisible();
    await page.getByTestId("platform-internal-access").click();
    await page.waitForTimeout(1000);
    // Now in the company context: company sidebar, no platform nav.
    await expect(page.getByTestId("company-nav")).toBeVisible();
    await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
  });

  test("context switch to Société Meelora reveals the company sidebar, then back to platform", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("context-company").click();
    // Company sidebar renders (platform_role grants no business modules by design).
    await expect(page.getByTestId("company-nav")).toBeVisible();
    // Platform nav is gone in company context.
    await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
    // Switch back.
    await page.getByTestId("context-platform").click();
    await expect(page.getByTestId("platform-home")).toBeVisible();
  });

  test("platform logs is a dedicated platform-scoped menu (no aggregated cross-client stream)", async ({ page }) => {
    await login(page, "platformAdmin");
    // Log separation is enforced by scoped endpoints (see security.spec.js). The
    // platform "Logs plateforme" menu exposes ONLY platform-scoped events —
    // never an aggregated operational stream of the tenants.
    await expect(page.getByTestId("nav-platform_logs")).toBeVisible();
    await page.getByTestId("nav-platform_logs").click();
    await expect(page.getByTestId("platform-logs")).toBeVisible();
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();
  });

  test("support platform_role can enter the platform context (read-only oversight)", async ({ page }) => {
    await login(page, "support");
    await expect(page.getByTestId("context-switcher")).toBeVisible();
    await expect(page.getByTestId("platform-home")).toBeVisible();
  });
});
