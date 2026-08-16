const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// ACCOUNTING A1 — shell & navigation: Comptabilité en accordéon (15 sous-menus),
// placeholders propres, gating par module (P1.13), menu avatar enrichi.
test.describe("ACCOUNTING A1 — shell & navigation", () => {
  test("employé avec ACCOUNTING : module Comptabilité + panneau flottant (15 sous-menus) + placeholder", async ({ page }) => {
    await login(page, "julie"); // employé simple, sans platform_role, ACCOUNTING read
    // Module ACCOUNTING visible (gating P1.13).
    await expect(page.getByTestId("nav-module-ACCOUNTING")).toBeVisible();
    // Ouvrir le panneau flottant du module.
    await page.getByTestId("nav-module-ACCOUNTING").click();
    await expect(page.getByTestId("flyout-ACCOUNTING")).toBeVisible();
    // Sous-menus clés présents dans le panneau.
    for (const k of ["acct_entries", "acct_close", "acct_ledger", "acct_taxes", "acct_reports2"]) {
      await expect(page.getByTestId(`nav-${k}`)).toBeVisible();
    }
    // Un écran non développé = placeholder propre (la sélection ferme le panneau).
    await page.getByTestId("nav-acct_taxes").click();
    await expect(page.getByTestId("acct-placeholder")).toBeVisible();
    await expect(page.getByTestId("acct-placeholder-title")).toContainText("Taxes");
    // Écran fonctionnel A2 : Écritures comptables (réouvrir le panneau).
    await page.getByTestId("nav-module-ACCOUNTING").click();
    await page.getByTestId("nav-acct_entries").click();
    await expect(page.getByTestId("acct-entries-page")).toBeVisible();
    // Clôture & Réconciliation (périodes).
    await page.getByTestId("nav-module-ACCOUNTING").click();
    await page.getByTestId("nav-acct_close").click();
    await expect(page.getByTestId("acct-periods-page")).toBeVisible();
  });

  test("menu avatar : Profil / Administration / Sécurité / Langue", async ({ page }) => {
    await login(page, "admin");
    await page.getByTestId("user-menu-toggle").click();
    await expect(page.getByTestId("menu-profile")).toBeVisible();
    await expect(page.getByTestId("menu-admin")).toBeVisible(); // admin_view
    await expect(page.getByTestId("menu-security")).toBeVisible();
    await expect(page.getByTestId("menu-language")).toBeVisible();
  });

  test("gating par module : un employé sans ACCOUNTING ne voit pas la Comptabilité", async ({ page }) => {
    await login(page, { email: "persona_reporting@accslegro.com", password: "persona123" });
    await expect(page.getByTestId("nav-module-ACCOUNTING")).toHaveCount(0);
  });

  test("multi-société : marc atterrit sur le chooser de mandats", async ({ page }) => {
    await login(page, "marc");
    // marc est multi-société → il atterrit sur « Tous les mandats » (chooser).
    await expect(page.getByTestId("mandats-list")).toBeVisible();
    await expect(page.locator('[data-testid^="mandat-access-"]').first()).toBeVisible();
  });
});
