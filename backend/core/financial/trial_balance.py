"""P2.5 — Normalized Trial Balance (trial_balance_lines) on top of the P2.4 data_imports lifecycle.

A Trial Balance import references a financial_year + financial_period and resolves
every source account_code against the normalized ``accounts`` collection (P2.3).
Preview never writes ``trial_balance_lines``; commit writes one line set tied to
``import_id`` (versioned per period — history is never silently overwritten).

Net convention is fixed and sign is NEVER flipped by account type:
    period_net = period_debit - period_credit
    ytd_net    = ytd_debit    - ytd_credit
Presentation / normal-balance logic belongs to later reporting phases.
Authorization reuses the P1.12 helpers; structural TB import = workspace admin
only (consistent with P2.4). No FX conversion. Legacy acct_*/qc9434_* untouched.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .data_imports import _checksum, _cell_str, public_import  # noqa: F401 (_checksum/_cell_str reused)
from .ingestion.readers import read_tabular

_TOLERANCE = 0.01  # currency 2-decimal tolerance

_TB_HEADER_ALIASES = {
    "account_code": {"account_code", "account code", "code", "compte", "no compte", "n° compte", "numero", "numéro"},
    "account_name": {"account_name", "account name", "name", "nom", "libelle", "libellé", "description"},
    "period_debit": {"period_debit", "period debit", "débit période", "debit periode", "debit", "débit", "mouvement débit", "dt"},
    "period_credit": {"period_credit", "period credit", "crédit période", "credit periode", "credit", "crédit", "mouvement crédit", "ct"},
    "period_net": {"period_net", "period net", "net période", "net periode", "mouvement", "net"},
    "ytd_debit": {"ytd_debit", "ytd debit", "débit cumul", "cumul débit", "débit à date", "debit cumul"},
    "ytd_credit": {"ytd_credit", "ytd credit", "crédit cumul", "cumul crédit", "crédit à date", "credit cumul"},
    "ytd_net": {"ytd_net", "ytd net", "net cumul", "cumulatif", "solde cumul", "solde à date"},
}


class TBCommitRequest(BaseModel):
    import_id: str


def public_tb_line(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "financial_year_id": doc.get("financial_year_id"),
        "financial_period_id": doc.get("financial_period_id"),
        "import_id": doc.get("import_id"),
        "account_id": doc.get("account_id"),
        "account_code": doc.get("account_code"),
        "period_debit": doc.get("period_debit", 0.0),
        "period_credit": doc.get("period_credit", 0.0),
        "period_net": doc.get("period_net", 0.0),
        "ytd_debit": doc.get("ytd_debit", 0.0),
        "ytd_credit": doc.get("ytd_credit", 0.0),
        "ytd_net": doc.get("ytd_net", 0.0),
        "currency": doc.get("currency"),
        "source_row": doc.get("source_row"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# ---- Parsing --------------------------------------------------------------
def _norm_tb_header(h) -> Optional[str]:
    if h is None:
        return None
    key = str(h).strip().lower()
    for field, aliases in _TB_HEADER_ALIASES.items():
        if key in aliases:
            return field
    return None


def _parse_number(raw):
    """Return (value, ok). Empty → 0.0. Supports negatives, accounting parens,
    french/US thousand & decimal separators. Non-numeric → (None, False)."""
    if raw is None:
        return 0.0, True
    s = str(raw).strip().replace("\xa0", "").replace(" ", "")
    if s == "":
        return 0.0, True
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if "," in s and "." in s:
        s = s.replace(",", "")       # comma = thousands separator
    elif "," in s:
        s = s.replace(",", ".")      # comma = decimal separator
    try:
        val = float(s)
    except ValueError:
        return None, False
    return (-val if neg else val), True


def parse_trial_balance_file(content: bytes, file_name: str) -> list[dict]:
    """Parse an Excel/CSV Trial Balance into raw rows keyed by TB field (P2.7 shared reader).
    account_code preserved as string. Raises 400 on unreadable file / missing headers."""
    rows, header_fields = read_tabular(content, file_name, _norm_tb_header)
    if "account_code" not in header_fields:
        raise HTTPException(status_code=400, detail="Colonne requise manquante : account_code")
    if not ({"period_debit", "period_credit"} & header_fields) and "period_net" not in header_fields:
        raise HTTPException(status_code=400, detail="Colonnes de mouvement manquantes (period_debit/period_credit ou period_net)")
    return rows


# ---- Financial context ----------------------------------------------------
async def _resolve_financial_context(db, company_id, workspace_id, financial_year_id, financial_period_id):
    fy = await db.financial_years.find_one({
        "_id": financial_year_id, "workspace_id": workspace_id, "company_id": company_id})
    if not fy:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    fp = await db.financial_periods.find_one({
        "_id": financial_period_id, "workspace_id": workspace_id, "company_id": company_id})
    if not fp:
        raise HTTPException(status_code=404, detail="Période introuvable")
    if fp.get("financial_year_id") != financial_year_id:
        raise HTTPException(status_code=422, detail="La période n'appartient pas à cet exercice")
    return fy, fp


# ---- Validation -----------------------------------------------------------
def validate_tb_rows(rows, company, accounts_by_code):
    """Return (preview_rows, warnings_flat, controls, blocking).

    preview_rows entries carry a normalized numeric payload + account_id when
    resolved. controls holds period/ytd totals & differences.
    """
    currency = company.get("functional_currency")
    seen: dict = {}
    preview: list[dict] = []
    warnings_flat: list[dict] = []
    unresolved: list[str] = []

    p_deb = p_cred = y_deb = y_cred = 0.0

    for r in rows:
        rownum = r.get("_row")
        code = (r.get("account_code") or "").strip()
        errors: list[str] = []
        rwarn: list[str] = []

        if not code:
            errors.append("account_code manquant")

        pd, ok1 = _parse_number(r.get("period_debit"))
        pc, ok2 = _parse_number(r.get("period_credit"))
        yd, ok3 = _parse_number(r.get("ytd_debit"))
        yc, ok4 = _parse_number(r.get("ytd_credit"))
        for ok, fld in ((ok1, "period_debit"), (ok2, "period_credit"), (ok3, "ytd_debit"), (ok4, "ytd_credit")):
            if not ok:
                errors.append(f"valeur non numérique: {fld}")
        pd = pd or 0.0; pc = pc or 0.0; yd = yd or 0.0; yc = yc or 0.0

        # Net convention (never sign-flipped by account type).
        period_net = round(pd - pc, 2)
        ytd_net = round(yd - yc, 2)

        # Supplied-net consistency.
        if (r.get("period_net") or "").strip():
            sn, oks = _parse_number(r.get("period_net"))
            if not oks:
                errors.append("valeur non numérique: period_net")
            elif abs(sn - period_net) > _TOLERANCE:
                errors.append(f"period_net incohérent (fourni {sn}, calculé {period_net})")
        if (r.get("ytd_net") or "").strip():
            syn, oky = _parse_number(r.get("ytd_net"))
            if not oky:
                errors.append("valeur non numérique: ytd_net")
            elif abs(syn - ytd_net) > _TOLERANCE:
                errors.append(f"ytd_net incohérent (fourni {syn}, calculé {ytd_net})")

        # Account resolution against normalized accounts (never create here).
        account = accounts_by_code.get(code) if code else None
        if code and not account:
            errors.append(f"compte introuvable dans le plan comptable normalisé: {code}")
            unresolved.append(code)

        normalized = {
            "account_code": code,
            "account_id": (account or {}).get("_id") or (account or {}).get("id"),
            "period_debit": round(pd, 2), "period_credit": round(pc, 2), "period_net": period_net,
            "ytd_debit": round(yd, 2), "ytd_credit": round(yc, 2), "ytd_net": ytd_net,
            "currency": currency, "source_row": rownum,
        }

        # In-file duplicate handling (exact → dedupe warning; conflicting → blocking).
        if code and code in seen:
            prev = seen[code]["normalized"]
            conflict = any(abs(prev[k] - normalized[k]) > _TOLERANCE
                           for k in ("period_debit", "period_credit", "ytd_debit", "ytd_credit"))
            if conflict:
                errors.append(f"compte dupliqué en conflit dans le fichier (ligne {seen[code]['row']})")
            else:
                rwarn.append("ligne dupliquée identique — ignorée")
                preview.append({"row": rownum, "account_code": code, "action": "skip",
                                "warnings": rwarn, "errors": []})
                continue

        action = "reject" if errors else "import"
        if action == "import":
            p_deb += pd; p_cred += pc; y_deb += yd; y_cred += yc
        if code:
            seen[code] = {"row": rownum, "normalized": normalized}

        preview.append({"row": rownum, "account_code": code, "action": action,
                        "warnings": rwarn, "errors": errors, "normalized": normalized})
        for w in rwarn:
            warnings_flat.append({"row": rownum, "account_code": code, "warning": w})

    period_diff = round(p_deb - p_cred, 2)
    ytd_diff = round(y_deb - y_cred, 2)
    controls = {
        "period_total_debit": round(p_deb, 2), "period_total_credit": round(p_cred, 2),
        "period_difference": period_diff,
        "ytd_total_debit": round(y_deb, 2), "ytd_total_credit": round(y_cred, 2),
        "ytd_difference": ytd_diff,
        "period_balanced": abs(period_diff) <= _TOLERANCE,
        "ytd_balanced": abs(ytd_diff) <= _TOLERANCE,
        "unresolved_codes": sorted(set(unresolved)),
    }
    return preview, warnings_flat, controls


# ---- Lifecycle (delegated to the P2.7 ingestion orchestrator) -------------
async def preview_trial_balance_import(db, company_id, user, content, file_name,
                                       financial_year_id, financial_period_id, source_type="excel"):
    from .ingestion.orchestrator import run_preview
    from .ingestion.registry import get_adapter
    return await run_preview(db, get_adapter("trial_balance"), company_id, user, content, file_name,
                             source_type, ctx={"financial_year_id": financial_year_id,
                                               "financial_period_id": financial_period_id})


async def commit_trial_balance_import(db, company_id, user, import_id):
    from .ingestion.orchestrator import run_commit
    from .ingestion.registry import get_adapter
    return await run_commit(db, get_adapter("trial_balance"), company_id, user, import_id)


# ---- Read -----------------------------------------------------------------
def _controls_from_lines(lines):
    pd = round(sum(l["period_debit"] for l in lines), 2)
    pc = round(sum(l["period_credit"] for l in lines), 2)
    yd = round(sum(l["ytd_debit"] for l in lines), 2)
    yc = round(sum(l["ytd_credit"] for l in lines), 2)
    return {
        "period_total_debit": pd, "period_total_credit": pc, "period_difference": round(pd - pc, 2),
        "ytd_total_debit": yd, "ytd_total_credit": yc, "ytd_difference": round(yd - yc, 2),
        "line_count": len(lines),
    }


async def list_trial_balance(db, company_id, user, financial_period_id=None,
                             import_id=None, account_id=None):
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    query = {"workspace_id": workspace_id, "company_id": company_id}
    if financial_period_id:
        query["financial_period_id"] = financial_period_id
    if import_id:
        query["import_id"] = import_id
    if account_id:
        query["account_id"] = account_id
    docs = await db.trial_balance_lines.find(query).to_list(None)
    docs.sort(key=lambda d: (d.get("account_code") or ""))
    lines = [public_tb_line(d) for d in docs]
    return {"lines": lines, "controls": _controls_from_lines(lines)}


async def ensure_indexes(db) -> None:
    await db.trial_balance_lines.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_period_id", 1), ("import_id", 1)],
        name="idx_tbl_period_import",
    )
    await db.trial_balance_lines.create_index(
        [("workspace_id", 1), ("company_id", 1), ("import_id", 1), ("account_id", 1)],
        unique=True, name="uniq_tbl_import_account",
    )
    await db.trial_balance_lines.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_period_id", 1), ("account_id", 1)],
        name="idx_tbl_period_account",
    )
