"""P2.6 — Normalized accounting journal (journal_entries + journal_entry_lines) on the P2.4 lifecycle.

A journal import references a financial_year + financial_period, groups source
rows into balanced entries (sum debit == sum credit within tolerance), and
resolves every line account_code against the normalized ``accounts`` (P2.3).
Preview never writes journal data; commit writes one entry/line set tied to
``import_id`` (versioned; history never silently overwritten).

Net convention is fixed and sign is NEVER flipped by account type:
    net = debit - credit
Normalized period status gates NEW journal writes (open only). This does NOT
touch legacy acct/qc9434 write behavior. Reconciliation aggregate is read-only
(does NOT overwrite trial_balance_lines). Authorization reuses P1.12 helpers.
"""
from datetime import datetime, timezone, date
from typing import Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .data_imports import _checksum, _cell_str, public_import
from .trial_balance import _parse_number, _resolve_financial_context

_TOLERANCE = 0.01
_DATE_FMT = "%Y-%m-%d"

_VALID_ENTRY_SOURCE = {"import", "manual", "invoice", "supplier_bill", "legacy", "api"}

_J_HEADER_ALIASES = {
    "entry_id": {"entry_id", "entry id", "entry", "écriture", "ecriture", "no écriture", "numéro écriture", "je", "batch"},
    "entry_date": {"entry_date", "entry date", "date", "date écriture", "date ecriture"},
    "reference": {"reference", "référence", "ref", "pièce", "piece", "no pièce"},
    "description": {"description", "libellé", "libelle", "mémo", "memo", "narration"},
    "account_code": {"account_code", "account code", "code", "compte", "no compte", "n° compte", "numéro"},
    "line_description": {"line_description", "line description", "ligne description", "détail", "detail"},
    "debit": {"debit", "débit", "dt", "montant débit"},
    "credit": {"credit", "crédit", "ct", "montant crédit"},
    "external_entry_id": {"external_entry_id", "external entry id", "id écriture externe", "ext entry id"},
    "external_line_id": {"external_line_id", "external line id", "id ligne externe", "ext line id"},
}


class JournalCommitRequest(BaseModel):
    import_id: str


def public_entry(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "financial_year_id": doc.get("financial_year_id"),
        "financial_period_id": doc.get("financial_period_id"),
        "import_id": doc.get("import_id"),
        "entry_date": doc.get("entry_date"),
        "reference": doc.get("reference"),
        "description": doc.get("description"),
        "source_type": doc.get("source_type"),
        "source_system": doc.get("source_system"),
        "external_id": doc.get("external_id"),
        "status": doc.get("status", "posted"),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by"),
        "updated_at": doc.get("updated_at"),
    }


def public_entry_line(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "journal_entry_id": doc.get("journal_entry_id"),
        "account_id": doc.get("account_id"),
        "account_code": doc.get("account_code"),
        "line_number": doc.get("line_number"),
        "description": doc.get("description"),
        "debit": doc.get("debit", 0.0),
        "credit": doc.get("credit", 0.0),
        "net": doc.get("net", 0.0),
        "currency": doc.get("currency"),
        "external_line_id": doc.get("external_line_id"),
        "source_row": doc.get("source_row"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def _parse_date(value: str):
    try:
        return datetime.strptime(value, _DATE_FMT).date()
    except (TypeError, ValueError):
        return None


def _check_period_open(period: dict) -> None:
    st = period.get("status", "open")
    if st != "open":
        raise HTTPException(status_code=409, detail=f"Période {st} — import de journal normalisé refusé")


# ---- Parsing --------------------------------------------------------------
def _norm_j_header(h) -> Optional[str]:
    if h is None:
        return None
    key = str(h).strip().lower()
    for field, aliases in _J_HEADER_ALIASES.items():
        if key in aliases:
            return field
    return None


def parse_journal_file(content: bytes, file_name: str) -> list[dict]:
    name = (file_name or "").lower()
    is_csv = name.endswith(".csv") or (not name.endswith((".xlsx", ".xls")) and b"PK" not in content[:4])
    rows: list[dict] = []
    header_fields: set = set()
    if is_csv:
        import csv as _csv
        import io
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        reader = list(_csv.reader(io.StringIO(text)))
        if not reader:
            raise HTTPException(status_code=400, detail="Fichier vide")
        header_map = {i: _norm_j_header(h) for i, h in enumerate(reader[0])}
        header_fields = {v for v in header_map.values() if v}
        for idx, raw in enumerate(reader[1:], start=2):
            if not any((c or "").strip() for c in raw):
                continue
            row = {"_row": idx}
            for i, field in header_map.items():
                if field and i < len(raw):
                    row[field] = (raw[i] or "").strip()
            rows.append(row)
    else:
        import openpyxl
        import io
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Fichier Excel illisible")
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = next(it)
        except StopIteration:
            raise HTTPException(status_code=400, detail="Fichier vide")
        header_map = {i: _norm_j_header(h) for i, h in enumerate(header)}
        header_fields = {v for v in header_map.values() if v}
        for idx, raw in enumerate(it, start=2):
            if raw is None or not any(c is not None and str(c).strip() for c in raw):
                continue
            row = {"_row": idx}
            for i, field in header_map.items():
                if field and i < len(raw):
                    row[field] = _cell_str(raw[i])
            rows.append(row)

    for req in ("entry_id", "account_code"):
        if req not in header_fields:
            raise HTTPException(status_code=400, detail=f"Colonne requise manquante : {req}")
    if not ({"debit", "credit"} & header_fields):
        raise HTTPException(status_code=400, detail="Colonnes de montant manquantes (debit/credit)")
    return rows


# ---- Validation -----------------------------------------------------------
def validate_journal_rows(rows, company, accounts_by_code, period):
    """Return (entries_preview, warnings_flat, controls).

    Rows are grouped by entry_id (never by row order alone). Each entry is
    validated for account resolution, amount rules, date-in-period and balance.
    """
    currency = company.get("functional_currency")
    p_start = _parse_date(period.get("start_date"))
    p_end = _parse_date(period.get("end_date"))

    # Preserve first-seen order of entries.
    order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        eid = (r.get("entry_id") or "").strip()
        grouped.setdefault(eid, [])
        if eid not in order:
            order.append(eid)
        grouped[eid].append(r)

    entries_preview: list[dict] = []
    warnings_flat: list[dict] = []
    unresolved: set = set()
    tot_debit = tot_credit = 0.0

    for eid in order:
        erows = grouped[eid]
        errors: list[str] = []
        ewarn: list[str] = []
        if not eid:
            errors.append("entry_id manquant")

        # Entry-level fields from first row; detect conflicts across lines.
        first = erows[0]
        entry_date = (first.get("entry_date") or "").strip()
        reference = (first.get("reference") or "").strip()
        description = (first.get("description") or "").strip()
        external_entry_id = (first.get("external_entry_id") or "").strip() or None
        for r in erows[1:]:
            ed = (r.get("entry_date") or "").strip()
            if ed and ed != entry_date:
                errors.append(f"entry_date incohérent dans l'écriture {eid}")
            xe = (r.get("external_entry_id") or "").strip()
            if xe and external_entry_id and xe != external_entry_id:
                errors.append(f"external_entry_id incohérent dans l'écriture {eid}")

        # Date within period.
        d = _parse_date(entry_date) if entry_date else None
        if not entry_date:
            errors.append(f"entry_date manquant (écriture {eid})")
        elif d is None:
            errors.append(f"entry_date invalide (écriture {eid}): {entry_date}")
        elif p_start and p_end and (d < p_start or d > p_end):
            errors.append(f"entry_date hors période ({period.get('start_date')} → {period.get('end_date')}): {entry_date}")

        # Line processing with dedup + amount rules.
        seen_lines: dict = {}
        kept: list[dict] = []
        sum_d = sum_c = 0.0
        for r in erows:
            rownum = r.get("_row")
            code = (r.get("account_code") or "").strip()
            ldesc = (r.get("line_description") or "").strip()
            xl = (r.get("external_line_id") or "").strip() or None
            deb, okd = _parse_number(r.get("debit"))
            cred, okc = _parse_number(r.get("credit"))
            lerr: list[str] = []
            if not okd:
                lerr.append("debit non numérique")
            if not okc:
                lerr.append("credit non numérique")
            deb = deb or 0.0; cred = cred or 0.0
            if deb < 0:
                lerr.append("debit négatif")
            if cred < 0:
                lerr.append("credit négatif")
            if deb > 0 and cred > 0:
                lerr.append("debit et credit positifs simultanément")
            if abs(deb) <= 0 and abs(cred) <= 0:
                lerr.append("ligne sans montant (debit et credit à 0)")

            account = accounts_by_code.get(code) if code else None
            if not code:
                lerr.append("account_code manquant")
            elif not account:
                lerr.append(f"compte introuvable: {code}")
                unresolved.add(code)

            # Dedup within entry.
            line_key = xl if xl else (code, round(deb, 2), round(cred, 2), ldesc)
            if line_key in seen_lines:
                prev = seen_lines[line_key]
                conflict = (prev["account_code"] != code or abs(prev["debit"] - deb) > _TOLERANCE
                            or abs(prev["credit"] - cred) > _TOLERANCE)
                if conflict:
                    lerr.append("ligne dupliquée en conflit (même identifiant, données différentes)")
                else:
                    ewarn.append(f"ligne dupliquée identique ignorée (compte {code})")
                    continue  # skip exact duplicate deterministically

            norm = {"account_code": code, "account_id": (account or {}).get("_id") or (account or {}).get("id"),
                    "description": ldesc, "debit": round(deb, 2), "credit": round(cred, 2),
                    "net": round(deb - cred, 2), "currency": currency,
                    "external_line_id": xl, "source_row": rownum}
            seen_lines[line_key] = norm
            if lerr:
                errors.extend(f"[ligne {rownum}] {m}" for m in lerr)
            else:
                kept.append(norm)
                sum_d += deb; sum_c += cred

        # Balance rule (only meaningful when there are no line-level errors).
        balanced = abs(round(sum_d - sum_c, 2)) <= _TOLERANCE
        if not errors and not balanced:
            errors.append(f"écriture déséquilibrée: débits {round(sum_d,2)} ≠ crédits {round(sum_c,2)}")

        # Assign contiguous line numbers.
        for i, ln in enumerate(kept, start=1):
            ln["line_number"] = i

        action = "reject" if errors else "import"
        if action == "import":
            tot_debit += sum_d; tot_credit += sum_c

        entries_preview.append({
            "entry_id": eid, "entry_date": entry_date, "reference": reference,
            "description": description, "external_entry_id": external_entry_id,
            "line_count": len(kept), "entry_debit": round(sum_d, 2), "entry_credit": round(sum_c, 2),
            "balanced": balanced, "action": action, "errors": errors, "warnings": ewarn,
            "lines": kept,
        })
        for w in ewarn:
            warnings_flat.append({"entry_id": eid, "warning": w})

    controls = {
        "entry_count": sum(1 for e in entries_preview if e["action"] == "import"),
        "line_count": sum(e["line_count"] for e in entries_preview if e["action"] == "import"),
        "total_debit": round(tot_debit, 2), "total_credit": round(tot_credit, 2),
        "difference": round(tot_debit - tot_credit, 2),
        "unresolved_codes": sorted(unresolved),
    }
    return entries_preview, warnings_flat, controls


# ---- Lifecycle: preview ---------------------------------------------------
async def preview_journal_import(db, company_id, user, content, file_name,
                                 financial_year_id, financial_period_id, source_type="import"):
    company = await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    if not financial_year_id or not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_year_id et financial_period_id requis")
    _fy, fp = await _resolve_financial_context(db, company_id, workspace_id, financial_year_id, financial_period_id)
    _check_period_open(fp)  # open only for NEW normalized journal writes

    checksum = _checksum(content)
    idempotency_key = f"{workspace_id}:{company_id}:journal:{financial_period_id}:{checksum}"
    now = datetime.now(timezone.utc).isoformat()

    rows = parse_journal_file(content, file_name)
    accounts = await db.accounts.find({"workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    accounts_by_code = {a.get("account_code"): a for a in accounts}
    entries_preview, warnings_flat, controls = validate_journal_rows(rows, company, accounts_by_code, fp)

    rejected = sum(1 for e in entries_preview if e["action"] == "reject")
    to_apply = [e for e in entries_preview if e["action"] == "import"]
    status = "failed" if rejected else "valid"
    error_summary = f"{rejected} écriture(s) en erreur" if rejected else None

    doc = {
        "_id": f"imp_{uuid.uuid4().hex}",
        "workspace_id": workspace_id, "company_id": company_id,
        "source_type": source_type, "data_type": "journal", "source_system": source_type,
        "file_name": file_name, "file_reference": None,
        "financial_year_id": financial_year_id, "financial_period_id": financial_period_id,
        "status": status, "version": 1,
        "records_received": len(rows), "records_created": 0, "records_updated": 0,
        "records_rejected": rejected,
        "checksum": checksum, "idempotency_key": idempotency_key,
        "started_at": now, "completed_at": None,
        "created_by": user.get("id"), "created_at": now, "updated_at": now,
        "error_summary": error_summary, "warnings": warnings_flat,
        "metadata": {"apply_entries": [
            {"entry_id": e["entry_id"], "entry_date": e["entry_date"], "reference": e["reference"],
             "description": e["description"], "external_entry_id": e["external_entry_id"],
             "lines": e["lines"]} for e in to_apply],
            "controls": controls},
    }
    await db.data_imports.insert_one(doc)

    result = public_import(doc)
    result["entries_preview"] = entries_preview
    result["controls"] = controls
    result["counts"] = {"received": len(rows), "entries_to_import": len(to_apply),
                        "rejected": rejected, "warnings": len(warnings_flat)}
    return result


# ---- Lifecycle: commit ----------------------------------------------------
async def commit_journal_import(db, company_id, user, import_id):
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    doc = await db.data_imports.find_one({
        "_id": import_id, "workspace_id": workspace_id, "company_id": company_id, "data_type": "journal"})
    if not doc:
        raise HTTPException(status_code=404, detail="Import introuvable")
    if doc.get("status") in ("completed", "completed_with_warnings"):
        return {"already_committed": True, **public_import(doc)}
    if doc.get("status") == "failed":
        raise HTTPException(status_code=409, detail="Import en échec — corriger les erreurs bloquantes avant validation")
    if doc.get("status") != "valid":
        raise HTTPException(status_code=409, detail=f"Statut d'import non validable: {doc.get('status')}")

    # Re-check period status at commit time (open only).
    fp = await db.financial_periods.find_one({
        "_id": doc.get("financial_period_id"), "workspace_id": workspace_id, "company_id": company_id})
    if not fp:
        raise HTTPException(status_code=404, detail="Période introuvable")
    _check_period_open(fp)

    # Retry safety.
    existing = await db.journal_entries.find_one({
        "workspace_id": workspace_id, "company_id": company_id, "import_id": import_id})
    if existing:
        return {"already_committed": True, **public_import(doc)}

    now = datetime.now(timezone.utc).isoformat()
    await db.data_imports.update_one({"_id": import_id}, {"$set": {"status": "importing", "updated_at": now}})

    apply_entries = (doc.get("metadata") or {}).get("apply_entries", [])
    entry_count = line_count = 0
    for e in apply_entries:
        je_id = f"je_{uuid.uuid4().hex}"
        entry_doc = {
            "_id": je_id, "workspace_id": workspace_id, "company_id": company_id,
            "financial_year_id": doc.get("financial_year_id"),
            "financial_period_id": doc.get("financial_period_id"),
            "import_id": import_id,
            "entry_date": e["entry_date"], "reference": e.get("reference"),
            "description": e.get("description"),
            "source_type": doc.get("source_type"), "source_system": doc.get("source_system"),
            "external_id": e.get("external_entry_id"), "status": "posted",
            "created_at": now, "created_by": user.get("id"), "updated_at": now,
        }
        await db.journal_entries.insert_one(entry_doc)
        entry_count += 1
        for ln in e["lines"]:
            line_doc = {
                "_id": f"jel_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
                "journal_entry_id": je_id, "account_id": ln["account_id"], "account_code": ln["account_code"],
                "line_number": ln["line_number"], "description": ln.get("description"),
                "debit": ln["debit"], "credit": ln["credit"], "net": ln["net"],
                "currency": ln["currency"], "external_line_id": ln.get("external_line_id"),
                "source_row": ln.get("source_row"), "created_at": now, "updated_at": now,
            }
            await db.journal_entry_lines.insert_one(line_doc)
            line_count += 1

    warnings = list(doc.get("warnings", []))
    final_status = "completed_with_warnings" if warnings else "completed"
    await db.data_imports.update_one({"_id": import_id}, {"$set": {
        "status": final_status, "records_created": entry_count, "completed_at": now, "updated_at": now,
        "metadata": {**(doc.get("metadata") or {}), "committed_line_count": line_count},
    }})
    doc = await db.data_imports.find_one({"_id": import_id})
    result = public_import(doc)
    result["entry_count"] = entry_count
    result["line_count"] = line_count
    result["controls"] = (doc.get("metadata") or {}).get("controls", {})
    return result


# ---- Read -----------------------------------------------------------------
async def _lines_for_entry(db, workspace_id, company_id, je_id):
    docs = await db.journal_entry_lines.find({
        "workspace_id": workspace_id, "company_id": company_id, "journal_entry_id": je_id}).to_list(None)
    docs.sort(key=lambda d: (d.get("line_number") or 0))
    return [public_entry_line(d) for d in docs]


async def list_journal_entries(db, company_id, user, financial_period_id=None, import_id=None,
                               account_id=None, date_from=None, date_to=None, reference=None):
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    query = {"workspace_id": workspace_id, "company_id": company_id}
    if financial_period_id:
        query["financial_period_id"] = financial_period_id
    if import_id:
        query["import_id"] = import_id
    entries = await db.journal_entries.find(query).to_list(None)

    # account_id filter → restrict to entries containing that account.
    allowed_ids = None
    if account_id:
        lines = await db.journal_entry_lines.find({
            "workspace_id": workspace_id, "company_id": company_id, "account_id": account_id}).to_list(None)
        allowed_ids = {l.get("journal_entry_id") for l in lines}

    out = []
    for e in entries:
        if allowed_ids is not None and e.get("_id") not in allowed_ids:
            continue
        ed = e.get("entry_date") or ""
        if date_from and ed < date_from:
            continue
        if date_to and ed > date_to:
            continue
        if reference and reference.lower() not in (e.get("reference") or "").lower():
            continue
        lines = await _lines_for_entry(db, workspace_id, company_id, e.get("_id"))
        pub = public_entry(e)
        pub["lines"] = lines
        pub["entry_debit"] = round(sum(l["debit"] for l in lines), 2)
        pub["entry_credit"] = round(sum(l["credit"] for l in lines), 2)
        out.append(pub)
    out.sort(key=lambda x: (x.get("entry_date") or "", x.get("reference") or ""))
    return out


async def get_journal_entry(db, company_id, entry_id, user):
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    e = await db.journal_entries.find_one({
        "_id": entry_id, "workspace_id": workspace_id, "company_id": company_id})
    if not e:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    lines = await _lines_for_entry(db, workspace_id, company_id, entry_id)
    pub = public_entry(e)
    pub["lines"] = lines
    pub["entry_debit"] = round(sum(l["debit"] for l in lines), 2)
    pub["entry_credit"] = round(sum(l["credit"] for l in lines), 2)
    return pub


async def aggregate_journal(db, company_id, user, financial_period_id=None, import_id=None):
    """Read-only reconciliation aggregate. Does NOT touch trial_balance_lines and
    is NOT the Trial Balance source of truth yet (full reconciliation = P2.9)."""
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    # Resolve the set of entries in scope, then aggregate their lines.
    eq = {"workspace_id": workspace_id, "company_id": company_id}
    if financial_period_id:
        eq["financial_period_id"] = financial_period_id
    if import_id:
        eq["import_id"] = import_id
    entries = await db.journal_entries.find(eq).to_list(None)
    entry_ids = {e.get("_id") for e in entries}

    lines = await db.journal_entry_lines.find({
        "workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    by_account: dict = {}
    tot_d = tot_c = 0.0
    for l in lines:
        if l.get("journal_entry_id") not in entry_ids:
            continue
        aid = l.get("account_id")
        agg = by_account.setdefault(aid, {"account_id": aid, "account_code": l.get("account_code"),
                                          "debit": 0.0, "credit": 0.0, "net": 0.0})
        agg["debit"] = round(agg["debit"] + l.get("debit", 0.0), 2)
        agg["credit"] = round(agg["credit"] + l.get("credit", 0.0), 2)
        agg["net"] = round(agg["debit"] - agg["credit"], 2)
        tot_d += l.get("debit", 0.0); tot_c += l.get("credit", 0.0)
    return {
        "total_debit": round(tot_d, 2), "total_credit": round(tot_c, 2),
        "difference": round(tot_d - tot_c, 2),
        "by_account": sorted(by_account.values(), key=lambda x: (x.get("account_code") or "")),
    }


async def ensure_indexes(db) -> None:
    await db.journal_entries.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_period_id", 1)], name="idx_je_period")
    await db.journal_entries.create_index(
        [("workspace_id", 1), ("company_id", 1), ("import_id", 1)], name="idx_je_import")
    await db.journal_entries.create_index(
        [("workspace_id", 1), ("company_id", 1), ("entry_date", 1)], name="idx_je_date")
    await db.journal_entries.create_index(
        [("workspace_id", 1), ("company_id", 1), ("source_system", 1), ("external_id", 1)],
        unique=True, partialFilterExpression={"external_id": {"$type": "string"}},
        name="uniq_je_external_id_per_source")
    await db.journal_entry_lines.create_index(
        [("workspace_id", 1), ("company_id", 1), ("journal_entry_id", 1), ("line_number", 1)],
        unique=True, name="uniq_jel_entry_line_number")
    await db.journal_entry_lines.create_index(
        [("workspace_id", 1), ("company_id", 1), ("account_id", 1)], name="idx_jel_account")
    await db.journal_entry_lines.create_index(
        [("workspace_id", 1), ("company_id", 1), ("journal_entry_id", 1)], name="idx_jel_entry")
