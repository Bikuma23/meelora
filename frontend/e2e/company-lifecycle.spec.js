const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — cycle de vie société : filtre Actives/Inactives, « Rendre inactive »
// (confirmation explicite), « Réactiver ». Opère sur une société jetable créée
// via l'API pour ne pas perturber les autres specs.
test("cycle de vie société : filtre + désactivation (confirmation) + réactivation", async ({ page }) => {
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

  // Désactivation : confirmation explicite requise.
  await page.getByTestId(`company-deactivate-${cid}`).click();
  await expect(page.getByTestId("deactivate-dialog")).toBeVisible();
  await page.getByTestId("deactivate-confirm").click();
  await expect(page.getByTestId(`company-status-${cid}`)).toContainText(/Inactive/i);

  // Filtre Inactives -> la société reste visible.
  await page.getByTestId("company-status-filter").click();
  await page.waitForTimeout(250);
  await page.getByRole("option", { name: "Inactives", exact: true }).click();
  await expect(page.getByTestId(`company-card-${cid}`)).toBeVisible();
  await expect(page.getByTestId(`company-reactivate-${cid}`)).toBeVisible();

  // Réactivation -> redevient Active.
  await page.getByTestId(`company-reactivate-${cid}`).click();
  await page.getByTestId("company-status-filter").click();
  await page.waitForTimeout(250);
  await page.getByRole("option", { name: "Actives", exact: true }).click();
  await expect(page.getByTestId(`company-status-${cid}`)).toContainText(/Active/i);
});
