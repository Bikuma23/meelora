const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — persona UX walkthroughs. NOTE: the legacy financial modules
// (Salaires & Budget, Comptabilité) still use the P1.10 role gate and are NOT
// yet wired to the new module/permission model — so this suite asserts CONTEXT
// & navigation clarity per persona, not per-module financial gating (future).
const PERSONAS = [
  { key: { email: "persona_employe@accslegro.com", password: "persona123" }, name: "B Employé" },
  { key: { email: "persona_clientadmin@accslegro.com", password: "persona123" }, name: "C Client Admin" },
  { key: { email: "persona_junior@accslegro.com", password: "persona123" }, name: "D Junior" },
  { key: { email: "persona_finance@accslegro.com", password: "persona123" }, name: "E Finance" },
  { key: { email: "persona_reporting@accslegro.com", password: "persona123" }, name: "F Reporting" },
  { key: { email: "persona_multi@accslegro.com", password: "persona123" }, name: "G Multi-société" },
  { key: { email: "persona_consol@accslegro.com", password: "persona123" }, name: "H Consolidation" },
];

test.describe("Persona UX & separation (P1.13E)", () => {
  for (const p of PERSONAS) {
    test(`${p.name} lands in the company app with NO platform context`, async ({ page }) => {
      await login(page, p.key);
      // No platform role -> no context switch, no platform nav.
      await expect(page.getByTestId("context-switcher")).toHaveCount(0);
      await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
      // The financial app shell is available.
      await expect(page.getByTestId("nav-budget")).toBeVisible();
      // Breadcrumb tells the persona where they are.
      await expect(page.getByTestId("breadcrumb")).toBeVisible();
    });
  }

  test("multi-société persona (G) can switch companies in the accounting selector", async ({ page }) => {
    await login(page, { email: "persona_multi@accslegro.com", password: "persona123" });
    await page.getByTestId("nav-acct_dashboard").click();
    await expect(page.getByTestId("company-select")).toBeVisible();
    await page.getByTestId("company-select").click();
    await expect(page.locator('[data-testid^="company-option-"]')).toHaveCount(2);
  });

  test("platform_admin sees the context switch that separates platform from Société Meelora", async ({ page }) => {
    await login(page, { email: "platform@meelora.com", password: "platform123" });
    await expect(page.getByTestId("context-switcher")).toBeVisible();
    await expect(page.getByTestId("platform-home")).toBeVisible();
    // Company context is a separate, explicit space.
    await page.getByTestId("context-company").click();
    await expect(page.getByTestId("nav-budget")).toBeVisible();
    await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
  });
});
