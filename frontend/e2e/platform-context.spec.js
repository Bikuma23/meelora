const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Contexte plateforme (modèle EXTENSION, pas bascule de contexte).
// Employé Meelora AVEC rôle plateforme : menus plateforme conservés
// (Tableau de bord / Sociétés-Clients / Société Meelora / Logs) ; depuis
// « Société Meelora → Accéder », les modules métier réellement autorisés sont
// AJOUTÉS à la sidebar. platform_role n'accorde aucune autorité financière.
test.describe("Platform context — extension (P1.13E)", () => {
  test("platform sidebar : Tableau de bord + Sociétés/Clients + Société Meelora + Logs", async ({ page }) => {
    await login(page, "platformAdmin");
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_clients")).toBeVisible();
    await expect(page.getByTestId("nav-platform_meelora")).toBeVisible();
    await expect(page.getByTestId("nav-platform_logs")).toBeVisible();
    // Aucun des 5 modules métier n'apparaît tant que « Société Meelora » n'est pas accédée.
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
    await expect(page.getByTestId("platform-home")).toBeVisible();
  });

  test("Société Meelora → Accéder : EXTENSION (menus plateforme conservés)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_meelora").click();
    await expect(page.getByTestId("platform-meelora-card")).toBeVisible();
    await page.getByTestId("platform-meelora-access").click();
    await page.waitForTimeout(1000);
    // Les 4 menus plateforme restent présents (extension, pas remplacement).
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_clients")).toBeVisible();
    await expect(page.getByTestId("nav-platform_meelora")).toBeVisible();
    await expect(page.getByTestId("nav-platform_logs")).toBeVisible();
    // La section d'extension « Société Meelora » apparaît. platform@ n'a AUCUN
    // module financier -> l'extension est vide (preuve : platform_role ≠ autorité).
    await expect(page.getByTestId("platform-business-ext")).toBeVisible();
    await expect(page.getByTestId("platform-ext-empty")).toBeVisible();
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
  });

  test("carte interne Meelora (Sociétés / Clients) : Accéder = même extension", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-internal-card")).toBeVisible();
    await page.getByTestId("platform-internal-access").click();
    await page.waitForTimeout(1000);
    await expect(page.getByTestId("platform-business-ext")).toBeVisible();
    // Menus plateforme conservés.
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
  });

  test("Logs plateforme = menu dédié scopé plateforme (aucun flux client agrégé)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_logs").click();
    await expect(page.getByTestId("platform-logs")).toBeVisible();
  });

  test("support platform_role peut entrer dans le contexte plateforme (lecture seule)", async ({ page }) => {
    await login(page, "support");
    await expect(page.getByTestId("platform-home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_meelora")).toBeVisible();
  });
});
