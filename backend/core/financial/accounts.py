"""P2.3 — Unified Accounts (canonical chart of accounts per company).

account_code is treated as an opaque STRING (leading zeros / punctuation
preserved, never cast to int). Currency defaults to the company's
functional_currency and never mutates it. No physical delete (active flag).
Authorization reuses the Phase 1 centralized helpers. No financial_concept_id
or report-line mapping here (later Reporting Engine phases).
"""
from datetime import datetime, timezone
from typing import Literal, Optional, Tuple
import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import require_company_access, require_company_admin, require_tenant_context

AccountType = Literal["asset", "liability", "equity", "revenue", "expense", "other"]
NormalBalance = Literal["debit", "credit"]

_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


class AccountCreate(BaseModel):
    account_code: str = Field(min_length=1, max_length=40)
    account_name: str = Field(min_length=1, max_length=160)
    account_type: AccountType
    normal_balance: NormalBalance
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    active: bool = True
    source_system: str = Field(default="manual", max_length=40)
    external_id: Optional[str] = Field(default=None, max_length=120)


class AccountUpdate(BaseModel):
    account_code: Optional[str] = Field(default=None, min_length=1, max_length=40)
    account_name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    account_type: Optional[AccountType] = None
    normal_balance: Optional[NormalBalance] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    active: Optional[bool] = None
    source_system: Optional[str] = Field(default=None, max_length=40)
    external_id: Optional[str] = Field(default=None, max_length=120)


def public_account(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "account_code": doc.get("account_code"),
        "account_name": doc.get("account_name"),
        "account_type": doc.get("account_type"),
        "normal_balance": doc.get("normal_balance"),
        "currency": doc.get("currency"),
        "active": doc.get("active", True),
        "source_system": doc.get("source_system", "manual"),
        "external_id": doc.get("external_id"),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by"),
        "updated_at": doc.get("updated_at"),
    }


def _validate_currency(value: str) -> str:
    if not value or not _CURRENCY_RE.match(value):
        raise HTTPException(status_code=422, detail=f"Code devise invalide (attendu 3 lettres ISO): {value}")
    return value.upper()


async def _ensure_code_unique(db, workspace_id, company_id, account_code, exclude_id=None):
    query = {"workspace_id": workspace_id, "company_id": company_id, "account_code": account_code}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if await db.accounts.find_one(query):
        raise HTTPException(status_code=409, detail="Ce code de compte existe déjà pour cette société")


async def _ensure_external_id_unique(db, workspace_id, company_id, source_system, external_id, exclude_id=None):
    if not external_id:
        return
    query = {"workspace_id": workspace_id, "company_id": company_id,
             "source_system": source_system, "external_id": external_id}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if await db.accounts.find_one(query):
        raise HTTPException(status_code=409, detail="external_id déjà utilisé pour cette société et ce système source")


async def list_accounts(db, company_id: str, user: dict,
                        active: Optional[bool] = None,
                        account_type: Optional[str] = None,
                        search: Optional[str] = None) -> list[dict]:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    query: dict = {"workspace_id": workspace_id, "company_id": company_id}
    if active is not None:
        query["active"] = active
    if account_type:
        query["account_type"] = account_type
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"account_code": rx}, {"account_name": rx}]
    docs = await db.accounts.find(query).to_list(None)
    docs.sort(key=lambda d: (d.get("account_code") or ""))
    return [public_account(d) for d in docs]


async def get_account(db, company_id: str, account_id: str, user: dict) -> dict:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    doc = await db.accounts.find_one({"_id": account_id, "workspace_id": workspace_id, "company_id": company_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return public_account(doc)


async def create_account(db, company_id: str, user: dict, payload: AccountCreate) -> dict:
    company = await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    code = payload.account_code.strip()
    if not code:
        raise HTTPException(status_code=422, detail="account_code requis")
    # Currency inherits the company functional currency when omitted; it never
    # mutates the company's functional currency.
    currency = payload.currency or company.get("functional_currency")
    if not currency:
        raise HTTPException(status_code=422, detail="Devise requise (la société n'a pas de devise fonctionnelle)")
    currency = _validate_currency(currency)
    await _ensure_code_unique(db, workspace_id, company_id, code)
    await _ensure_external_id_unique(db, workspace_id, company_id, payload.source_system, payload.external_id)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": f"acc_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "company_id": company_id,
        "account_code": code,
        "account_name": payload.account_name.strip(),
        "account_type": payload.account_type,
        "normal_balance": payload.normal_balance,
        "currency": currency,
        "active": payload.active,
        "source_system": payload.source_system,
        "external_id": payload.external_id,
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
    }
    await db.accounts.insert_one(doc)
    return public_account(doc)


async def update_account(db, company_id: str, account_id: str, user: dict, payload: AccountUpdate) -> Tuple[dict, Optional[bool]]:
    """Return (public_account, active_changed_to) where active_changed_to is
    True/False only when the active flag actually changed (for precise logging)."""
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    current = await db.accounts.find_one({"_id": account_id, "workspace_id": workspace_id, "company_id": company_id})
    if not current:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return public_account(current), None

    if "account_code" in changes:
        changes["account_code"] = changes["account_code"].strip()
        await _ensure_code_unique(db, workspace_id, company_id, changes["account_code"], exclude_id=account_id)
    if "account_name" in changes and changes["account_name"]:
        changes["account_name"] = changes["account_name"].strip()
    if "currency" in changes and changes["currency"] is not None:
        changes["currency"] = _validate_currency(changes["currency"])

    new_source = changes.get("source_system", current.get("source_system"))
    if "external_id" in changes or "source_system" in changes:
        await _ensure_external_id_unique(db, workspace_id, company_id, new_source,
                                         changes.get("external_id", current.get("external_id")),
                                         exclude_id=account_id)

    prev_active = current.get("active", True)
    active_changed = "active" in changes and changes["active"] != prev_active

    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    changes["updated_by"] = user.get("id")
    await db.accounts.update_one(
        {"_id": account_id, "workspace_id": workspace_id, "company_id": company_id},
        {"$set": changes},
    )
    updated = await db.accounts.find_one({"_id": account_id, "workspace_id": workspace_id, "company_id": company_id})
    return public_account(updated), (updated.get("active") if active_changed else None)


async def ensure_indexes(db) -> None:
    await db.accounts.create_index(
        [("workspace_id", 1), ("company_id", 1), ("account_code", 1)],
        unique=True, name="uniq_account_code_per_company",
    )
    await db.accounts.create_index(
        [("workspace_id", 1), ("company_id", 1), ("active", 1)],
        name="idx_account_company_active",
    )
    await db.accounts.create_index(
        [("workspace_id", 1), ("company_id", 1), ("account_type", 1)],
        name="idx_account_company_type",
    )
    # Connector prep: uniqueness of external_id per (company, source) ONLY when present.
    await db.accounts.create_index(
        [("workspace_id", 1), ("company_id", 1), ("source_system", 1), ("external_id", 1)],
        unique=True,
        partialFilterExpression={"external_id": {"$type": "string"}},
        name="uniq_account_external_id_per_source",
    )
