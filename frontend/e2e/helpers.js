// Shared E2E helpers & test credentials (see /app/memory/test_credentials.md).
const CREDS = {
  admin: { email: "admin@accslegro.com", password: "admin123" },
  platformAdmin: { email: "platform@meelora.com", password: "platform123" },
  support: { email: "support@meelora.com", password: "support123" },
  julie: { email: "julie@accslegro.com", password: "julie123" }, // simple user
  marc: { email: "marc@accslegro.com", password: "marc123" },     // multi-company user
};

async function login(page, who) {
  const c = typeof who === "string" ? CREDS[who] : who;
  await page.goto("/");
  // Reset any stored context/page so defaults are deterministic.
  await page.evaluate(() => {
    try { localStorage.removeItem("meelora:ctx"); localStorage.removeItem("acct:lastPage"); } catch (e) {}
  });
  await page.goto("/");
  await page.getByTestId("login-email").fill(c.email);
  await page.getByTestId("login-password").fill(c.password);
  await page.getByTestId("login-submit").click();
  // Wait for the app shell (sidebar brand logo) to appear.
  await page.getByTestId("brand-logo").first().waitFor({ state: "visible" });
}

module.exports = { CREDS, login };
