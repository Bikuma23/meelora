const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — persona UX: the company sidebar is a projection of EFFECTIVE ACCESS
// (data-testid nav-module-<CODE>), never derived from user.role.
const CASES = [
  { email: "persona_reporting@accslegro.com", name: "F Reporting-only", modules: ["REPORTING"] },
  { email: "persona_budgets@accslegro.com", name: "Budgets-only", modules: ["BUDGETS"] },
  { email: "persona_junior@accslegro.com", name: "D Junior (Accounting)", modules: ["ACCOUNTING"] },
  { email: "persona_finance@accslegro.com", name: "E Finance (Accounting)", modules: ["ACCOUNTING"] },
  { email: "persona_consol@accslegro.com", name: "H Consolidation", modules: ["CONSOLIDATION"] },
];

async function visibleModules(page, expectedCount) {
  await page.getByTestId("company-nav").waitFor({ state: "visible" });
  if (expectedCount != null) {
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(expectedCount);
  }
  return page.$$eval('[data-testid^="nav-module-"]', (els) => els.map((e) => e.getAttribute("data-testid").replace("nav-module-", "")));
}

const LANDING = { REPORTING: "Reporting", BUDGETS: "Gestion des Budgets", ACCOUNTING: "Comptabilité", FIXED_ASSETS: "Immobilisations", CONSOLIDATION: "Consolidation" };

test.describe("Persona sidebar = effective access (P1.13E)", () => {
  for (const c of CASES) {
    test(`${c.name} sees exactly ${c.modules.join("+")} and lands on its module`, async ({ page }) => {
      await login(page, { email: c.email, password: "persona123" });
      await expect(page.getByTestId("context-switcher")).toHaveCount(0);
      const mods = await visibleModules(page, c.modules.length);
      expect(mods).toEqual(c.modules);
      // Single-company employee: no "Tous les mandats" menu.
      await expect(page.getByTestId("nav-mandats_list")).toHaveCount(0);
      // Non-budget employee lands directly on its primary module (not empty dashboard).
      if (!c.modules.includes("BUDGETS")) {
        await expect(page.getByTestId("breadcrumb")).toContainText(LANDING[c.modules[0]]);
      }
    });
  }

  test("Client Admin gets the management view (all entitled modules, no financial authority)", async ({ page }) => {
    await login(page, { email: "persona_clientadmin@accslegro.com", password: "persona123" });
    const mods = await visibleModules(page, 5);
    expect(mods).toEqual(["REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"]);
    // Administration section is available to the client admin.
    await expect(page.getByTestId("nav-admin-section")).toBeVisible();
  });

  test("multi-société persona recomputes the sidebar on mandate switch", async ({ page }) => {
    const CA = "965f0770-8cf2-4199-a99f-819ff270436a"; // meelora -> BUDGETS + ACCOUNTING
    const CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"; // 9434 -> ACCOUNTING + CONSOLIDATION
    await login(page, { email: "persona_multi@accslegro.com", password: "persona123" });
    await page.getByTestId("nav-mandats_list").click();
    await expect(page.getByTestId("mandats-list")).toBeVisible();
    // Enter meelora mandate.
    await page.getByTestId(`mandat-access-${CA}`).click();
    await expect(page.getByTestId("active-mandat-name")).toBeVisible();
    await expect(page.locator('[data-testid="nav-module-BUDGETS"]')).toBeVisible();
    await expect(page.locator('[data-testid="nav-module-CONSOLIDATION"]')).toHaveCount(0);
    // Switch to 9434 mandate -> sidebar recomputed, no rights carried over.
    await page.getByTestId("nav-mandats_list").click();
    await page.getByTestId(`mandat-access-${CB}`).click();
    await expect(page.locator('[data-testid="nav-module-CONSOLIDATION"]')).toBeVisible();
    await expect(page.locator('[data-testid="nav-module-BUDGETS"]')).toHaveCount(0);
  });

  test("Reporting-only opens the placeholder module page without errors", async ({ page }) => {
    await login(page, { email: "persona_reporting@accslegro.com", password: "persona123" });
    await page.getByTestId("nav-reporting_home").click();
    await expect(page.getByTestId("module-placeholder-REPORTING")).toBeVisible();
  });

  test("platform_admin: extension keeps platform nav; platform_role adds no financial module", async ({ page }) => {
    await login(page, { email: "platform@meelora.com", password: "platform123" });
    // No business modules appear before accessing Société Meelora.
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
    await expect(page.getByTestId("platform-home")).toBeVisible();
    // Access Société Meelora -> extension appended, platform menus RETAINED.
    await page.getByTestId("nav-platform_meelora").click();
    await page.getByTestId("platform-meelora-access").click();
    await page.waitForTimeout(1000);
    await expect(page.getByTestId("platform-business-ext")).toBeVisible();
    await expect(page.getByTestId("platform-ext-empty")).toBeVisible(); // platform_role => no module
    await expect(page.getByTestId("nav-platform_home")).toBeVisible();
    await expect(page.getByTestId("nav-platform_meelora")).toBeVisible();
  });
});
