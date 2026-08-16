"""Smoke sécurité P1.13A (via l'API réelle). Vérifie l'accès EFFECTIF au module
ACCOUNTING (navigation gated par resolve_effective_access) pour chaque compte,
+ no-leak cross-workspace. À lancer AVANT et APRÈS le commit.

Usage: python scripts/smoke_p1_13a.py [--tag before|after]
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ.get("PUBLIC_API", "http://localhost:8001")
MEELORA = "965f0770-8cf2-4199-a99f-819ff270436a"
QC9434 = "58a59a28-4701-4ba5-8e2f-61ff76e0f2e9"
GHOST = "cmp_does_not_exist_000000000000"

ACCOUNTS = [
    ("julie@accslegro.com", "julie123"),
    ("marc@accslegro.com", "marc123"),
    ("platform@meelora.com", "platform123"),
    ("persona_reporting@accslegro.com", "persona123"),
    ("persona_consol@accslegro.com", "persona123"),
    ("persona_budgets@accslegro.com", "persona123"),
]


def _req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"detail": (e.read().decode() or "")[:200]}


def login(email, pw):
    st, d = _req("POST", "/api/auth/login", body={"email": email, "password": pw})
    return d.get("token") or d.get("access_token")


def acct_of(nav):
    for m in nav.get("modules", []):
        if m.get("module_code") == "ACCOUNTING":
            return m
    return None


def main(tag):
    print(f"===== SMOKE SÉCURITÉ P1.13A [{tag}] (base={BASE}) =====")
    for email, pw in ACCOUNTS:
        tok = login(email, pw)
        if not tok:
            print(f"  {email:40s} : LOGIN ÉCHEC")
            continue
        st, nav = _req("GET", f"/api/companies/{MEELORA}/navigation", token=tok)
        m = acct_of(nav) if st == 200 else None
        if m:
            print(f"  {email:40s} : ACCOUNTING = {m['level']} (source={m['source']}) [http {st}]")
        else:
            print(f"  {email:40s} : ACCOUNTING = AUCUN [http {st}]")
    # No-leak: Julie sur société inconnue -> 404 ; Julie sur 9434 (sans accès) -> 403.
    tok = login("julie@accslegro.com", "julie123")
    st_ghost, _ = _req("GET", f"/api/companies/{GHOST}/navigation", token=tok)
    st_9434, d9434 = _req("GET", f"/api/companies/{QC9434}/navigation", token=tok)
    print(f"  no-leak: Julie -> société inconnue = HTTP {st_ghost} (attendu 404) ; Julie -> 9434 = HTTP {st_9434} (attendu 403/404)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="before")
    main(p.parse_args().tag)
