"""P2.1 — Financial years (normalized Financial Core).

A financial year belongs to exactly one (workspace, company). It is NOT assumed
to be a calendar year; membership is never derived from ``date.year``. Overlap
is validated application-side. No physical delete. Authorization reuses the
Phase 1 centralized helpers so tenant/company/company_access rules and the
"do not leak existence" (404) behavior are preserved.
"""
from datetime import datetime, timezone, date
from typing import Literal, Optional, Tuple
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import require_company_access, require_company_admin, require_tenant_context

FinancialYearStatus = Literal["open", "closed"]

_DATE_FMT = "%Y-%m-%d"


class FinancialYearCreate(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    status: FinancialYearStatus = "open"


class FinancialYearUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=40)
    start_date: Optional[str] = Field(default=None, min_length=10, max_length=10)
    end_date: Optional[str] = Field(default=None, min_length=10, max_length=10)
    status: Optional[FinancialYearStatus] = None


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, _DATE_FMT).date()
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"Date invalide (attendu AAAA-MM-JJ): {value}")


def public_financial_year(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "label": doc.get("label"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "status": doc.get("status", "open"),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by"),
        "updated_at": doc.get("updated_at"),
    }


def _validate_range(start_s: str, end_s: str) -> Tuple[str, str]:
    start = _parse_date(start_s)
    end = _parse_date(end_s)
    if start > end:
        raise HTTPException(status_code=422, detail="start_date doit être <= end_date")
    return start.isoformat(), end.isoformat()


async def _ensure_label_unique(db, workspace_id: str, company_id: str, label: str, exclude_id: Optional[str] = None):
    query = {"workspace_id": workspace_id, "company_id": company_id, "label": label}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if await db.financial_years.find_one(query):
        raise HTTPException(status_code=409, detail="Ce libellé d'exercice existe déjà pour cette société")


async def _ensure_no_overlap(db, workspace_id: str, company_id: str, start_s: str, end_s: str, exclude_id: Optional[str] = None):
    start = _parse_date(start_s)
    end = _parse_date(end_s)
    query = {"workspace_id": workspace_id, "company_id": company_id}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    existing = await db.financial_years.find(query).to_list(None)
    for row in existing:
        rs = _parse_date(row.get("start_date"))
        re_ = _parse_date(row.get("end_date"))
        # Two closed intervals overlap iff start <= re_ AND rs <= end.
        if start <= re_ and rs <= end:
            raise HTTPException(
                status_code=409,
                detail=f"Chevauchement avec l'exercice '{row.get('label')}' ({row.get('start_date')} → {row.get('end_date')})",
            )


async def list_financial_years(db, company_id: str, user: dict) -> list[dict]:
    # Read: admin (workspace-wide) or assigned user (active company_access). 404 if
    # the company is cross-workspace/nonexistent (require_company_access -> require_same_workspace).
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    docs = await db.financial_years.find({
        "workspace_id": workspace_id,
        "company_id": company_id,
    }).to_list(None)
    docs.sort(key=lambda d: (d.get("start_date") or "", d.get("label") or ""))
    return [public_financial_year(d) for d in docs]


async def get_financial_year(db, company_id: str, financial_year_id: str, user: dict) -> dict:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    doc = await db.financial_years.find_one({
        "_id": financial_year_id,
        "workspace_id": workspace_id,
        "company_id": company_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    return public_financial_year(doc)


async def create_financial_year(db, company_id: str, user: dict, payload: FinancialYearCreate) -> dict:
    # Admin only; company must be in the admin's workspace (404 otherwise).
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    label = payload.label.strip()
    start_s, end_s = _validate_range(payload.start_date, payload.end_date)
    await _ensure_label_unique(db, workspace_id, company_id, label)
    await _ensure_no_overlap(db, workspace_id, company_id, start_s, end_s)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": f"fy_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "company_id": company_id,
        "label": label,
        "start_date": start_s,
        "end_date": end_s,
        "status": payload.status,
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
    }
    await db.financial_years.insert_one(doc)
    return public_financial_year(doc)


async def update_financial_year(db, company_id: str, financial_year_id: str, user: dict, payload: FinancialYearUpdate) -> Tuple[dict, Optional[str]]:
    """Return (public_year, previous_status). previous_status is set only when the
    status actually changed, so the route can log close/reopen precisely."""
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    current = await db.financial_years.find_one({
        "_id": financial_year_id,
        "workspace_id": workspace_id,
        "company_id": company_id,
    })
    if not current:
        raise HTTPException(status_code=404, detail="Exercice introuvable")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return public_financial_year(current), None

    new_start = changes.get("start_date", current.get("start_date"))
    new_end = changes.get("end_date", current.get("end_date"))
    if "start_date" in changes or "end_date" in changes:
        new_start, new_end = _validate_range(new_start, new_end)
        changes["start_date"] = new_start
        changes["end_date"] = new_end
        await _ensure_no_overlap(db, workspace_id, company_id, new_start, new_end, exclude_id=financial_year_id)

    if "label" in changes:
        changes["label"] = changes["label"].strip()
        await _ensure_label_unique(db, workspace_id, company_id, changes["label"], exclude_id=financial_year_id)

    prev_status = current.get("status", "open")
    status_changed = "status" in changes and changes["status"] != prev_status

    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    changes["updated_by"] = user.get("id")
    await db.financial_years.update_one(
        {"_id": financial_year_id, "workspace_id": workspace_id, "company_id": company_id},
        {"$set": changes},
    )
    updated = await db.financial_years.find_one({
        "_id": financial_year_id,
        "workspace_id": workspace_id,
        "company_id": company_id,
    })
    return public_financial_year(updated), (prev_status if status_changed else None)


async def ensure_indexes(db) -> None:
    """P2.1 indexes: logical uniqueness of label per company + date retrieval."""
    await db.financial_years.create_index(
        [("workspace_id", 1), ("company_id", 1), ("label", 1)],
        unique=True,
        name="uniq_financial_year_label_per_company",
    )
    await db.financial_years.create_index(
        [("workspace_id", 1), ("company_id", 1), ("start_date", 1), ("end_date", 1)],
        name="idx_financial_year_company_dates",
    )
