from pathlib import Path

from core.auth_context import build_auth_user

ROOT = Path(__file__).resolve().parents[2]
SERVER = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")


def test_legacy_editor_is_normalized_to_user_in_auth_context():
    user = build_auth_user({"_id": "u1", "email": "x@example.com", "role": "editor"}, None)
    assert user["role"] == "user"


def test_standard_user_writes_are_not_blocked_by_legacy_write_guard():
    # Admin-only routes still have their own guard. For all other existing
    # operational routes, P1.10 must preserve the former editor write ability
    # for the new unified `user` role.
    assert '_normalized_role(role) not in ("admin", "user")' in SERVER


def test_foundation_api_contract_is_present():
    required = [
        '@api.get("/auth/me")',
        '@api.get("/companies")',
        '@api.post("/companies", status_code=201)',
        '@api.get("/companies/{company_id}")',
        '@api.patch("/companies/{company_id}")',
        '@api.post("/companies/import/preview")',
        '@api.post("/companies/import/commit")',
        '@api.get("/mandates")',
        '@api.post("/mandates", status_code=201)',
        '@api.get("/logs")',
        '@api.get("/users")',
        '@api.get("/users/{uid}/company-access")',
        '@api.put("/users/{uid}/company-access")',
    ]
    missing = [item for item in required if item not in SERVER]
    assert not missing, f"Foundation routes missing: {missing}"


def test_legacy_financial_route_surface_remains_present():
    required = [
        '@api.get("/acct/summary")',
        '@api.post("/acct/bv")',
        '@api.post("/acct/ledger")',
        '@api.get("/acct/report")',
        '@api.get("/acct/report/pnl-monthly")',
        '@api.get("/qc9434/years")',
        '@api.get("/qc9434/entries")',
        '@api.post("/qc9434/entries")',
        '@api.get("/qc9434/invoices")',
        '@api.get("/qc9434/bills")',
    ]
    missing = [item for item in required if item not in SERVER]
    assert not missing, f"Legacy financial endpoints removed: {missing}"


def test_legacy_financial_collections_are_not_removed_in_phase1():
    required = [
        "db.acct_bv",
        "db.acct_ledger",
        "db.acct_template",
        "db.acct_account_map",
        "db.qc9434_entries",
        "db.qc9434_accounts",
        "db.qc9434_invoices",
        "db.qc9434_bills",
    ]
    missing = [item for item in required if item not in SERVER]
    assert not missing, f"Legacy financial collections unexpectedly removed: {missing}"


def test_phase1_migrations_do_not_destructively_touch_financial_collections():
    scripts = list((ROOT / "backend" / "scripts").glob("migrate_phase1_*.py"))
    assert scripts
    destructive_tokens = ("drop(", ".drop()", "drop_collection", "delete_many(", "rename_collection")
    legacy_tokens = ("acct_", "qc9434_")
    offenders = []
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        if any(x in text for x in destructive_tokens) and any(x in text for x in legacy_tokens):
            offenders.append(script.name)
    assert not offenders, f"Destructive legacy financial migration detected: {offenders}"


def test_frontend_new_user_role_preserves_operational_editing():
    checks = {
        "frontend/src/pages/Employes.js": '["admin", "user", "editor"].includes(user?.role)',
        "frontend/src/pages/Departements.js": '["admin", "user", "editor"].includes(user?.role)',
        "frontend/src/pages/QcEntity.js": '["admin", "user", "editor"].includes(user?.role)',
        "frontend/src/pages/Comptabilite.js": '["admin", "user", "editor"].includes(user.role)',
        "frontend/src/pages/SalairesBudget.js": '["user", "editor"].includes(user?.role)',
    }
    missing = []
    for rel, token in checks.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        if token not in text:
            missing.append(rel)
    assert not missing, f"Unified user role lost legacy edit capability in: {missing}"


def test_logs_navigation_is_admin_only():
    layout = (ROOT / "frontend" / "src" / "components" / "Layout.js").read_text(encoding="utf-8")
    assert 'user?.role === "admin"' in layout
    assert 'key: "logs"' in layout
