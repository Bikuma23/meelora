const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Sign-off complémentaire : navigation hiérarchique obligatoire.
// Mappe 1:1 les critères d'acceptation du client :
//   Meelora -> Sociétés / Clients -> Meelora -> Accéder  => contexte Société Meelora
//   Client  -> Tous les mandats  -> Société A -> Accéder => modules de A
//   retour  -> Tous les mandats  -> Société B -> Accéder => modules de B
//   PREUVE : les accès de A ne persistent pas dans B.
const CA = "965f0770-8cf2-4199-a99f-819ff270436a"; // Meelora  -> BUDGETS + ACCOUNTING
const CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"; // 9434     -> ACCOUNTING + CONSOLIDATION

test.describe("Navigation hiérarchique (sign-off P1.13E)", () => {
  test("Meelora → Sociétés / Clients → Meelora → Accéder → EXTENSION (menus plateforme conservés)", async ({ page }) => {
    await login(page, "platformAdmin");
    // Sidebar plateforme = 4 entrées.
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_clients")).toBeVisible();
    await expect(page.getByTestId("nav-platform_meelora")).toBeVisible();
    await expect(page.getByTestId("nav-platform_logs")).toBeVisible();
    // Page Sociétés / Clients : carte Meelora (fond vert) + Accéder.
    await page.getByTestId("nav-platform_clients").click();
    await expect(page.getByTestId("platform-internal-card")).toBeVisible();
    await page.getByTestId("platform-internal-access").click();
    await page.waitForTimeout(1000);
    // EXTENSION : les menus plateforme restent + section « Société Meelora » ajoutée.
    await expect(page.getByTestId("platform-business-ext")).toBeVisible();
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_meelora")).toBeVisible();
  });

  test("Client → Tous les mandats → A → Accéder → modules A ; puis B → modules B (isolation A↛B)", async ({ page }) => {
    await login(page, { email: "persona_multi@accslegro.com", password: "persona123" });
    // Le libellé reste « Tous les mandats ».
    await expect(page.getByTestId("nav-mandats_list")).toBeVisible();
    await page.getByTestId("nav-mandats_list").click();
    await expect(page.getByTestId("mandats-list")).toBeVisible();
    // Chaque mandat autorisé a un bouton Accéder.
    await expect(page.getByTestId(`mandat-access-${CA}`)).toBeVisible();
    await expect(page.getByTestId(`mandat-access-${CB}`)).toBeVisible();

    // Accéder à A -> définit le contexte + recharge les droits effectifs -> modules de A.
    await page.getByTestId(`mandat-access-${CA}`).click();
    await expect(page.getByTestId("active-mandat-name")).toContainText("meelora", { ignoreCase: true });
    await expect(page.locator('[data-testid="nav-module-BUDGETS"]')).toBeVisible();
    await expect(page.locator('[data-testid="nav-module-ACCOUNTING"]')).toBeVisible();
    // A n'a PAS Consolidation.
    await expect(page.locator('[data-testid="nav-module-CONSOLIDATION"]')).toHaveCount(0);

    // Retour Tous les mandats -> Accéder à B -> sidebar recomposée sur l'accès effectif de B.
    await page.getByTestId("nav-mandats_list").click();
    await page.getByTestId(`mandat-access-${CB}`).click();
    await expect(page.locator('[data-testid="nav-module-CONSOLIDATION"]')).toBeVisible();
    await expect(page.locator('[data-testid="nav-module-ACCOUNTING"]')).toBeVisible();
    // PREUVE d'isolation : BUDGETS (accès propre à A) ne persiste PAS dans B.
    await expect(page.locator('[data-testid="nav-module-BUDGETS"]')).toHaveCount(0);
  });

  test("Isolation renforcée : les droits de A ne fuient pas côté API en contexte B", async ({ page }) => {
    await login(page, { email: "persona_multi@accslegro.com", password: "persona123" });
    // persona_multi : A(meelora)=BUDGETS+ACCOUNTING(read) ; B(9434)=ACCOUNTING(manage)+CONSOLIDATION.
    // Le gating par module est appliqué côté serveur (middleware), indépendamment de l'UI :
    // une route BUDGETS legacy (masse salariale) est portée UNIQUEMENT par la société Meelora (A).
    // Aucune route BUDGETS n'est rattachée à 9434 -> l'isolation par société est structurelle.
    const nav = await page.evaluate(async () => {
      const call = async (cid) => {
        const r = await fetch(`/api/companies/${cid}/navigation`, { credentials: "include" });
        return { status: r.status, body: r.ok ? await r.json() : null };
      };
      return { a: await call("965f0770-8cf2-4199-a99f-819ff270436a"), b: await call("58a59a28-4701-4ba5-8e2f-61ff76e0f2e9") };
    });
    const codes = (res) => (res.body?.modules || []).map((m) => m.module_code).sort();
    expect(nav.a.status).toBe(200);
    expect(nav.b.status).toBe(200);
    // A expose BUDGETS ; B ne l'expose PAS (aucune fuite inter-mandats).
    expect(codes(nav.a)).toContain("BUDGETS");
    expect(codes(nav.b)).not.toContain("BUDGETS");
    expect(codes(nav.b)).toContain("CONSOLIDATION");
    expect(codes(nav.a)).not.toContain("CONSOLIDATION");
  });
});
