"""
One-off E2E test for P1.11 (legacy financial access hardening) + P1.9 (Excel import commit).
NOT stored in /app/backend/tests to avoid polluting pytest runs.
Handles full cleanup: temp user, test company, mandate, company_access rows.
"""
import os, io, sys, uuid, json, time, random, string
import requests

BASE = "https://budgetapp-qc.preview.emergentagent.com"
API = BASE + "/api"

RESULTS = {"passed": [], "failed": [], "info": []}

def _log(bucket, msg):
    RESULTS[bucket].append(msg)
    print(f"[{bucket.upper()}] {msg}")

def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {tok}"}, r.json()

def check(name, cond, detail=""):
    if cond:
        _log("passed", f"{name}")
    else:
        _log("failed", f"{name} :: {detail}")

def main():
    # ---- Login all 3 base users ----
    admin_h, admin_u = login("admin@accslegro.com", "admin123")
    julie_h, julie_u = login("julie@accslegro.com", "julie123")
    marc_h,  marc_u  = login("marc@accslegro.com",  "marc123")
    _log("info", f"Admin id={admin_u.get('user',{}).get('id') or admin_u.get('id')}")
    julie_id = julie_u.get('user',{}).get('id') or julie_u.get('id')
    _log("info", f"Julie id={julie_id}")

    # ================================================================
    # P1.11 READ enforcement
    # ================================================================
    def gcode(h, path):
        r = requests.get(f"{API}{path}", headers=h, timeout=30)
        return r.status_code, r

    # Admin GET
    for p in ["/acct/dashboard", "/qc9434/accounts"]:
        sc, _ = gcode(admin_h, p)
        check(f"Admin GET {p} -> 200", sc == 200, f"got {sc}")

    # Julie GET
    for p, expected in [("/acct/dashboard", 200), ("/acct/accounts", 200),
                        ("/qc9434/accounts", 403), ("/qc9434/years", 403)]:
        sc, r = gcode(julie_h, p)
        check(f"Julie GET {p} -> {expected}", sc == expected, f"got {sc} body={r.text[:150]}")

    # Marc GET all four -> 200
    for p in ["/acct/dashboard", "/acct/accounts", "/qc9434/accounts", "/qc9434/years"]:
        sc, r = gcode(marc_h, p)
        check(f"Marc GET {p} -> 200", sc == 200, f"got {sc} body={r.text[:150]}")

    # ================================================================
    # P1.11 WRITE enforcement
    # ================================================================
    # Julie POST /api/qc9434/accounts -> 403 (no access)
    r = requests.post(f"{API}/qc9434/accounts", headers=julie_h, json={"code":"9999","name":"TEST"}, timeout=20)
    check("Julie POST /qc9434/accounts -> 403", r.status_code == 403, f"got {r.status_code} body={r.text[:200]}")

    # Marc POST /api/qc9434/accounts -> not company-access 403 (may be 4xx validation OK)
    r = requests.post(f"{API}/qc9434/accounts", headers=marc_h, json={"code":"TESTP111","name":"TEST P111"}, timeout=20)
    # Should NOT be an access 403. Accept 200/201/400/422/409 etc. If 403, check reason.
    is_access_403 = (r.status_code == 403 and ("access" in r.text.lower() or "acc" in r.text.lower()))
    check("Marc POST /qc9434/accounts NOT access-403", not is_access_403,
          f"got {r.status_code} body={r.text[:200]}")
    _log("info", f"Marc POST /qc9434/accounts status={r.status_code}")
    # If accidentally created, try to delete (best-effort)
    if r.status_code in (200, 201):
        try:
            created = r.json()
            code = created.get("code") or "TESTP111"
            requests.delete(f"{API}/qc9434/accounts/{code}", headers=marc_h, timeout=10)
            requests.delete(f"{API}/qc9434/accounts/{code}", headers=admin_h, timeout=10)
        except Exception:
            pass

    # Marc POST /api/acct/accounts -> also not access-403 (has collaborator on acct)
    r = requests.post(f"{API}/acct/accounts", headers=marc_h, json={"code":"TESTP111A","name":"TP111A"}, timeout=20)
    is_access_403 = (r.status_code == 403)
    check("Marc POST /acct/accounts NOT access-403", not is_access_403,
          f"got {r.status_code} body={r.text[:200]}")
    _log("info", f"Marc POST /acct/accounts status={r.status_code}")
    if r.status_code in (200, 201):
        try:
            code = r.json().get("code") or "TESTP111A"
            requests.delete(f"{API}/acct/accounts/{code}", headers=admin_h, timeout=10)
        except Exception: pass

    # Admin write on both -> not blocked by access (bypass)
    for prefix in ["acct", "qc9434"]:
        r = requests.post(f"{API}/{prefix}/accounts", headers=admin_h,
                          json={"code":f"TP111X{prefix[:2].upper()}","name":"TP111 admin"}, timeout=20)
        check(f"Admin POST /{prefix}/accounts NOT access-403", r.status_code != 403,
              f"got {r.status_code} body={r.text[:200]}")
        _log("info", f"Admin POST /{prefix}/accounts status={r.status_code}")
        if r.status_code in (200,201):
            try:
                code = r.json().get("code") or f"TP111X{prefix[:2].upper()}"
                requests.delete(f"{API}/{prefix}/accounts/{code}", headers=admin_h, timeout=10)
            except Exception: pass

    # ================================================================
    # P1.11 unassigned temp user
    # ================================================================
    temp_email = "temp-p111@accslegro.com"
    temp_pw = "temp123"
    temp_id = None
    # Create temp user via admin API. Try common shapes.
    payload = {"email": temp_email, "password": temp_pw, "name": "Temp P111", "role": "user"}
    r = requests.post(f"{API}/users", headers=admin_h, json=payload, timeout=20)
    if r.status_code in (200, 201):
        temp_id = r.json().get("id") or r.json().get("user",{}).get("id")
        _log("info", f"Created temp user id={temp_id}")
    else:
        _log("info", f"POST /users failed {r.status_code} {r.text[:200]}; trying /admin/users")
        r = requests.post(f"{API}/admin/users", headers=admin_h, json=payload, timeout=20)
        if r.status_code in (200,201):
            temp_id = r.json().get("id") or r.json().get("user",{}).get("id")
            _log("info", f"Created temp user via /admin/users id={temp_id}")
        else:
            _log("failed", f"Cannot create temp user: {r.status_code} {r.text[:300]}")

    if temp_id:
        try:
            temp_h, _ = login(temp_email, temp_pw)
            for p in ["/acct/dashboard", "/acct/accounts", "/qc9434/accounts", "/qc9434/years"]:
                sc, rr = gcode(temp_h, p)
                check(f"Unassigned user GET {p} -> 403", sc == 403, f"got {sc} body={rr.text[:150]}")
        except AssertionError as e:
            _log("failed", f"temp user login failed: {e}")

    # ================================================================
    # Financial smoke (admin) — unchanged
    # ================================================================
    smoke = [
        "/acct/dashboard",
        "/acct/kpis?year=2026&month=7",
        "/acct/report/pnl-monthly?year=2026",
        "/acct/cashflow?open_year=2026&open_month=1&close_year=2026&close_month=7",
        "/qc9434/trial-balance?year=2026",
        "/qc9434/bilan?year=2026",
        "/qc9434/pnl?year=2026",
        "/qc9434/entries?year=2026",
        "/qc9434/invoices?year=2026",
    ]
    for p in smoke:
        r = requests.get(f"{API}{p}", headers=admin_h, timeout=60)
        ok = r.status_code == 200
        body_ok = False
        if ok:
            try:
                j = r.json()
                # Non-empty check
                if isinstance(j, list):
                    body_ok = True  # list may be empty for some endpoints; consider as OK if 200
                elif isinstance(j, dict):
                    body_ok = len(j.keys()) > 0
                else:
                    body_ok = True
            except Exception:
                body_ok = len(r.content) > 0
        check(f"Smoke admin GET {p} -> 200 & non-empty", ok and body_ok,
              f"status={r.status_code} len={len(r.content)} body={r.text[:200]}")

    # ================================================================
    # P1.9 E2E Excel Import COMMIT
    # ================================================================
    import openpyxl
    suffix = ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
    company_code = f"P111E2E-{suffix}"
    mandate_code = f"MDT-P111E2E-{suffix}"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nom","Code société","Juridiction","Devise","Type société","Code mandat","Responsable principal","Collaborateurs"])
    ws.append(["P111 E2E Test SA", company_code, "CA", "CAD", "operating", mandate_code, "julie@accslegro.com", "marc@accslegro.com"])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    files = {"file": ("p111_import.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    # Preview
    r = requests.post(f"{API}/companies/import/preview", headers=admin_h, files=files, timeout=60)
    _log("info", f"Preview status={r.status_code}")
    preview_ok = False
    if r.status_code == 200:
        pj = r.json()
        _log("info", f"Preview body keys={list(pj.keys()) if isinstance(pj,dict) else type(pj)}")
        valid = pj.get("valid") or pj.get("valid_count") or pj.get("stats",{}).get("valid")
        errors = pj.get("errors") or pj.get("error_count") or pj.get("stats",{}).get("errors")
        # errors can be a list — check length
        if isinstance(errors, list): errcount = len(errors)
        else: errcount = errors
        preview_ok = (valid == 1 and (errcount in (0, None)))
        check("Preview valid=1 errors=0", preview_ok, f"valid={valid} errors={errcount} full={json.dumps(pj)[:400]}")
    else:
        check("Preview HTTP 200", False, f"{r.status_code} {r.text[:300]}")

    # Commit
    created_company_id = None
    created_mandate_id = None
    if preview_ok:
        buf.seek(0)
        files = {"file": ("p111_import.xlsx", buf.getvalue(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{API}/companies/import/commit", headers=admin_h, files=files, timeout=60)
        _log("info", f"Commit status={r.status_code} body={r.text[:400]}")
        if r.status_code == 200:
            cj = r.json()
            created = cj.get("created") or cj.get("created_count") or cj.get("stats",{}).get("created")
            check("Commit created=1", created == 1, f"created={created} full={json.dumps(cj)[:400]}")
            # Find company/mandate ids
            comps = cj.get("companies") or cj.get("created_companies") or []
            mands = cj.get("mandates") or cj.get("created_mandates") or []
            if comps: created_company_id = comps[0].get("id") if isinstance(comps[0], dict) else comps[0]
            if mands: created_mandate_id = mands[0].get("id") if isinstance(mands[0], dict) else mands[0]
        else:
            check("Commit HTTP 200", False, f"{r.status_code} {r.text[:300]}")

    # If we didn't get ids from commit, look them up
    if not created_company_id:
        rc = requests.get(f"{API}/companies", headers=admin_h, timeout=20)
        if rc.status_code == 200:
            for c in rc.json() if isinstance(rc.json(), list) else rc.json().get("companies",[]):
                if c.get("company_code") == company_code or c.get("code") == company_code or c.get("name") == "P111 E2E Test SA":
                    created_company_id = c.get("id"); break
    if not created_mandate_id:
        rm = requests.get(f"{API}/mandates", headers=admin_h, timeout=20)
        if rm.status_code == 200:
            for m in rm.json() if isinstance(rm.json(), list) else rm.json().get("mandates",[]):
                if m.get("mandate_code") == mandate_code or m.get("code") == mandate_code:
                    created_mandate_id = m.get("id"); break

    _log("info", f"Created company_id={created_company_id} mandate_id={created_mandate_id}")

    # Verify c1: companies includes new
    rc = requests.get(f"{API}/companies", headers=admin_h, timeout=20)
    comps = rc.json() if isinstance(rc.json(), list) else rc.json().get("companies",[])
    check("C1 GET /companies includes new company", any(c.get("id")==created_company_id for c in comps),
          f"comps ids={[c.get('id') for c in comps]}")

    # Verify c2: mandates includes new
    rm = requests.get(f"{API}/mandates", headers=admin_h, timeout=20)
    mands = rm.json() if isinstance(rm.json(), list) else rm.json().get("mandates",[])
    m_found = next((m for m in mands if m.get("id")==created_mandate_id), None)
    check("C2 GET /mandates includes new mandate active", m_found is not None and (m_found.get("status")=="active"),
          f"mandate={m_found}")

    # Verify c3: julie company_access
    ra = requests.get(f"{API}/users/{julie_id}/company-access", headers=admin_h, timeout=20)
    if ra.status_code == 200:
        acc = ra.json() if isinstance(ra.json(), list) else ra.json().get("access",[])
        has_julie_principal = any(a.get("company_id")==created_company_id and a.get("role")=="principal" and (a.get("active",True)) for a in acc)
        check("C3 Julie principal on new company", has_julie_principal, f"access={acc}")
    else:
        _log("info", f"users/{julie_id}/company-access -> {ra.status_code}")

    # Verify c4: /logs
    rl = requests.get(f"{API}/logs", headers=admin_h, timeout=20)
    if rl.status_code == 200:
        logs = rl.json() if isinstance(rl.json(), list) else rl.json().get("logs",[])
        events = " ".join(json.dumps(l) for l in logs[:100])
        check("C4 logs contains company.created", "company.created" in events, "not found in recent logs")
        check("C4 logs contains mandate.created", "mandate.created" in events, "not found in recent logs")
        check("C4 logs contains company.bulk_imported", "company.bulk_imported" in events or "bulk_imported" in events,
              "not found in recent logs")
    else:
        _log("failed", f"GET /logs -> {rl.status_code}")

    # ================================================================
    # CLEANUP
    # ================================================================
    if created_mandate_id:
        for path in [f"/mandates/{created_mandate_id}", f"/admin/mandates/{created_mandate_id}"]:
            r = requests.delete(f"{API}{path}", headers=admin_h, timeout=20)
            _log("info", f"DELETE {path} -> {r.status_code}")
            if r.status_code in (200,204): break

    if created_company_id:
        for path in [f"/companies/{created_company_id}", f"/admin/companies/{created_company_id}"]:
            r = requests.delete(f"{API}{path}", headers=admin_h, timeout=20)
            _log("info", f"DELETE {path} -> {r.status_code}")
            if r.status_code in (200,204): break

    # Cleanup temp user
    if temp_id:
        for path in [f"/users/{temp_id}", f"/admin/users/{temp_id}"]:
            r = requests.delete(f"{API}{path}", headers=admin_h, timeout=20)
            _log("info", f"DELETE {path} -> {r.status_code}")
            if r.status_code in (200,204): break

    # Verify baseline
    rc = requests.get(f"{API}/companies", headers=admin_h, timeout=20)
    comps = rc.json() if isinstance(rc.json(), list) else rc.json().get("companies",[])
    check("E baseline: exactly 2 companies", len(comps) == 2, f"count={len(comps)} names={[c.get('name') for c in comps]}")

    rm = requests.get(f"{API}/mandates", headers=admin_h, timeout=20)
    mands = rm.json() if isinstance(rm.json(), list) else rm.json().get("mandates",[])
    active = [m for m in mands if m.get("status") in (None,"active")]
    check("E baseline: mandates count returns to 0 active", len(active) == 0, f"mandates={mands}")

    ru = requests.get(f"{API}/users", headers=admin_h, timeout=20)
    users = ru.json() if isinstance(ru.json(), list) else ru.json().get("users",[])
    check("E baseline: exactly 3 users", len(users) == 3, f"count={len(users)} emails={[u.get('email') for u in users]}")

    # ---- Print summary ----
    print("\n===== SUMMARY =====")
    print(f"PASSED: {len(RESULTS['passed'])}")
    print(f"FAILED: {len(RESULTS['failed'])}")
    for f in RESULTS['failed']:
        print(f"  - {f}")
    return 0 if not RESULTS['failed'] else 1

if __name__ == "__main__":
    sys.exit(main())
