const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// Cycle de vie société — désormais une fonction de la CONSOLE PLATEFORME MEELORA
// (Sociétés / Clients). Motif OBLIGATOIRE à la désactivation, motif optionnel à la
// réactivation, historique de statut tracé. Opère sur une société jetable créée via
// l'API, avec teardown automatique (aucune pollution « ZZ Lifecycle Test »).
test.describe("Cycle de vie société — console Plateforme (P1.13)", () => {
  let cid = null;

  test.afterEach(async () => {
    // Teardown is handled globally (global-teardown.js removes all "ZZ *" company
    // artifacts from the DB) since there is no company-delete API endpoint.
    cid = null;
  });

  test("motif obligatoire + désactivation + réactivation + historique (Plateforme)", async ({ page }) => {
    await login(page, "platformAdmin");
    cid = await page.evaluate(async () => {
      const r = await fetch("/api/companies", {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "ZZ Lifecycle Test", jurisdiction: "CA", functional_currency: "CAD" }),
      });
      return (await r.json()).id;
    });
    await page.reload();
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();

    const row = page.getByTestId(`platform-company-row-${cid}`);
    await expect(row).toBeVisible();
    await expect(page.getByTestId(`platform-company-status-${cid}`)).toContainText(/Active/i);

    // Désactivation : motif OBLIGATOIRE — le bouton reste désactivé tant que vide.
    await page.getByTestId(`company-deactivate-${cid}`).click();
    await expect(page.getByTestId("deactivate-dialog")).toBeVisible();
    await expect(page.getByTestId("deactivate-confirm")).toBeDisabled();
    await page.getByTestId("status-reason").fill("Fin de mandat client");
    await expect(page.getByTestId("deactivate-confirm")).toBeEnabled();
    await page.getByTestId("deactivate-confirm").click();
    await expect(page.getByTestId(`platform-company-status-${cid}`)).toContainText(/Inactive/i);
    await expect(page.getByTestId(`company-reason-${cid}`)).toContainText("Fin de mandat client");

    // Réactivation via dialogue (motif optionnel).
    await page.getByTestId(`company-reactivate-${cid}`).click();
    await expect(page.getByTestId("reactivate-dialog")).toBeVisible();
    await page.getByTestId("status-reason").fill("Reprise du mandat");
    await page.getByTestId("reactivate-confirm").click();
    await expect(page.getByTestId(`platform-company-status-${cid}`)).toContainText(/Active/i);

    // Historique de statut : au moins 2 entrées (désactivation + réactivation).
    await page.getByTestId(`company-history-${cid}`).click();
    await expect(page.getByTestId("status-history-dialog")).toBeVisible();
    await expect(page.getByTestId("status-history-entry")).toHaveCount(2);
    await expect(page.getByTestId("status-history-dialog")).toContainText("Fin de mandat client");
    await expect(page.getByTestId("status-history-dialog")).toContainText("Reprise du mandat");
  });
});
