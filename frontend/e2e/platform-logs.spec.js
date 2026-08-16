const { test, expect } = require("@playwright/test");
const { login } = require("./helpers");

// P1.13E — Logs plateforme = outil d'audit (recherche + filtres) + isolation
// plateforme/client + aucun secret exposé. Nécessite le seed personas
// (scripts/seed_p1_13e_personas.py) qui insère 4 évènements plateforme d'exemple.
test.describe("Logs plateforme — audit (P1.13E)", () => {
  test("recherche texte libre", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_logs").click();
    await expect(page.getByTestId("platform-logs")).toBeVisible();
    await expect(page.getByTestId("platform-logs-list")).toBeVisible();
    await page.getByTestId("platform-logs-search").fill("ABC");
    await page.waitForTimeout(600);
    const entries = page.getByTestId("platform-log-entry");
    await expect(entries.first()).toBeVisible();
    for (const el of await entries.all()) {
      await expect(el).toContainText(/ABC/i);
    }
  });

  test("filtres (type d'évènement + résultat)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_logs").click();
    await page.getByTestId("platform-logs-filter-event").selectOption("support.action");
    await page.waitForTimeout(600);
    await expect(page.getByTestId("platform-log-entry")).toHaveCount(1);
    await expect(page.getByTestId("platform-log-entry").first()).toHaveAttribute("data-event", "support.action");
    // Filtre résultat = échec.
    await page.getByTestId("platform-logs-reset").click();
    await page.getByTestId("platform-logs-filter-result").selectOption("failure");
    await page.waitForTimeout(600);
    for (const el of await page.getByTestId("platform-log-entry").all()) {
      await expect(el).toHaveAttribute("data-result", "failure");
    }
  });

  test("aucun secret exposé dans les logs (mot de passe / token redacted)", async ({ page }) => {
    await login(page, "platformAdmin");
    await page.getByTestId("nav-platform_logs").click();
    await page.getByTestId("platform-logs-search").fill("SHOULD_NOT_APPEAR");
    await page.waitForTimeout(600);
    await expect(page.getByTestId("platform-logs-empty")).toBeVisible();
    await page.getByTestId("platform-logs-search").fill("tok_secret_xyz");
    await page.waitForTimeout(600);
    await expect(page.getByTestId("platform-logs-empty")).toBeVisible();
    // Le contenu de la page ne doit jamais contenir le secret brut.
    expect(await page.content()).not.toContain("SHOULD_NOT_APPEAR");
  });

  test("isolation : /platform/logs ne renvoie que des évènements de scope plateforme", async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await login(page, "platformAdmin");
    const data = await page.evaluate(async () => {
      const r = await fetch("/api/platform/logs?limit=1000", { credentials: "include" });
      return r.ok ? await r.json() : [];
    });
    const platformPrefixes = ["platform.", "client.", "client_admin.", "support."];
    for (const e of data) {
      expect(e.scope).toBe("platform");
      expect(platformPrefixes.some((p) => (e.event_type || "").startsWith(p))).toBeTruthy();
    }
    await ctx.close();
  });
});
