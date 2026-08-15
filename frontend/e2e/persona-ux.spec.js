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

test.describe("Persona sidebar = effective access (P1.13E)", () => {
  for (const c of CASES) {
    test(`${c.name} sees exactly ${c.modules.join("+")}`, async ({ page }) => {
      await login(page, { email: c.email, password: "persona123" });
      await expect(page.getByTestId("context-switcher")).toHaveCount(0);
      const mods = await visibleModules(page, c.modules.length);
      expect(mods).toEqual(c.modules);
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
    await login(page, { email: "persona_multi@accslegro.com", password: "persona123" });
    // Enter the first mandate from "Tous les mandats".
    await page.getByTestId("nav-mandats_list").click();
    await expect(page.getByTestId("mandats-list")).toBeVisible();
    const cards = page.locator('[data-testid^="mandat-access-"]');
    await expect(cards).toHaveCount(2);
    await cards.nth(0).click();
    await page.waitForTimeout(1200);
    const first = await visibleModules(page);
    // Back to the list and enter the second mandate.
    await page.getByTestId("nav-mandats_list").click();
    await page.locator('[data-testid^="mandat-access-"]').nth(1).click();
    await page.waitForTimeout(1200);
    const second = await visibleModules(page);
    expect(second).not.toEqual(first);
    for (const m of [...first, ...second]) expect(["REPORTING", "BUDGETS", "ACCOUNTING", "CONSOLIDATION"]).toContain(m);
  });

  test("Reporting-only opens the placeholder module page without errors", async ({ page }) => {
    await login(page, { email: "persona_reporting@accslegro.com", password: "persona123" });
    await page.getByTestId("nav-reporting_home").click();
    await expect(page.getByTestId("module-placeholder-REPORTING")).toBeVisible();
  });

  test("platform_admin: company context shows the company sidebar, platform nav shows none of the 5 modules", async ({ page }) => {
    await login(page, { email: "platform@meelora.com", password: "platform123" });
    // Platform context: none of the business modules appear.
    await expect(page.locator('[data-testid^="nav-module-"]')).toHaveCount(0);
    await expect(page.getByTestId("platform-home")).toBeVisible();
    // Switch to Société Meelora -> company sidebar renders (platform_role grants
    // no business modules, so the business list may be empty by design).
    await page.getByTestId("context-company").click();
    await expect(page.getByTestId("company-nav")).toBeVisible();
    await expect(page.getByTestId("nav-platform_home")).toHaveCount(0);
  });
});
