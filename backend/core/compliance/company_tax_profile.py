"""CH.3 — Swiss company tax profile (versioned) + onboarding/migration.

Rules (GATE CH.3): identity stays in `companies`; country/canton here are the
VERSIONED fiscal context (no divergent duplication of the canonical address).
`unknown` is NEVER auto-converted (always feeds `unresolved`). Published versions
are immutable — any correction (even effective_from) creates a NEW version.
Overlapping published profiles for the same company/effective_from = fail-closed.
UID format/checksum validity is DISTINCT from official online verification.
tax_profile_manage grants profile publish only — never posting/approval/VAT override.
Activation Gate is per-company: A3/A4 stay on legacy until `fiscal_engine_active`.
"""
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

STATUSES = ("draft", "published", "superseded")
_UID_RE = re.compile(r"^CHE[-\s]?(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})$", re.I)


def _now():
    return datetime.now(timezone.utc).isoformat()


# --- UID / VAT number: format+checksum (offline) vs official verification ------
def validate_vat_number(raw):
    """Offline validation ONLY. Never a proof of fiscal status."""
    if not raw:
        return {"format_ok": False, "checksum_ok": False, "normalized": None,
                "online_verified": False, "note": "Numéro absent."}
    m = _UID_RE.match(raw.strip().replace("MWST", "").replace("TVA", "").replace("IVA", "").strip())
    if not m:
        return {"format_ok": False, "checksum_ok": False, "normalized": None,
                "online_verified": False, "note": "Format attendu : CHE-123.456.789."}
    digits = "".join(m.groups())  # 9 digits
    weights = [5, 4, 3, 2, 7, 6, 5, 4]
    total = sum(int(d) * w for d, w in zip(digits[:8], weights))
    check = 11 - (total % 11)
    check = 0 if check == 11 else check
    checksum_ok = (check != 10 and check == int(digits[8]))
    return {"format_ok": True, "checksum_ok": checksum_ok,
            "normalized": f"CHE-{digits[0:3]}.{digits[3:6]}.{digits[6:9]}",
            "online_verified": False,  # set only by an explicit online enrichment step
            "note": "Format/somme de contrôle valides — statut fiscal NON vérifié officiellement."
                    if checksum_ok else "Somme de contrôle invalide."}


# --- Completeness: unknown NEVER auto-converted --------------------------------
def compute_completeness(p):
    unresolved = []
    if p.get("vat_status") in (None, "unknown"):
        unresolved.append({"field": "vat_status", "reason": "Assujettissement TVA à confirmer.",
                           "blocks": ["vat_ch"]})
    elif p.get("vat_status") == "taxable":
        if p.get("vat_method") in (None, "unknown"):
            unresolved.append({"field": "vat_method", "reason": "Méthode de décompte à confirmer.",
                               "blocks": ["vat_return"]})
        if not p.get("vat_number"):
            unresolved.append({"field": "vat_number", "reason": "N° TVA à renseigner.",
                               "blocks": ["vat_invoice_number"]})
    if not p.get("country"):
        unresolved.append({"field": "country", "reason": "Pays requis.", "blocks": ["vat_ch"]})
    state = "complete" if not unresolved else "needs_attention"
    return state, unresolved


def public_profile(d):
    if not d:
        return None
    return {k: d.get(k) for k in (
        "_id", "company_id", "profile_version", "status", "effective_from", "effective_to",
        "country", "canton", "vat_status", "vat_number", "vat_number_validation",
        "vat_method", "vat_method_start", "vat_period", "net_tax_rates",
        "completeness", "unresolved", "source_entry", "created_at", "published_at",
        "supersedes_version_id", "supersession_reason", "superseded_at", "superseded_by")}


def _superseded_ids(docs):
    """Append-only supersession: an old version is 'Remplacée' when a NEWER
    published version references it via supersedes_version_id. The old document
    is never mutated — the state is DERIVED from the chain."""
    return {d["supersedes_version_id"] for d in docs
            if d.get("status") == "published" and d.get("supersedes_version_id")}


async def _active_published(db, ws, co, as_of):
    docs = await db.company_tax_profiles.find({
        "workspace_id": ws, "company_id": co, "status": "published",
        "effective_from": {"$lte": as_of}}).to_list(500)
    docs = [d for d in docs if not d.get("effective_to") or d["effective_to"] > as_of]
    # Resolution = tip of each supersession chain (exclude superseded versions).
    dead = _superseded_ids(docs)
    docs = [d for d in docs if d["_id"] not in dead]
    if not docs:
        return None
    docs.sort(key=lambda d: (d["effective_from"], d["profile_version"]))
    return docs[-1]


async def get_active_profile(db, ws, co, as_of=None):
    return public_profile(await _active_published(db, ws, co, as_of or _now()[:10]))


async def list_versions(db, ws, co):
    docs = await db.company_tax_profiles.find({"workspace_id": ws, "company_id": co}).sort(
        "profile_version", -1).to_list(500)
    dead = _superseded_ids(docs)
    out = []
    for d in docs:
        pub = public_profile(d)
        pub["is_superseded"] = d["_id"] in dead  # DERIVED, never stored on the old doc
        out.append(pub)
    return out


def _source_entry(user, kind, provenance=None):
    if kind not in ("user", "platform", "fiduciary", "migration"):
        kind = "user"
    return {"type": kind, "actor_id": (user or {}).get("id"),
            "actor_email": (user or {}).get("email"), "provenance": provenance, "at": _now()}


async def create_draft(db, ws, co, user, payload, *, source_kind="user", provenance=None):
    published = await db.company_tax_profiles.find({
        "workspace_id": ws, "company_id": co, "status": "published"}).sort("profile_version", -1).to_list(1)
    next_v = (published[0]["profile_version"] + 1) if published else 1
    vatn = payload.get("vat_number")
    p = {"_id": f"txp_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
         "profile_version": next_v, "status": "draft",
         "effective_from": payload.get("effective_from") or _now()[:10],
         "effective_to": payload.get("effective_to"),
         "country": (payload.get("country") or "").upper() or None,
         "canton": (payload.get("canton") or None),
         "vat_status": payload.get("vat_status") or "unknown",
         "vat_number": (validate_vat_number(vatn)["normalized"] if vatn else None),
         "vat_number_validation": validate_vat_number(vatn) if vatn else None,
         "vat_method": payload.get("vat_method") or ("unknown" if payload.get("vat_status") == "taxable" else None),
         "vat_method_start": payload.get("vat_method_start"),
         "vat_period": payload.get("vat_period"),
         "net_tax_rates": payload.get("net_tax_rates") or None,
         "supersedes_version_id": payload.get("supersedes_version_id") or None,
         "supersession_reason": payload.get("supersession_reason") or None,
         "source_entry": _source_entry(user, source_kind, provenance),
         "created_by": (user or {}).get("id"), "created_at": _now(), "published_at": None}
    state, unresolved = compute_completeness(p)
    p["completeness"], p["unresolved"] = state, unresolved
    await db.company_tax_profiles.insert_one(p)
    return public_profile(p)


async def update_draft(db, ws, co, profile_id, payload):
    d = await db.company_tax_profiles.find_one({"_id": profile_id, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    if d["status"] != "draft":
        raise HTTPException(status_code=409, detail="Version publiée immuable : créez une nouvelle version.")
    for f in ("effective_from", "effective_to", "country", "canton", "vat_status", "vat_method",
              "vat_method_start", "vat_period", "net_tax_rates"):
        if f in payload and payload[f] is not None:
            d[f] = payload[f].upper() if f == "country" else payload[f]
    if payload.get("vat_number") is not None:
        v = validate_vat_number(payload["vat_number"])
        d["vat_number"], d["vat_number_validation"] = v["normalized"], v
    d["completeness"], d["unresolved"] = compute_completeness(d)
    await db.company_tax_profiles.update_one({"_id": profile_id}, {"$set": d})
    return public_profile(d)


async def publish(db, ws, co, user, profile_id):
    d = await db.company_tax_profiles.find_one({"_id": profile_id, "workspace_id": ws, "company_id": co})
    if not d:
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    if d["status"] == "published":
        return public_profile(d)
    if d["status"] != "draft":
        raise HTTPException(status_code=409, detail="Publication impossible.")
    # Same-date published versions (candidates for supersession / overlap).
    all_pub = await db.company_tax_profiles.find({
        "workspace_id": ws, "company_id": co, "status": "published"}).to_list(500)
    dead = _superseded_ids(all_pub)
    same_date = [p for p in all_pub if p["effective_from"] == d["effective_from"] and p["_id"] != profile_id]
    # Tip = the not-yet-superseded version for that date (there is at most one).
    live_same_date = [p for p in same_date if p["_id"] not in dead]
    sup_id = d.get("supersedes_version_id")
    superseded = False
    if live_same_date:
        # Overlap without an explicit supersession relation = fail-closed.
        if not sup_id:
            raise HTTPException(status_code=409,
                                detail="Conflit : une version fiscale publiée existe déjà pour cette date d'effet.")
        tip = live_same_date[0]
        # Only the current tip can be superseded — no concurrent supersession branches.
        if sup_id != tip["_id"]:
            raise HTTPException(status_code=409,
                                detail="Rectification impossible : la version ciblée n'est plus la version courante.")
        superseded = True
    elif sup_id:
        # Referenced version must exist, share the date, and still be the live tip.
        target = next((p for p in same_date if p["_id"] == sup_id), None)
        if not target or sup_id in dead:
            raise HTTPException(status_code=409,
                                detail="Rectification impossible : la version à remplacer est introuvable ou déjà remplacée.")
        superseded = True
    upd = {"status": "published", "published_at": _now()}
    if superseded:
        upd["superseded_at"] = _now()
        upd["superseded_by"] = (user or {}).get("id")
    await db.company_tax_profiles.update_one({"_id": profile_id}, {"$set": upd})
    await db.tax_profile_audit.insert_one({
        "_id": f"txpaud_{uuid.uuid4().hex}", "workspace_id": ws, "company_id": co,
        "event": "tax_profile.superseded" if superseded else "tax_profile.published",
        "profile_version": d["profile_version"], "effective_from": d["effective_from"],
        "supersedes_version_id": sup_id if superseded else None,
        "vat_status": d["vat_status"], "vat_method": d.get("vat_method"),
        "source_entry": d.get("source_entry"), "by": (user or {}).get("id"), "at": _now()})
    return public_profile(await db.company_tax_profiles.find_one({"_id": profile_id}))


# --- Migration report (3 columns; sensitive fields never silently confirmed) ---
async def migration_report(db, ws, co):
    company = await db.companies.find_one({"id": co}) or await db.companies.find_one({"_id": co}) or {}
    confirmed, deduced, to_confirm = [], [], []
    if company.get("country"):
        confirmed.append({"field": "country", "value": company["country"], "source": "companies"})
    else:
        to_confirm.append({"field": "country", "reason": "Pays non renseigné."})
    canton = company.get("canton") or company.get("subdivision") or company.get("region")
    if canton:
        deduced.append({"field": "canton", "value": canton, "source": "adresse (déduit)"})
    else:
        to_confirm.append({"field": "canton", "reason": "Canton non identifiable."})
    # vat_status/method are SENSITIVE → never confirmed silently.
    to_confirm.append({"field": "vat_status", "reason": "Assujettissement TVA à confirmer (non déduit)."})
    to_confirm.append({"field": "vat_method", "reason": "Méthode de décompte à confirmer."})
    return {"company_id": co, "confirmed": confirmed, "deduced": deduced, "to_confirm": to_confirm,
            "note": "Aucun champ fiscal sensible n'est confirmé automatiquement."}


async def build_migration_draft(db, ws, co, user):
    company = await db.companies.find_one({"id": co}) or await db.companies.find_one({"_id": co}) or {}
    payload = {"country": company.get("country"),
               "canton": company.get("canton") or company.get("subdivision") or company.get("region"),
               "vat_status": "unknown"}  # sensitive stays unknown → unresolved
    return await create_draft(db, ws, co, user, payload, source_kind="migration",
                              provenance="auto-migration depuis companies")


# --- Activation Gate (per-company; A3/A4 stay on legacy until active) ----------
async def get_activation(db, ws, co):
    d = await db.company_fiscal_activation.find_one({"workspace_id": ws, "company_id": co})
    return {"company_id": co, "fiscal_engine_active": bool(d and d.get("fiscal_engine_active")),
            "activated_at": (d or {}).get("activated_at")}


async def set_activation(db, ws, co, user, active):
    # Guard: only activate when a COMPLETE published profile exists.
    if active:
        prof = await _active_published(db, ws, co, _now()[:10])
        if not prof or prof.get("completeness") != "complete":
            raise HTTPException(status_code=409,
                                detail="Profil fiscal incomplet : impossible d'activer le moteur TVA.")
    await db.company_fiscal_activation.update_one(
        {"workspace_id": ws, "company_id": co},
        {"$set": {"workspace_id": ws, "company_id": co, "fiscal_engine_active": bool(active),
                  "activated_at": _now() if active else None, "by": (user or {}).get("id")}}, upsert=True)
    return await get_activation(db, ws, co)


async def ensure_indexes(db):
    await db.company_tax_profiles.create_index(
        [("workspace_id", 1), ("company_id", 1), ("status", 1), ("effective_from", 1)],
        name="idx_taxprofile")
    await db.company_fiscal_activation.create_index(
        [("workspace_id", 1), ("company_id", 1)], unique=True, name="idx_fiscal_activation")
