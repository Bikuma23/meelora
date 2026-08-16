const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Sociétés / Clients (portefeuille plateforme) : Meelora + 9434 visibles,
// Modifier (platform_admin) persiste + journalise, fiche société → Utilisateurs
// (company_memberships), pas de fuite inter-sociétés, filtre inactives, no-leak.
const MEELORA = "965f0770-8cf2-4199-a99f-819ff270436a";
const QC9434 = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9";

async function gotoClients(page) {
  await login(page, "platformAdmin");
  await page.getByTestId("nav-platform_clients").click();
  await expect(page.getByTestId("platform-clients")).toBeVisible();
}

test.describe("Sociétés / Clients — portefeuille plateforme (P1.13E)", () => {
  test("platform_admin voit Meelora + 9434 ; Meelora en premier", async ({ page }) => {
    await gotoClients(page);
    const internal = page.getByTestId("platform-internal-card");
    const row9434 = page.getByTestId(`platform-company-row-${QC9434}`);
    await expect(internal).toBeVisible();
    await expect(row9434).toBeVisible();
    await expect(internal).toContainText("meelora");
    await expect(row9434).toContainText("9434");
    // Meelora (interne) rendu avant 9434.
    const yi = (await internal.boundingBox()).y;
    const yq = (await row9434.boundingBox()).y;
    expect(yi).toBeLessThan(yq);
  });

  test("Modifier visible sur 9434 et persiste (log before/after backend)", async ({ page }) => {
    await gotoClients(page);
    const editBtn = page.getByTestId(`platform-company-edit-${QC9434}`);
    await expect(editBtn).toBeVisible();
    await editBtn.click();
    await expect(page.getByTestId("company-form-dialog")).toBeVisible();
    const marker = "QC-" + Date.now();
    await page.getByTestId("company-phone").fill(marker);
    await page.getByTestId("company-submit").click();
    await expect(page.getByTestId("company-form-dialog")).toHaveCount(0);
    // Persistance vérifiée via l'API (registre plateforme).
    const phone = await page.evaluate(async (cid) => {
      const r = await fetch("/api/platform/companies", { credentials: "include" });
      const d = await r.json();
      return (d.companies.find((c) => c.id === cid) || {}).phone;
    }, QC9434);
    expect(phone).toBe(marker);
  });

  test("fiche 9434 → Utilisateurs non vide (company_memberships) sans fuite d'une autre société", async ({ page }) => {
    await gotoClients(page);
    await page.getByTestId(`platform-company-access-${QC9434}`).click();
    await expect(page.getByTestId("company-fiche-card")).toBeVisible();
    await page.getByTestId("company-tab-users").click();
    await expect(page.getByTestId("company-users-panel")).toBeVisible();
    // Au moins un utilisateur rattaché.
    await expect(page.locator('[data-testid^="company-user-"]').first()).toBeVisible();
    // marc est membre de 9434 ; julie (Meelora uniquement) NE fuit PAS dans 9434.
    await expect(page.getByTestId("company-users-panel")).toContainText("marc@accslegro.com");
    await expect(page.getByTestId("company-users-panel")).not.toContainText("julie@accslegro.com");
  });

  test("filtre Inactives + réactivation conservent les utilisateurs", async ({ page }) => {
    await gotoClients(page);
    // Désactiver 9434 via l'API (motif obligatoire), puis recharger la vue.
    await page.evaluate(async (cid) => {
      await fetch(`/api/companies/${cid}`, { method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "inactive", status_reason: "Test E2E portefeuille" }) });
    }, QC9434);
    await page.reload();
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-clients")).toBeVisible();
    // Filtre "Inactives" -> 9434 visible avec statut Inactive.
    await page.getByTestId("platform-company-status-filter").selectOption("inactive");
    await expect(page.getByTestId(`platform-company-row-${QC9434}`)).toBeVisible();
    await expect(page.getByTestId(`platform-company-status-${QC9434}`)).toContainText(/Inactive/i);
    // Réactiver via l'API puis vérifier que les utilisateurs sont conservés.
    const usersAfter = await page.evaluate(async (cid) => {
      await fetch(`/api/companies/${cid}`, { method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "active", status_reason: "Reprise E2E" }) });
      const r = await fetch(`/api/platform/companies/${cid}/members`, { credentials: "include" });
      return (await r.json()).users.length;
    }, QC9434);
    expect(usersAfter).toBeGreaterThan(0);
  });

  test("staff plateforme : aucun accès financier implicite (platform@ ACCOUNTING = none)", async ({ page }) => {
    await login(page, "platformAdmin");
    const level = await page.evaluate(async (cid) => {
      const r = await fetch(`/api/companies/${cid}/navigation`, { credentials: "include" });
      if (r.status !== 200) return `http_${r.status}`;
      const d = await r.json();
      const m = (d.modules || []).find((x) => x.module_code === "ACCOUNTING");
      return m ? m.level : "none";
    }, MEELORA);
    expect(level).toBe("none");
  });
});
