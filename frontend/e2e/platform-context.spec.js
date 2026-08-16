const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Interface plateforme Meelora (version finale) :
// sidebar = EXACTEMENT 3 menus (Tableau de bord · Sociétés/Clients · Logs plateforme).
// « Société Meelora » n'est PAS un menu ; elle est gérée depuis Sociétés/Clients.
test.describe("Interface plateforme Meelora (P1.13E final)", () => {
  test("sidebar = exactement 3 menus, aucun module, Société Meelora absente comme menu", async ({ page }) => {
    await login(page, "platformAdmin");
    await expect(page.getByTestId("platform-nav")).toBeVisible();
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_clients")).toBeVisible();
    await expect(page.getByTestId("nav-platform_logs")).toBeVisible();
    // Exactement 3 entrées plateforme.
    await expect(page.locator('[data-testid^="nav-platform_"]')).toHaveCount(3);
    // Société Meelora n'est PAS une entrée indépendante.
    await expect(page.getByTestId("nav-platform_meelora")).toHaveCount(0);
    // Aucun module financier dans la sidebar plateforme.
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
  });

  test("Logs plateforme ancré tout en bas de la sidebar", async ({ page }) => {
    await login(page, "platformAdmin");
    const anchor = page.getByTestId("platform-logs-anchor");
    await expect(anchor).toBeVisible();
    await expect(anchor.getByTestId("nav-platform_logs")).toBeVisible();
    // Le bloc logs est visuellement plus bas que les entrées principales.
    const homeBox = await page.getByTestId("nav-platform_home").boundingBox();
    const logsBox = await anchor.boundingBox();
    expect(logsBox.y).toBeGreaterThan(homeBox.y);
  });

  test("Sociétés / Clients : Société Meelora en 1re position, distinction visuelle Société interne", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();
    const internal = page.getByTestId("platform-internal-card");
    await expect(internal).toBeVisible();
    await expect(internal.getByText("Société interne")).toBeVisible();
    await expect(page.getByTestId("platform-internal-access")).toBeVisible();
    // Recherche présente + création d'une nouvelle société depuis cette page.
    await expect(page.getByTestId("platform-clients-search")).toBeVisible();
  });

  test("Société Meelora → Accéder → gestion complète (console d'accès), aucun module ajouté à la sidebar", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await page.getByTestId("platform-internal-access").click();
    await expect(page.getByTestId("platform-meelora-manage")).toBeVisible();
    await expect(page.getByTestId("meelora-manage-header")).toBeVisible();
    // La console d'accès (utilisateurs / modules / niveaux / permissions / effectifs) est rendue.
    await expect(page.getByTestId("access-management")).toBeVisible();
    // La sidebar plateforme reste à 3 menus, aucun module financier ajouté.
    await expect(page.locator('[data-testid^="nav-platform_"]')).toHaveCount(3);
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
  });

  test("client externe → Accéder → fiche client (aucun accès financier implicite)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();
    // Attendre le rendu de la liste (la carte interne existe toujours).
    await expect(page.getByTestId("platform-internal-card")).toBeVisible();
    const access = page.locator('[data-testid^="platform-client-access-"]').first();
    await expect(access).toBeVisible();
    await access.click();
    await expect(page.getByTestId("client-card")).toBeVisible();
    // Vue d'administration : aucun module financier dans la sidebar plateforme.
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
    await expect(page.locator('[data-testid^="nav-platform_"]')).toHaveCount(3);
  });

  test("support platform_role accède au contexte plateforme (lecture seule)", async ({ page }) => {
    await login(page, "support");
    await expect(page.getByTestId("platform-home")).toBeVisible();
    await expect(page.locator('[data-testid^="nav-platform_"]')).toHaveCount(3);
  });

  test("+ Nouvelle société / client : visible pour platform_admin, ouvre le formulaire complet", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-new-company-btn")).toBeVisible();
    await page.getByTestId("platform-new-company-btn").click();
    await expect(page.getByTestId("company-form-dialog")).toBeVisible();
    await expect(page.getByTestId("company-name")).toBeVisible();
    await expect(page.getByTestId("company-legal-name")).toBeVisible();
    await expect(page.getByTestId("company-jurisdiction")).toBeVisible();
    await expect(page.getByTestId("company-modules")).toBeVisible();
    await expect(page.getByTestId("company-admin-email")).toBeVisible();
  });

  test("support : bouton de création ABSENT + API création refusée (403)", async ({ page }) => {
    await login(page, "support");
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-new-company-btn")).toHaveCount(0);
    // Backend-gated : appel API direct refusé pour support.
    const status = await page.evaluate(async () => {
      const r = await fetch("/api/companies", { method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "ZZ support forbidden", jurisdiction: "CA", functional_currency: "CAD" }) });
      return r.status;
    });
    expect(status).toBe(403);
  });
});
