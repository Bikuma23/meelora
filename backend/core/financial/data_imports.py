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


def _cell_str(v) -> str:
    """Stringify a cell WITHOUT losing leading zeros / punctuation for text values.
    Numeric cells are rendered without a trailing .0 for whole numbers."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_accounts_file(content: bytes, file_name: str) -> list[dict]:
    """Parse an Excel/CSV chart-of-accounts into raw string rows.

    Returns a list of {"_row": <1-based data row>, <field>: str}. Raises 400 on
    an unreadable file or a missing account_code/account_name header.
    """
    name = (file_name or "").lower()
    is_csv = name.endswith(".csv") or (not name.endswith((".xlsx", ".xls")) and b"," in content[:200] and b"PK" not in content[:4])

    rows: list[dict] = []
    if is_csv:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        reader = list(_csv.reader(io.StringIO(text)))
        if not reader:
            raise HTTPException(status_code=400, detail="Fichier vide")
        header_map = {i: _norm_header(h) for i, h in enumerate(reader[0])}
        data_rows = reader[1:]
        for idx, raw in enumerate(data_rows, start=2):
            if not any((c or "").strip() for c in raw):
                continue
            row = {"_row": idx}
            for i, field in header_map.items():
                if field and i < len(raw):
                    row[field] = (raw[i] or "").strip()
            rows.append(row)
    else:
        import openpyxl
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
        header_map = {i: _norm_header(h) for i, h in enumerate(header)}
        for idx, raw in enumerate(it, start=2):
            if raw is None or not any(c is not None and str(c).strip() for c in raw):
                continue
            row = {"_row": idx}
            for i, field in header_map.items():
                if field and i < len(raw):
                    row[field] = _cell_str(raw[i])
            rows.append(row)

    fields_present = set().union(*(set(r.keys()) for r in rows)) if rows else set()
    header_fields = set(v for v in header_map.values() if v)
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
    company = await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    if source_type not in _VALID_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=f"source_type invalide: {source_type}")

    checksum = _checksum(content)
    idempotency_key = f"{workspace_id}:{company_id}:accounts:{checksum}"
    now = datetime.now(timezone.utc).isoformat()
    source_system = source_type

    rows = parse_accounts_file(content, file_name)
    by_code, by_ext = await _existing_indexes(db, workspace_id, company_id, source_system)
    preview_rows, warnings_flat = validate_accounts_rows(rows, company, by_code, by_ext)

    rejected = sum(1 for p in preview_rows if p["action"] == "reject")
    to_apply = [p for p in preview_rows if p["action"] in ("create", "update")]
    status = "failed" if rejected else "valid"

    doc = {
        "_id": f"imp_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "company_id": company_id,
        "source_type": source_type,
        "data_type": "accounts",
        "source_system": source_system,
        "file_name": file_name,
        "file_reference": None,
        "financial_year_id": None,
        "financial_period_id": None,
        "status": status,
        "version": 1,
        "records_received": len(rows),
        "records_created": 0,
        "records_updated": 0,
        "records_rejected": rejected,
        "checksum": checksum,
        "idempotency_key": idempotency_key,
        "started_at": now,
        "completed_at": None,
        "created_by": user.get("id"),
        "created_at": now,
        "updated_at": now,
        "error_summary": (f"{rejected} ligne(s) en erreur" if rejected else None),
        "warnings": warnings_flat,
        "metadata": {"apply_rows": [p["normalized"] for p in to_apply]},
    }
    await db.data_imports.insert_one(doc)

    result = public_import(doc)
    result["preview_rows"] = preview_rows
    result["counts"] = {
        "received": len(rows),
        "to_create": sum(1 for p in to_apply if p["action"] == "create"),
        "to_update": sum(1 for p in to_apply if p["action"] == "update"),
        "rejected": rejected,
        "warnings": len(warnings_flat),
    }
    return result


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
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    doc = await db.data_imports.find_one({"_id": import_id, "workspace_id": workspace_id, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Import introuvable")

    # Already committed → idempotent no-op.
    if doc.get("status") in ("completed", "completed_with_warnings"):
        return {"already_committed": True, **public_import(doc)}
    if doc.get("status") == "failed":
        raise HTTPException(status_code=409, detail="Import en échec — corriger les erreurs bloquantes avant validation")
    if doc.get("status") != "valid":
        raise HTTPException(status_code=409, detail=f"Statut d'import non validable: {doc.get('status')}")

    now = datetime.now(timezone.utc).isoformat()
    warnings = list(doc.get("warnings", []))

    # Same-source idempotency: an identical source already fully imported → safe no-op.
    dup = await db.data_imports.find_one({
        "workspace_id": workspace_id, "company_id": company_id,
        "idempotency_key": doc.get("idempotency_key"),
        "status": {"$in": ["completed", "completed_with_warnings"]},
        "_id": {"$ne": import_id},
    })
    if dup:
        warnings.append({"warning": f"Source identique déjà importée ({dup['_id']}) — aucune modification"})
        await db.data_imports.update_one({"_id": import_id}, {"$set": {
            "status": "completed_with_warnings", "records_created": 0, "records_updated": 0,
            "completed_at": now, "updated_at": now, "warnings": warnings,
        }})
        doc = await db.data_imports.find_one({"_id": import_id})
        return public_import(doc)

    await db.data_imports.update_one({"_id": import_id}, {"$set": {"status": "importing", "updated_at": now}})

    source_system = doc.get("source_system")
    created = updated = 0
    apply_rows = (doc.get("metadata") or {}).get("apply_rows", [])
    for row in apply_rows:
        outcome = await _upsert_account(db, workspace_id, company_id, source_system, row, user.get("id"))
        if outcome == "created":
            created += 1
        else:
            updated += 1

    final_status = "completed_with_warnings" if warnings else "completed"
    await db.data_imports.update_one({"_id": import_id}, {"$set": {
        "status": final_status, "records_created": created, "records_updated": updated,
        "completed_at": now, "updated_at": now, "warnings": warnings,
    }})
    doc = await db.data_imports.find_one({"_id": import_id})
    return public_import(doc)


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
