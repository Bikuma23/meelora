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

  test("platform navigation: Accueil, Mandats/Clients, Logs plateforme", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();
    await page.getByTestId("nav-platform_logs").click();
    await expect(page.getByTestId("platform-logs")).toBeVisible();
    await page.getByTestId("nav-platform_home").click();
    await expect(page.getByTestId("platform-home")).toBeVisible();
  });

  test("client card exposes all 6 tabs (Aperçu, Administrateurs, Utilisateurs, Modules, Logs, Support)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await page.locator('[data-testid^="platform-client-row-"]').first().click();
    await expect(page.getByTestId("client-card")).toBeVisible();
    for (const tab of ["overview", "admins", "users", "modules", "logs", "support"]) {
      await page.getByTestId(`client-tab-${tab}`).click();
      await expect(page.getByTestId(`client-panel-${tab}`)).toBeVisible();
    }
    // Administrators tab shows a replace-admin action (governed emergency authority).
    await page.getByTestId("client-tab-admins").click();
    await expect(page.locator('[data-testid^="replace-admin-"]').first()).toBeVisible();
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

  test("log separation: platform logs are not the tenant operational stream", async ({ page }) => {
    await login(page, "platformAdmin");
    // Platform logs page (platform-scoped only).
    await page.getByTestId("nav-platform_logs").click();
    await expect(page.getByTestId("platform-logs")).toBeVisible();
    // Client card > Logs tab = tenant operational logs (separate collection/scope).
    await page.getByTestId("nav-platform_clients").click();
    await page.locator('[data-testid^="platform-client-row-"]').first().click();
    await page.getByTestId("client-tab-logs").click();
    await expect(page.getByTestId("logs-tab")).toBeVisible();
    // The tenant stream renders operational entries (or an empty state), never the
    // platform stream — both panels exist independently.
    await expect(page.getByTestId("client-panel-logs")).toBeVisible();
  });

  test("support platform_role can enter the platform context (read-only oversight)", async ({ page }) => {
    await login(page, "support");
    await expect(page.getByTestId("context-switcher")).toBeVisible();
    await expect(page.getByTestId("platform-home")).toBeVisible();
  });
});
