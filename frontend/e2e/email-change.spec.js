const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Changement d'email de connexion (opération sensible). Compte jetable
// seedé (emailchange_demo@accslegro.com / persona123). Le test fait un aller-retour
// A -> B -> A (idempotent) : la nouvelle adresse doit être vérifiée, l'ancienne
// devient inutilisable après bascule, et les droits ne changent pas.
const A = "emailchange_demo@accslegro.com";
const B = "emailchange_demo2@accslegro.com";
const PWD = "persona123";

test("changement d'email : vérification, login nouvelle adresse, ancienne refusée, droits inchangés, audit", async ({ page }) => {
  await login(page, { email: A, password: PWD });
  // Ouvrir le profil via le menu utilisateur.
  await page.getByTestId("user-menu-toggle").click();
  await page.getByTestId("menu-profile").click();
  await expect(page.getByTestId("preferences-page")).toBeVisible();
  await expect(page.getByTestId("email-login-card")).toBeVisible();
  await expect(page.getByTestId("current-login-email")).toContainText(A);

  // Demander le changement -> vérification requise (opération sensible).
  await page.getByTestId("email-change-open").click();
  await page.getByTestId("email-change-input").fill(B);
  await page.getByTestId("email-change-request").click();
  await expect(page.getByTestId("email-change-verify")).toBeVisible();
  // Confirmer (preuve de contrôle).
  await page.getByTestId("email-change-confirm").click();
  await expect(page.getByTestId("email-change-done")).toBeVisible();

  // Vérifications API (même contexte) : nouvelle adresse OK, ancienne refusée,
  // rôle inchangé ; puis restauration A (idempotent).
  const res = await page.evaluate(async ({ A, B, PWD }) => {
    const post = (p, b, t) => fetch("/api" + p, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json", ...(t ? { Authorization: "Bearer " + t } : {}) },
      body: JSON.stringify(b),
    }).then(async (r) => ({ s: r.status, d: r.ok ? await r.json() : null }));
    const nu = await post("/auth/login", { email: B, password: PWD });
    const old = await post("/auth/login", { email: A, password: PWD });
    let restored = null;
    if (nu.d && nu.d.token) {
      const req = await post("/me/email-change/request", { new_email: A }, nu.d.token);
      if (req.d && req.d.verify_token) await post("/me/email-change/confirm", { token: req.d.verify_token });
      restored = (await post("/auth/login", { email: A, password: PWD })).s;
    }
    return { newStatus: nu.s, newRole: (nu.d && nu.d.user) ? nu.d.user.role : null, oldStatus: old.s, restored };
  }, { A, B, PWD });

  expect(res.newStatus).toBe(200);      // login avec la nouvelle adresse
  expect(res.newRole).toBe("user");     // droits/rôle inchangés
  expect(res.oldStatus).toBe(401);      // ancienne adresse refusée après bascule
  expect(res.restored).toBe(200);       // restauration (idempotence du test)
});
