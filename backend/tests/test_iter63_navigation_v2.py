"""Iteration 63 — V2 navigation vocabulary + Client -> Mandat -> Modules gating.
Live HTTP against public REACT_APP_BACKEND_URL. No xdist. Fail-closed sec checks.
"""
import os, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://budgetapp-qc.preview.emergentagent.com").rstrip("/")

CREDS = {
    "platform": ("platform@meelora.com", "platform123"),
    "clientadmin": ("persona_clientadmin@accslegro.com", "persona123"),
    "multi": ("persona_multi@accslegro.com", "persona123"),
    "reporting": ("persona_reporting@accslegro.com", "persona123"),
    "budgets": ("persona_budgets@accslegro.com", "persona123"),
    "admin": ("admin@accslegro.com", "admin123"),
}

_tokens = {}

def token(role):
    if role in _tokens: return _tokens[role]
    email, pwd = CREDS[role]
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {role}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    _tokens[role] = tok
    return tok

def H(role):
    return {"Authorization": f"Bearer {token(role)}"}

def context(role):
    r = requests.get(f"{BASE}/api/me/company-context", headers=H(role), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()

# -------- company-context / mandate visibility --------

def test_multi_sees_two_mandates():
    ctx = context("multi")
    cs = ctx.get("companies", [])
    assert len(cs) >= 2, ctx
    prefixes = {c.get("legacy_prefix") for c in cs}
    assert {"acct", "qc9434"}.issubset(prefixes)

def test_reporting_mono_mandate():
    ctx = context("reporting")
    cs = ctx.get("companies", [])
    assert len(cs) == 1, ctx

def test_clientadmin_visible():
    ctx = context("clientadmin")
    assert len(ctx.get("companies", [])) >= 1

# -------- navigation per company --------

def nav(role, cid):
    r = requests.get(f"{BASE}/api/companies/{cid}/navigation", headers=H(role), timeout=15)
    return r

def _cid(role, prefix):
    for c in context(role)["companies"]:
        if c.get("legacy_prefix") == prefix:
            return c["id"]
    pytest.fail(f"prefix {prefix} not visible for {role}")

def test_multi_navigation_CA_vs_CB_distinct():
    ca = _cid("multi", "acct"); cb = _cid("multi", "qc9434")
    a = nav("multi", ca); b = nav("multi", cb)
    assert a.status_code == 200 and b.status_code == 200
    ma = {m["module_code"] for m in a.json().get("modules", [])}
    mb = {m["module_code"] for m in b.json().get("modules", [])}
    assert ma == {"BUDGETS", "ACCOUNTING"}, ma
    assert mb == {"ACCOUNTING", "CONSOLIDATION"}, mb

def test_reporting_only_module():
    cid = _cid("reporting", "acct")
    j = nav("reporting", cid).json()
    assert {m["module_code"] for m in j.get("modules", [])} == {"REPORTING"}

def test_clientadmin_sees_all_five_admin_view():
    cid = _cid("clientadmin", "acct")
    j = nav("clientadmin", cid).json()
    codes = {m["module_code"] for m in j.get("modules", [])}
    assert codes == {"REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"}, codes
    assert j.get("admin_view") is True
    # no sensitive capabilities under admin_view
    for m in j["modules"]:
        assert not m.get("capabilities"), m

# -------- security: hidden module 403 via legacy API --------

def test_reporting_only_denied_budget_and_acct():
    r1 = requests.get(f"{BASE}/api/budget", headers=H("reporting"), timeout=15)
    r2 = requests.get(f"{BASE}/api/acct/periods", headers=H("reporting"), timeout=15)
    assert r1.status_code == 403, r1.status_code
    assert r2.status_code == 403, r2.status_code

def test_budgets_only_allowed_budget_denied_acct():
    r1 = requests.get(f"{BASE}/api/budget", headers=H("budgets"), timeout=15)
    r2 = requests.get(f"{BASE}/api/acct/periods", headers=H("budgets"), timeout=15)
    assert r1.status_code == 200, (r1.status_code, r1.text[:120])
    assert r2.status_code == 403, r2.status_code

# -------- no cross-workspace enumeration --------

def test_bogus_company_returns_404():
    r = requests.get(f"{BASE}/api/companies/00000000-0000-0000-0000-000000000000/navigation", headers=H("reporting"), timeout=15)
    assert r.status_code == 404, r.status_code

def test_no_access_company_returns_403_or_404():
    # reporting has only CA -> ask navigation for CB
    cb = _cid("multi", "qc9434")
    r = nav("reporting", cb)
    assert r.status_code in (403, 404), (r.status_code, r.text[:120])

# -------- admin regression --------

def test_admin_sees_all_companies_and_all_modules():
    ctx = context("admin")
    assert len(ctx["companies"]) >= 2
    cid = _cid("admin", "acct")
    j = nav("admin", cid).json()
    codes = {m["module_code"] for m in j.get("modules", [])}
    assert codes == {"REPORTING", "BUDGETS", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"}

def test_admin_budget_and_acct_accessible():
    assert requests.get(f"{BASE}/api/budget", headers=H("admin"), timeout=15).status_code == 200
    assert requests.get(f"{BASE}/api/acct/periods", headers=H("admin"), timeout=15).status_code == 200

# -------- platform bare membership --------

def test_platform_bare_member_no_modules_and_denied_finance():
    ctx = context("platform")
    if not ctx.get("companies"):
        pytest.skip("platform has no company membership in this env")
    cid = ctx["companies"][0]["id"]
    j = nav("platform", cid).json()
    assert j.get("modules", []) == [], j
    assert requests.get(f"{BASE}/api/budget", headers=H("platform"), timeout=15).status_code == 403
    assert requests.get(f"{BASE}/api/acct/periods", headers=H("platform"), timeout=15).status_code == 403
