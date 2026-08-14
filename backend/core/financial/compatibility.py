"""P2.8 — Legacy compatibility bridge (READ-ONLY).

Lets legacy consumers read normalized V2 financial data (accounts / trial
balance / journal) in legacy-compatible shapes, WITHOUT copying data back into
legacy collections and WITHOUT changing financial formulas. Source selection is
company-scoped, backend-enforced, defaults to ``legacy`` and is reversible.

This module NEVER writes to acct_* / qc9434_*; the only collection it writes is
``financial_config`` (the company-scoped source flag). No silent legacy fallback:
if normalized mode is on but required data is missing, a controlled error is
returned. P&L / Balance Sheet / Cash Flow engines stay on legacy (migration =
later phases; reconciliation = P2.9).
"""
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from ..permissions import require_company_access, require_company_admin, require_tenant_context

VALID_SOURCES = {"legacy", "normalized"}
DEFAULT_SOURCE = "legacy"


class FinancialSourceUpdate(BaseModel):
    source: str


# ---- Source selection (company-scoped feature flag) -----------------------
async def get_financial_source(db, company_id: str, workspace_id: str) -> str:
    cfg = await db.financial_config.find_one({"workspace_id": workspace_id, "company_id": company_id})
    src = (cfg or {}).get("financial_data_source")
    return src if src in VALID_SOURCES else DEFAULT_SOURCE


async def set_financial_source(db, company_id: str, user: dict, source: str) -> dict:
    """Admin-only, company-scoped, reversible. Returns old/new for logging."""
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"Source financière invalide: {source} (attendu legacy|normalized)")
    old = await get_financial_source(db, company_id, workspace_id)
    now = datetime.now(timezone.utc).isoformat()
    cfg = await db.financial_config.find_one({"workspace_id": workspace_id, "company_id": company_id})
    if cfg:
        await db.financial_config.update_one(
            {"_id": cfg["_id"]},
            {"$set": {"financial_data_source": source, "updated_at": now, "updated_by": user.get("id")}})
    else:
        await db.financial_config.insert_one({
            "_id": f"fcfg_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
            "financial_data_source": source, "created_at": now, "updated_at": now, "updated_by": user.get("id")})
    return {"company_id": company_id, "old_source": old, "new_source": source, "source": source}


# ---- Version selection (deterministic) ------------------------------------
async def _latest_completed_import(db, workspace_id, company_id, data_type, financial_period_id=None):
    """Deterministic rule: the latest successfully completed import for the
    requested company (+period), ordered by (completed_at, _id). Failed /
    incomplete imports are never selected."""
    q = {"workspace_id": workspace_id, "company_id": company_id, "data_type": data_type,
         "status": {"$in": ["completed", "completed_with_warnings"]}}
    if financial_period_id:
        q["financial_period_id"] = financial_period_id
    docs = await db.data_imports.find(q).to_list(None)
    if not docs:
        return None
    docs.sort(key=lambda d: (d.get("completed_at") or "", d.get("_id") or ""))
    return docs[-1]


# ---- Compatibility adapters (normalized → legacy-compatible shapes) -------
class NormalizedAccountsCompatibilityAdapter:
    async def read(self, db, company_id, workspace_id, active_only=False):
        q = {"workspace_id": workspace_id, "company_id": company_id}
        if active_only:
            q["active"] = True
        docs = await db.accounts.find(q).to_list(None)
        docs.sort(key=lambda d: (d.get("account_code") or ""))
        return [{
            "account_code": d.get("account_code"),   # preserved string exactly
            "account_name": d.get("account_name"),
            "active": d.get("active", True),
            "account_type": d.get("account_type"),
            "normal_balance": d.get("normal_balance"),
            "currency": d.get("currency"),
        } for d in docs]


class NormalizedTrialBalanceCompatibilityAdapter:
    async def read(self, db, company_id, workspace_id, financial_period_id):
        imp = await _latest_completed_import(db, workspace_id, company_id, "trial_balance", financial_period_id)
        if not imp:
            raise HTTPException(status_code=409,
                                detail="Données normalisées de balance indisponibles pour cette période")
        docs = await db.trial_balance_lines.find({
            "workspace_id": workspace_id, "company_id": company_id, "import_id": imp["_id"]}).to_list(None)
        docs.sort(key=lambda d: (d.get("account_code") or ""))
        lines = [{
            "account_code": d.get("account_code"),
            "period_debit": d.get("period_debit", 0.0), "period_credit": d.get("period_credit", 0.0),
            "period_net": d.get("period_net", 0.0),
            "ytd_debit": d.get("ytd_debit", 0.0), "ytd_credit": d.get("ytd_credit", 0.0),
            "ytd_net": d.get("ytd_net", 0.0), "currency": d.get("currency"),
        } for d in docs]
        controls = {
            "period_total_debit": round(sum(l["period_debit"] for l in lines), 2),
            "period_total_credit": round(sum(l["period_credit"] for l in lines), 2),
            "ytd_total_debit": round(sum(l["ytd_debit"] for l in lines), 2),
            "ytd_total_credit": round(sum(l["ytd_credit"] for l in lines), 2),
            "line_count": len(lines),
        }
        controls["period_difference"] = round(controls["period_total_debit"] - controls["period_total_credit"], 2)
        controls["ytd_difference"] = round(controls["ytd_total_debit"] - controls["ytd_total_credit"], 2)
        return {"import_id": imp["_id"], "financial_period_id": financial_period_id,
                "lines": lines, "controls": controls}


class NormalizedJournalCompatibilityAdapter:
    async def read(self, db, company_id, workspace_id, financial_period_id):
        imp = await _latest_completed_import(db, workspace_id, company_id, "journal", financial_period_id)
        if not imp:
            raise HTTPException(status_code=409,
                                detail="Données normalisées de journal indisponibles pour cette période")
        entries = await db.journal_entries.find({
            "workspace_id": workspace_id, "company_id": company_id, "import_id": imp["_id"]}).to_list(None)
        out = []
        total_d = total_c = 0.0
        for e in entries:
            lines = await db.journal_entry_lines.find({
                "workspace_id": workspace_id, "company_id": company_id, "journal_entry_id": e["_id"]}).to_list(None)
            lines.sort(key=lambda d: (d.get("line_number") or 0))  # preserve line ordering
            elines = [{
                "line_number": l.get("line_number"), "account_code": l.get("account_code"),
                "debit": l.get("debit", 0.0), "credit": l.get("credit", 0.0), "net": l.get("net", 0.0),
                "description": l.get("description"),
            } for l in lines]
            total_d += sum(l["debit"] for l in elines)
            total_c += sum(l["credit"] for l in elines)
            out.append({
                "entry_date": e.get("entry_date"), "reference": e.get("reference"),
                "description": e.get("description"), "lines": elines,
            })
        out.sort(key=lambda x: (x.get("entry_date") or "", x.get("reference") or ""))
        controls = {"total_debit": round(total_d, 2), "total_credit": round(total_c, 2),
                    "difference": round(total_d - total_c, 2), "entry_count": len(out)}
        return {"import_id": imp["_id"], "financial_period_id": financial_period_id,
                "entries": out, "controls": controls}


_ACCOUNTS_ADAPTER = NormalizedAccountsCompatibilityAdapter()
_TB_ADAPTER = NormalizedTrialBalanceCompatibilityAdapter()
_JOURNAL_ADAPTER = NormalizedJournalCompatibilityAdapter()


# ---- Legacy-mode marker (existing legacy endpoints remain the source) -----
def _legacy_marker(source):
    return {"source": source, "mode": "legacy", "use_legacy_endpoint": True, "data": None,
            "message": "Mode legacy actif — utiliser les endpoints financiers legacy existants."}


# ---- Public compatibility reads -------------------------------------------
async def compat_accounts(db, company_id, user, active_only=False):
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    source = await get_financial_source(db, company_id, workspace_id)
    if source != "normalized":
        return _legacy_marker(source)
    accounts = await _ACCOUNTS_ADAPTER.read(db, company_id, workspace_id, active_only=active_only)
    return {"source": "normalized", "accounts": accounts, "count": len(accounts)}


async def compat_trial_balance(db, company_id, user, financial_period_id):
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    if not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_period_id requis")
    source = await get_financial_source(db, company_id, workspace_id)
    if source != "normalized":
        return _legacy_marker(source)
    data = await _TB_ADAPTER.read(db, company_id, workspace_id, financial_period_id)
    return {"source": "normalized", **data}


async def compat_journal(db, company_id, user, financial_period_id):
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    if not financial_period_id:
        raise HTTPException(status_code=422, detail="financial_period_id requis")
    source = await get_financial_source(db, company_id, workspace_id)
    if source != "normalized":
        return _legacy_marker(source)
    data = await _JOURNAL_ADAPTER.read(db, company_id, workspace_id, financial_period_id)
    return {"source": "normalized", **data}


async def financial_source_status(db, company_id, user, financial_period_id=None):
    """P2.9-preparation metadata: selected source, selected import ids, counts, control totals."""
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    source = await get_financial_source(db, company_id, workspace_id)
    account_count = await db.accounts.count_documents({"workspace_id": workspace_id, "company_id": company_id})
    out = {"company_id": company_id, "source": source, "default": DEFAULT_SOURCE,
           "normalized_available": {"account_count": account_count}}
    tb_imp = await _latest_completed_import(db, workspace_id, company_id, "trial_balance", financial_period_id)
    je_imp = await _latest_completed_import(db, workspace_id, company_id, "journal", financial_period_id)
    if financial_period_id:
        out["financial_period_id"] = financial_period_id
    out["selected_trial_balance_import_id"] = tb_imp["_id"] if tb_imp else None
    out["selected_journal_import_id"] = je_imp["_id"] if je_imp else None
    if tb_imp:
        tb = await _TB_ADAPTER.read(db, company_id, workspace_id, tb_imp["financial_period_id"])
        out["trial_balance_controls"] = tb["controls"]
    if je_imp:
        je = await _JOURNAL_ADAPTER.read(db, company_id, workspace_id, je_imp["financial_period_id"])
        out["journal_controls"] = je["controls"]
    return out


async def ensure_indexes(db) -> None:
    await db.financial_config.create_index(
        [("workspace_id", 1), ("company_id", 1)], unique=True, name="uniq_financial_config_company")
