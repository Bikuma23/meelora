"""P2.4 — Data Imports registry & import lifecycle (canonical ingestion audit trail).

This layer records every financial data ingestion (accounts now; trial_balance /
transactions / journal / api later) as an immutable-ish audit record in the
``data_imports`` collection. Only the ``accounts`` data type is fully connected
in P2.4 (preview + commit → normalized ``accounts`` from P2.3). Preview never
writes accounts; commit applies idempotent upserts and is safe against double
submission. Authorization reuses the P1.12 centralized helpers; structural
imports follow the SAME policy as P2.3 (workspace admin only).
"""
from datetime import datetime, timezone
from typing import Literal, Optional
import csv as _csv
import hashlib
import io
import uuid

from fastapi import HTTPException
from pydantic import BaseModel

from ..permissions import require_company_access, require_company_admin, require_tenant_context
from .accounts import (
    _CURRENCY_RE, _validate_currency, public_account,
)
from .ingestion.readers import read_tabular, _cell_str  # noqa: F401 (re-exported for TB/journal)

SourceType = Literal["excel", "csv", "api", "manual"]
DataType = Literal["accounts", "trial_balance", "transactions", "journal"]

_VALID_SOURCE_TYPES = {"excel", "csv", "api", "manual"}
_VALID_DATA_TYPES = {"accounts", "trial_balance", "transactions", "journal"}
_VALID_STATUSES = {
    "pending", "validating", "valid", "importing",
    "completed", "completed_with_warnings", "failed",
}
_ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense", "other"}
_NORMAL_BALANCES = {"debit", "credit"}

# Header aliases (case-insensitive) for the accounts chart-of-accounts file.
_HEADER_ALIASES = {
    "account_code": {"account_code", "account code", "code", "compte", "no compte", "n° compte", "numero", "numéro"},
    "account_name": {"account_name", "account name", "name", "nom", "libelle", "libellé", "description"},
    "account_type": {"account_type", "account type", "type"},
    "normal_balance": {"normal_balance", "normal balance", "solde normal", "balance", "sens"},
    "currency": {"currency", "devise"},
    "external_id": {"external_id", "external id", "id externe", "id_externe"},
}


class CommitRequest(BaseModel):
    import_id: str


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def public_import(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "source_type": doc.get("source_type"),
        "data_type": doc.get("data_type"),
        "source_system": doc.get("source_system"),
        "file_name": doc.get("file_name"),
        "file_reference": doc.get("file_reference"),
        "financial_year_id": doc.get("financial_year_id"),
        "financial_period_id": doc.get("financial_period_id"),
        "status": doc.get("status"),
        "version": doc.get("version", 1),
        "records_received": doc.get("records_received", 0),
        "records_created": doc.get("records_created", 0),
        "records_updated": doc.get("records_updated", 0),
        "records_rejected": doc.get("records_rejected", 0),
        "checksum": doc.get("checksum"),
        "idempotency_key": doc.get("idempotency_key"),
        "started_at": doc.get("started_at"),
        "completed_at": doc.get("completed_at"),
        "created_by": doc.get("created_by"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "error_summary": doc.get("error_summary"),
        "warnings": doc.get("warnings", []),
        "metadata": doc.get("metadata", {}),
    }


# ---- Parsing --------------------------------------------------------------
def _norm_header(h) -> Optional[str]:
    if h is None:
        return None
    key = str(h).strip().lower()
    for field, aliases in _HEADER_ALIASES.items():
        if key in aliases:
            return field
    return None


def parse_accounts_file(content: bytes, file_name: str) -> list[dict]:
    """Parse an Excel/CSV chart-of-accounts into raw string rows (P2.7 shared reader).

    Returns a list of {"_row": <1-based data row>, <field>: str}. Raises 400 on
    an unreadable file or a missing account_code/account_name header.
    """
    rows, header_fields = read_tabular(content, file_name, _norm_header)
    if "account_code" not in header_fields or "account_name" not in header_fields:
        raise HTTPException(status_code=400, detail="Colonnes requises manquantes : account_code et account_name")
    return rows


# ---- Validation -----------------------------------------------------------
def validate_accounts_rows(rows: list[dict], company: dict, existing_by_code: dict,
                           existing_by_ext: dict) -> tuple[list[dict], list[dict]]:
    """Return (preview_rows, warnings_flat).

    preview_rows: one entry per data row with action create|update|reject +
    per-row errors/warnings. Duplicate codes within the file with CONFLICTING
    data are blocking; identical duplicates are deduped with a warning.
    """
    functional_currency = company.get("functional_currency")
    seen: dict[str, dict] = {}
    preview: list[dict] = []
    warnings_flat: list[dict] = []

    for r in rows:
        rownum = r.get("_row")
        code = (r.get("account_code") or "").strip()
        name = (r.get("account_name") or "").strip()
        atype = (r.get("account_type") or "").strip().lower()
        nb = (r.get("normal_balance") or "").strip().lower()
        currency_raw = (r.get("currency") or "").strip()
        external_id = (r.get("external_id") or "").strip() or None

        errors: list[str] = []
        rwarn: list[str] = []

        if not code:
            errors.append("account_code manquant")
        if not name:
            errors.append("account_name manquant")
        if atype and atype not in _ACCOUNT_TYPES:
            errors.append(f"account_type invalide: {atype}")
        elif not atype:
            errors.append("account_type manquant")
        if nb and nb not in _NORMAL_BALANCES:
            errors.append(f"normal_balance invalide: {nb}")
        elif not nb:
            errors.append("normal_balance manquant")

        currency = currency_raw or functional_currency
        if currency and not _CURRENCY_RE.match(currency):
            errors.append(f"devise invalide: {currency}")
        elif not currency:
            errors.append("devise absente et société sans devise fonctionnelle")
        if not currency_raw and currency:
            rwarn.append("Devise omise — héritée de la société")
        if not external_id:
            rwarn.append("external_id absent")

        normalized = {
            "account_code": code, "account_name": name, "account_type": atype,
            "normal_balance": nb, "currency": (currency.upper() if currency else None),
            "external_id": external_id,
        }

        # In-file duplicate detection (conflicting = blocking; identical = dedupe).
        if code and code in seen:
            prev = seen[code]["normalized"]
            conflict = any(prev.get(k) != normalized.get(k)
                           for k in ("account_name", "account_type", "normal_balance", "currency", "external_id"))
            if conflict:
                errors.append(f"code dupliqué en conflit dans le fichier (ligne {seen[code]['row']})")
            else:
                rwarn.append("ligne dupliquée identique — ignorée")
                preview.append({"row": rownum, "account_code": code, "action": "skip",
                                "warnings": rwarn, "errors": []})
                continue

        # Existing-account detection → update warning.
        action = "create"
        if not errors:
            match = (existing_by_ext.get((external_id,)) if external_id else None) or existing_by_code.get(code)
            if match:
                action = "update"
                rwarn.append("compte existant — sera mis à jour")

        if errors:
            action = "reject"
        if code:
            seen[code] = {"row": rownum, "normalized": normalized}

        preview.append({"row": rownum, "account_code": code, "action": action,
                        "warnings": rwarn, "errors": errors, "normalized": normalized})
        for w in rwarn:
            warnings_flat.append({"row": rownum, "account_code": code, "warning": w})

    return preview, warnings_flat


# ---- Lifecycle: preview ---------------------------------------------------
async def _existing_indexes(db, workspace_id, company_id, source_system):
    docs = await db.accounts.find({"workspace_id": workspace_id, "company_id": company_id}).to_list(None)
    by_code = {d.get("account_code"): d for d in docs}
    by_ext = {(d.get("external_id"),): d for d in docs
              if d.get("external_id") and d.get("source_system") == source_system}
    return by_code, by_ext


async def preview_accounts_import(db, company_id: str, user: dict, content: bytes,
                                  file_name: str, source_type: str = "excel") -> dict:
    from .ingestion.orchestrator import run_preview
    from .ingestion.registry import get_adapter
    return await run_preview(db, get_adapter("accounts"), company_id, user, content, file_name, source_type)


# ---- Lifecycle: commit ----------------------------------------------------
async def _upsert_account(db, workspace_id, company_id, source_system, row, actor_id) -> str:
    """Idempotent upsert → return 'created' | 'updated'."""
    ext = row.get("external_id")
    now = datetime.now(timezone.utc).isoformat()
    match = None
    if ext:
        match = await db.accounts.find_one({
            "workspace_id": workspace_id, "company_id": company_id,
            "source_system": source_system, "external_id": ext,
        })
    if not match:
        match = await db.accounts.find_one({
            "workspace_id": workspace_id, "company_id": company_id,
            "account_code": row["account_code"],
        })
    payload = {
        "account_code": row["account_code"],
        "account_name": row["account_name"],
        "account_type": row["account_type"],
        "normal_balance": row["normal_balance"],
        "currency": _validate_currency(row["currency"]),
        "external_id": ext,
        "source_system": source_system,
    }
    if match:
        payload["updated_at"] = now
        payload["updated_by"] = actor_id
        await db.accounts.update_one({"_id": match["_id"]}, {"$set": payload})
        return "updated"
    doc = {"_id": f"acc_{uuid.uuid4().hex}", "workspace_id": workspace_id,
           "company_id": company_id, "active": True,
           "created_at": now, "created_by": actor_id, "updated_at": now, **payload}
    await db.accounts.insert_one(doc)
    return "created"


async def commit_accounts_import(db, company_id: str, user: dict, import_id: str) -> dict:
    from .ingestion.orchestrator import run_commit
    from .ingestion.registry import get_adapter
    return await run_commit(db, get_adapter("accounts"), company_id, user, import_id)


# ---- History --------------------------------------------------------------
async def list_imports(db, company_id: str, user: dict, data_type: Optional[str] = None,
                       source_type: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    query: dict = {"workspace_id": workspace_id, "company_id": company_id}
    if data_type:
        query["data_type"] = data_type
    if source_type:
        query["source_type"] = source_type
    if status:
        query["status"] = status
    docs = await db.data_imports.find(query).to_list(None)
    docs.sort(key=lambda d: (d.get("created_at") or ""), reverse=True)
    return [public_import(d) for d in docs]


async def get_import(db, company_id: str, import_id: str, user: dict) -> dict:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    doc = await db.data_imports.find_one({"_id": import_id, "workspace_id": workspace_id, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Import introuvable")
    return public_import(doc)


async def ensure_indexes(db) -> None:
    await db.data_imports.create_index(
        [("workspace_id", 1), ("company_id", 1), ("created_at", -1)],
        name="idx_import_company_created",
    )
    await db.data_imports.create_index(
        [("workspace_id", 1), ("company_id", 1), ("status", 1)],
        name="idx_import_company_status",
    )
    await db.data_imports.create_index(
        [("workspace_id", 1), ("company_id", 1), ("data_type", 1)],
        name="idx_import_company_data_type",
    )
    # Non-unique: legitimate re-imports of CHANGED data must remain possible.
    await db.data_imports.create_index([("idempotency_key", 1)], name="idx_import_idempotency")
