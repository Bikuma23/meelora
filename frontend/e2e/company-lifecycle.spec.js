const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — cycle de vie société : filtre Actives/Inactives, « Rendre inactive »
// (motif OBLIGATOIRE + confirmation), « Réactiver » (motif optionnel), et
// historique de statut tracé (date, ancien/nouveau statut, acteur, motif).
// Opère sur une société jetable créée via l'API pour ne pas perturber les autres specs.
test("cycle de vie société : motif obligatoire + désactivation + réactivation + historique", async ({ page }) => {
  await login(page, "admin");
  const cid = await page.evaluate(async () => {
    const r = await fetch("/api/companies", {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "ZZ Lifecycle Test", jurisdiction: "CA", functional_currency: "CAD" }),
    });
    return (await r.json()).id;
  });
  await page.reload();
  await page.getByTestId("nav-companies").click();
  await expect(page.getByTestId("companies-page")).toBeVisible();

  const card = page.getByTestId(`company-card-${cid}`);
  await expect(card).toBeVisible();
  await expect(page.getByTestId(`company-status-${cid}`)).toContainText(/Active/i);

  // Désactivation : le motif est OBLIGATOIRE — le bouton reste désactivé tant que vide.
  await page.getByTestId(`company-deactivate-${cid}`).click();
  await expect(page.getByTestId("deactivate-dialog")).toBeVisible();
  await expect(page.getByTestId("deactivate-confirm")).toBeDisabled();
  await page.getByTestId("status-reason").fill("Fin de mandat client");
  await expect(page.getByTestId("deactivate-confirm")).toBeEnabled();
  await page.getByTestId("deactivate-confirm").click();
  await expect(page.getByTestId(`company-status-${cid}`)).toContainText(/Inactive/i);
  // Le motif est visible sur la fiche société.
  await expect(page.getByTestId(`company-reason-${cid}`)).toContainText("Fin de mandat client");

  // Filtre Inactives -> la société reste visible.
  await page.getByTestId("company-status-filter").click();
  await page.waitForTimeout(250);
  await page.getByRole("option", { name: "Inactives", exact: true }).click();
  await expect(page.getByTestId(`company-card-${cid}`)).toBeVisible();
  await expect(page.getByTestId(`company-reactivate-${cid}`)).toBeVisible();

  // Réactivation via dialogue (motif optionnel).
  await page.getByTestId(`company-reactivate-${cid}`).click();
  await expect(page.getByTestId("reactivate-dialog")).toBeVisible();
  await page.getByTestId("status-reason").fill("Reprise du mandat");
  await page.getByTestId("reactivate-confirm").click();
  await page.getByTestId("company-status-filter").click();
  await page.waitForTimeout(250);
  await page.getByRole("option", { name: "Actives", exact: true }).click();
  await expect(page.getByTestId(`company-status-${cid}`)).toContainText(/Active/i);

  // Historique de statut : au moins 2 entrées (désactivation + réactivation) tracées.
  await page.getByTestId(`company-history-${cid}`).click();
  await expect(page.getByTestId("status-history-dialog")).toBeVisible();
  const entries = page.getByTestId("status-history-entry");
  await expect(entries).toHaveCount(2);
  await expect(page.getByTestId("status-history-dialog")).toContainText("Fin de mandat client");
  await expect(page.getByTestId("status-history-dialog")).toContainText("Reprise du mandat");
});
