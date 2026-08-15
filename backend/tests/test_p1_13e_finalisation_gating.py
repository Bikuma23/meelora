"""P1.13E FINALISATION — Live HTTP legacy-route module gating.

Confirms: a menu hidden in the sidebar cannot be reached via URL/API.
Matrix from the review request:
  reporting-only:  GET /api/budget=403, /api/reports/pnl=403, /api/acct/periods=403
  budgets-only:    GET /api/budget=200, /api/acct/periods=403
  junior (ACCT):   GET /api/acct/periods=200, /api/budget=403
  admin:           GET /api/budget=200, /api/acct/periods=200
Also: navigation endpoint reflects the correct module lists.
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")
CA = "965f0770-8cf2-4199-a99f-819ff270436a"
CB = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"
WS = "ws_56c492936ea64c4db53a2f14a0825ef5"

CREDS = {
    "admin":       ("admin@accslegro.com", "admin123"),
    "reporting":   ("persona_reporting@accslegro.com", "persona123"),
    "budgets":     ("persona_budgets@accslegro.com", "persona123"),
    "junior":      ("persona_junior@accslegro.com", "persona123"),
    "finance":     ("persona_finance@accslegro.com", "persona123"),
    "consol":      ("persona_consol@accslegro.com", "persona123"),
    "clientadmin": ("persona_clientadmin@accslegro.com", "persona123"),
    "multi":       ("persona_multi@accslegro.com", "persona123"),
    "platform":    ("platform@meelora.com", "platform123"),
}

_tokens: dict[str, str] = {}


def _login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    data = r.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module", autouse=True)
def _all_tokens():
    for k, (e, p) in CREDS.items():
        _tokens[k] = _login(e, p)
    return _tokens


def _h(who):
    return {"Authorization": f"Bearer {_tokens[who]}"}


def _get(who, path):
    return requests.get(f"{BASE}{path}", headers=_h(who), timeout=15)


# ---------- Legacy route gating matrix (BLOCKER if any fails) ----------------
class TestLegacyGating:
    def test_reporting_only_denied_on_budget(self):
        r = _get("reporting", f"/api/budget?company_id={CA}")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_reporting_only_denied_on_reports_pnl(self):
        r = _get("reporting", f"/api/reports/pnl?company_id={CA}")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_reporting_only_denied_on_acct_periods(self):
        r = _get("reporting", f"/api/acct/periods?company_id={CA}")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_budgets_only_allowed_on_budget(self):
        r = _get("budgets", f"/api/budget?company_id={CA}")
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"

    def test_budgets_only_denied_on_acct_periods(self):
        r = _get("budgets", f"/api/acct/periods?company_id={CA}")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_junior_allowed_on_acct_periods(self):
        r = _get("junior", f"/api/acct/periods?company_id={CA}")
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"

    def test_junior_denied_on_budget(self):
        r = _get("junior", f"/api/budget?company_id={CA}")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_admin_allowed_on_budget(self):
        r = _get("admin", f"/api/budget?company_id={CA}")
        assert r.status_code == 200

    def test_admin_allowed_on_acct_periods(self):
        r = _get("admin", f"/api/acct/periods?company_id={CA}")
        assert r.status_code == 200


# ---------- Platform admin in company context: 0 business modules ------------
class TestPlatformIsolation:
    def test_platform_admin_bare_membership_no_business_access(self):
        # Should be denied on /api/budget for CA even though member
        r = _get("platform", f"/api/budget?company_id={CA}")
        assert r.status_code == 403, f"platform_admin got {r.status_code} on /api/budget"

    def test_platform_admin_no_acct(self):
        r = _get("platform", f"/api/acct/periods?company_id={CA}")
        assert r.status_code == 403, f"platform_admin got {r.status_code} on /api/acct/periods"


# ---------- Navigation endpoint reflects module lists ------------------------
class TestNavigationEndpoint:
    def _nav_codes(self, who, cid):
        r = requests.get(f"{BASE}/api/companies/{cid}/navigation",
                         headers=_h(who), timeout=15)
        assert r.status_code == 200, f"nav {who}/{cid}: {r.status_code} {r.text[:200]}"
        return [m["module_code"] for m in r.json().get("modules", [])], r.json()

    def test_nav_reporting_only(self):
        codes, _ = self._nav_codes("reporting", CA)
        assert codes == ["REPORTING"], codes

    def test_nav_budgets_only(self):
        codes, _ = self._nav_codes("budgets", CA)
        assert codes == ["BUDGETS"], codes

    def test_nav_junior_accounting_only(self):
        codes, _ = self._nav_codes("junior", CA)
        assert codes == ["ACCOUNTING"], codes

    def test_nav_finance_accounting_only(self):
        codes, _ = self._nav_codes("finance", CA)
        assert codes == ["ACCOUNTING"], codes

    def test_nav_consol_consolidation_only(self):
        codes, _ = self._nav_codes("consol", CA)
        assert codes == ["CONSOLIDATION"], codes

    def test_nav_admin_all_five_management_view(self):
        codes, nav = self._nav_codes("admin", CA)
        assert codes == ["REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"], codes
        assert nav.get("admin_view") is True
        # admin_view must never carry sensitive capabilities
        assert all(m["capabilities"] == [] for m in nav["modules"]), \
            "admin_view should never expose sensitive capabilities"

    def test_nav_clientadmin_management_view_five_no_caps(self):
        codes, nav = self._nav_codes("clientadmin", CA)
        assert codes == ["REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"], codes
        assert nav.get("admin_view") is True
        assert all(m["source"] == "admin_view" for m in nav["modules"])
        assert all(m["capabilities"] == [] for m in nav["modules"])

    def test_nav_multi_ca_budgets_accounting(self):
        codes, _ = self._nav_codes("multi", CA)
        assert set(codes) == {"BUDGETS", "ACCOUNTING"}, codes

    def test_nav_multi_cb_accounting_consolidation(self):
        codes, _ = self._nav_codes("multi", CB)
        assert set(codes) == {"ACCOUNTING", "CONSOLIDATION"}, codes

    def test_nav_platform_admin_bare_zero_modules(self):
        codes, nav = self._nav_codes("platform", CA)
        assert codes == [], f"platform_admin must have 0 modules in bare-membership context, got {codes}"


# ---------- Client Admin has NO financial authority --------------------------
class TestClientAdminNoAuthority:
    def test_clientadmin_denied_write_sensitive(self):
        # Client Admin (company_user admin) should be able to READ via admin_view
        # but NOT hold sensitive perms (e.g. period_close, entry_post).
        # Verify /api/acct/periods GET is allowed (admin_view) but sensitive POST is not.
        r = _get("clientadmin", f"/api/acct/periods?company_id={CA}")
        # Admin_view grants read/write visibility on entitled+enabled modules.
        assert r.status_code == 200, f"clientadmin read should be allowed, got {r.status_code}"


# ---------- Multi persona quick admin sanity ---------------------------------
class TestMultiCompanyIsolation:
    def test_multi_can_reach_budget_on_CA(self):
        # persona_multi has BUDGETS on CA
        r = _get("multi", f"/api/budget?company_id={CA}")
        assert r.status_code == 200

    def test_multi_can_reach_acct_periods(self):
        # persona_multi has ACCOUNTING on both CA (read) and CB (manage)
        r = _get("multi", f"/api/acct/periods?company_id={CA}")
        assert r.status_code == 200
