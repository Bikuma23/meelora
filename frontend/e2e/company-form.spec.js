const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Formulaire « Créer une société / client » : champs complets +
// modèle fiscal EXTENSIBLE par juridiction (Canada : BN/TPS/TVQ/PST conditionnels).
// Lecture seule côté DB : on ouvre/renseigne le formulaire sans soumettre.
test.describe("Formulaire société / client (P1.13E)", () => {
  test("champs complets + fiscalité conditionnelle par juridiction", async ({ page }) => {
    await login(page, "admin");
    await page.getByTestId("nav-companies").click();
    await expect(page.getByTestId("companies-page")).toBeVisible();
    await page.getByTestId("add-company-btn").click();
    await expect(page.getByTestId("company-form-dialog")).toBeVisible();
    // Identification / adresse / paramètres présents.
    for (const id of ["company-name", "company-legal-name", "company-trade-name", "company-entity-type",
      "company-business-number", "company-city", "company-region", "company-country", "company-jurisdiction",
      "company-currency", "company-language", "company-admin-email", "company-modules"]) {
      await expect(page.getByTestId(id)).toBeVisible();
    }
    // Juridiction Canada + province QC -> TPS/GST + TVQ/QST visibles ; PST masqué.
    await page.getByTestId("company-region").fill("QC");
    await expect(page.getByTestId("tax-bn")).toBeVisible();
    await expect(page.getByTestId("tax-gst")).toBeVisible();
    await expect(page.getByTestId("tax-qst")).toBeVisible();
    await expect(page.getByTestId("tax-pst")).toHaveCount(0);
    // Province BC -> PST apparaît, TVQ disparaît.
    await page.getByTestId("company-region").fill("BC");
    await expect(page.getByTestId("tax-pst")).toBeVisible();
    await expect(page.getByTestId("tax-qst")).toHaveCount(0);
    // Sélection de modules souscrits (toggle).
    await page.getByTestId("module-CONSOLIDATION").click();
    // Administrateur : classification d'identité (aucun accès créé automatiquement).
    await page.getByTestId("company-admin-email").fill(`brand.new.${Date.now()}@nowhere.test`);
    await page.getByTestId("admin-check-btn").click();
    await expect(page.getByTestId("admin-check-result")).toHaveAttribute("data-status", "absent");
    await page.getByTestId("company-admin-email").fill("admin@accslegro.com");
    await page.getByTestId("admin-check-btn").click();
    await expect(page.getByTestId("admin-check-result")).toHaveAttribute("data-status", "verified");
    // Modèle extensible : bascule vers Suisse -> champs fiscaux suisses (UID/TVA).
    await page.getByTestId("company-jurisdiction").click();
    await page.waitForTimeout(200);
    await page.getByRole("option", { name: "Suisse" }).click();
    await expect(page.getByTestId("tax-uid")).toBeVisible();
    await expect(page.getByTestId("tax-vat")).toBeVisible();
    await expect(page.getByTestId("tax-bn")).toHaveCount(0);
  });
});
