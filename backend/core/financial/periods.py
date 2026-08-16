"""P2.2 — Financial periods (normalized Financial Core), attached to financial_years.

Monthly periods are the canonical basis for future reporting (no independent
quarterly source of truth). Periods never physically deleted. Authorization
reuses the Phase 1 / P2.1 centralized helpers (no second permission system).
Lock/close state is established here ONLY as normalized period state — it is NOT
propagated to legacy acct_*/qc9434_* write restrictions in P2.2.
"""
from calendar import monthrange
from datetime import datetime, timezone, date
from typing import Literal, Optional, Tuple
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..permissions import require_company_access, require_company_admin, require_tenant_context

PeriodType = Literal["month", "quarter", "adjustment"]
PeriodStatus = Literal["open", "locked", "closed"]

_DATE_FMT = "%Y-%m-%d"

# Explicit allowed status transitions (canonical period state machine, aligned
# with ACCOUNTING A2). ``closed`` is TERMINAL — historical reopening (closed→open)
# is permanently removed/deprecated for everyone; corrections happen via a later
# period. This is the SINGLE source of truth consumed by both the Financial Core
# and the Accounting workflow.
_ALLOWED_TRANSITIONS = {
    "open": {"locked", "closed", "open"},
    "locked": {"open", "closed", "locked"},
    "closed": {"closed"},
}

_FR_MONTHS = ["", "janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


class FinancialPeriodCreate(BaseModel):
    period_code: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    period_type: PeriodType = "month"
    sequence: int = Field(ge=1)
    status: PeriodStatus = "open"


class FinancialPeriodUpdate(BaseModel):
    period_code: Optional[str] = Field(default=None, min_length=1, max_length=40)
    label: Optional[str] = Field(default=None, min_length=1, max_length=80)
    start_date: Optional[str] = Field(default=None, min_length=10, max_length=10)
    end_date: Optional[str] = Field(default=None, min_length=10, max_length=10)
    period_type: Optional[PeriodType] = None
    sequence: Optional[int] = Field(default=None, ge=1)
    status: Optional[PeriodStatus] = None


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, _DATE_FMT).date()
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"Date invalide (attendu AAAA-MM-JJ): {value}")


def public_financial_period(doc: dict) -> dict:
    return {
        "id": doc.get("_id") or doc.get("id"),
        "workspace_id": doc.get("workspace_id"),
        "company_id": doc.get("company_id"),
        "financial_year_id": doc.get("financial_year_id"),
        "period_code": doc.get("period_code"),
        "label": doc.get("label"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "period_type": doc.get("period_type", "month"),
        "sequence": doc.get("sequence"),
        "status": doc.get("status", "open"),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by"),
        "updated_at": doc.get("updated_at"),
    }


async def _load_year_scoped(db, company_id: str, financial_year_id: str, workspace_id: str) -> dict:
    fy = await db.financial_years.find_one({
        "_id": financial_year_id,
        "workspace_id": workspace_id,
        "company_id": company_id,
    })
    if not fy:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    return fy


async def _ensure_code_unique(db, workspace_id, company_id, period_code, exclude_id=None):
    query = {"workspace_id": workspace_id, "company_id": company_id, "period_code": period_code}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if await db.financial_periods.find_one(query):
        raise HTTPException(status_code=409, detail="Ce code de période existe déjà pour cette société")


async def _ensure_sequence_unique(db, workspace_id, company_id, financial_year_id, sequence, exclude_id=None):
    query = {"workspace_id": workspace_id, "company_id": company_id,
             "financial_year_id": financial_year_id, "sequence": sequence}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    if await db.financial_periods.find_one(query):
        raise HTTPException(status_code=409, detail="Ce numéro de séquence existe déjà dans cet exercice")


async def _ensure_no_overlap(db, workspace_id, company_id, financial_year_id, start_s, end_s, exclude_id=None):
    start = _parse_date(start_s)
    end = _parse_date(end_s)
    query = {"workspace_id": workspace_id, "company_id": company_id, "financial_year_id": financial_year_id}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    for row in await db.financial_periods.find(query).to_list(None):
        rs = _parse_date(row.get("start_date"))
        re_ = _parse_date(row.get("end_date"))
        if start <= re_ and rs <= end:
            raise HTTPException(
                status_code=409,
                detail=f"Chevauchement avec la période '{row.get('period_code')}' ({row.get('start_date')} → {row.get('end_date')})",
            )


def _validate_within_year(fy: dict, start_s: str, end_s: str) -> Tuple[str, str]:
    start = _parse_date(start_s)
    end = _parse_date(end_s)
    if start > end:
        raise HTTPException(status_code=422, detail="start_date doit être <= end_date")
    fy_start = _parse_date(fy["start_date"])
    fy_end = _parse_date(fy["end_date"])
    if start < fy_start or end > fy_end:
        raise HTTPException(
            status_code=422,
            detail=f"La période doit être entièrement comprise dans l'exercice ({fy['start_date']} → {fy['end_date']})",
        )
    return start.isoformat(), end.isoformat()


async def list_financial_periods(db, company_id: str, financial_year_id: str, user: dict) -> list[dict]:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    await _load_year_scoped(db, company_id, financial_year_id, workspace_id)
    docs = await db.financial_periods.find({
        "workspace_id": workspace_id,
        "company_id": company_id,
        "financial_year_id": financial_year_id,
    }).to_list(None)
    docs.sort(key=lambda d: (d.get("sequence") or 0, d.get("start_date") or ""))
    return [public_financial_period(d) for d in docs]


async def get_financial_period(db, company_id: str, period_id: str, user: dict) -> dict:
    await require_company_access(db, company_id, user)
    workspace_id = require_tenant_context(user)
    doc = await db.financial_periods.find_one({
        "_id": period_id, "workspace_id": workspace_id, "company_id": company_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Période introuvable")
    return public_financial_period(doc)


async def create_financial_period(db, company_id: str, financial_year_id: str, user: dict, payload: FinancialPeriodCreate) -> dict:
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    fy = await _load_year_scoped(db, company_id, financial_year_id, workspace_id)
    start_s, end_s = _validate_within_year(fy, payload.start_date, payload.end_date)
    code = payload.period_code.strip()
    await _ensure_code_unique(db, workspace_id, company_id, code)
    await _ensure_sequence_unique(db, workspace_id, company_id, financial_year_id, payload.sequence)
    await _ensure_no_overlap(db, workspace_id, company_id, financial_year_id, start_s, end_s)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": f"fp_{uuid.uuid4().hex}",
        "workspace_id": workspace_id,
        "company_id": company_id,
        "financial_year_id": financial_year_id,
        "period_code": code,
        "label": payload.label.strip(),
        "start_date": start_s,
        "end_date": end_s,
        "period_type": payload.period_type,
        "sequence": payload.sequence,
        "status": payload.status,
        "created_at": now,
        "created_by": user.get("id"),
        "updated_at": now,
    }
    await db.financial_periods.insert_one(doc)
    return public_financial_period(doc)


async def update_financial_period(db, company_id: str, period_id: str, user: dict, payload: FinancialPeriodUpdate) -> Tuple[dict, Optional[str]]:
    """Return (public_period, previous_status) — previous_status only when status changed."""
    # Authorization is enforced at the route (P1.13F sensitive-permission guard for
    # status transitions; admin for metadata). Here we only scope to the tenant.
    workspace_id = require_tenant_context(user)
    current = await db.financial_periods.find_one({
        "_id": period_id, "workspace_id": workspace_id, "company_id": company_id,
    })
    if not current:
        raise HTTPException(status_code=404, detail="Période introuvable")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return public_financial_period(current), None

    fy = await _load_year_scoped(db, company_id, current["financial_year_id"], workspace_id)

    if "start_date" in changes or "end_date" in changes:
        new_start = changes.get("start_date", current.get("start_date"))
        new_end = changes.get("end_date", current.get("end_date"))
        new_start, new_end = _validate_within_year(fy, new_start, new_end)
        changes["start_date"] = new_start
        changes["end_date"] = new_end
        await _ensure_no_overlap(db, workspace_id, company_id, current["financial_year_id"], new_start, new_end, exclude_id=period_id)

    if "period_code" in changes:
        changes["period_code"] = changes["period_code"].strip()
        await _ensure_code_unique(db, workspace_id, company_id, changes["period_code"], exclude_id=period_id)

    if "sequence" in changes:
        await _ensure_sequence_unique(db, workspace_id, company_id, current["financial_year_id"], changes["sequence"], exclude_id=period_id)

    prev_status = current.get("status", "open")
    status_changed = "status" in changes and changes["status"] != prev_status
    if status_changed:
        new_status = changes["status"]
        if new_status not in _ALLOWED_TRANSITIONS.get(prev_status, set()):
            raise HTTPException(status_code=409, detail=f"Transition de statut non autorisée: {prev_status} → {new_status}")

    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    changes["updated_by"] = user.get("id")
    await db.financial_periods.update_one(
        {"_id": period_id, "workspace_id": workspace_id, "company_id": company_id},
        {"$set": changes},
    )
    updated = await db.financial_periods.find_one({
        "_id": period_id, "workspace_id": workspace_id, "company_id": company_id,
    })
    return public_financial_period(updated), (prev_status if status_changed else None)


def _iter_year_months(fy_start: date, fy_end: date):
    """Yield (year, month) from fy_start's month up to fy_end's month inclusive."""
    y, m = fy_start.year, fy_start.month
    while (y, m) <= (fy_end.year, fy_end.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


async def generate_monthly_periods(db, company_id: str, financial_year_id: str, user: dict) -> dict:
    """Generate contiguous calendar-month periods covering the financial year.
    Idempotent: existing period_codes are skipped. Rejects non-whole-month FYs."""
    await require_company_admin(db, company_id, user)
    workspace_id = require_tenant_context(user)
    fy = await _load_year_scoped(db, company_id, financial_year_id, workspace_id)
    fy_start = _parse_date(fy["start_date"])
    fy_end = _parse_date(fy["end_date"])

    # Whole-calendar-month alignment is required; do NOT invent a rule otherwise.
    if fy_start.day != 1:
        raise HTTPException(status_code=422, detail="L'exercice ne commence pas au 1er d'un mois — génération mensuelle impossible")
    if fy_end.day != monthrange(fy_end.year, fy_end.month)[1]:
        raise HTTPException(status_code=422, detail="L'exercice ne se termine pas le dernier jour d'un mois — génération mensuelle impossible")

    existing = await db.financial_periods.find({
        "workspace_id": workspace_id, "company_id": company_id, "financial_year_id": financial_year_id,
    }).to_list(None)
    existing_codes = {r.get("period_code") for r in existing}

    now = datetime.now(timezone.utc).isoformat()
    created, skipped, items = 0, 0, []
    seq = 0
    for (y, m) in _iter_year_months(fy_start, fy_end):
        seq += 1
        code = f"{y:04d}-{m:02d}"
        p_start = date(y, m, 1).isoformat()
        p_end = date(y, m, monthrange(y, m)[1]).isoformat()
        if code in existing_codes:
            skipped += 1
            items.append({"period_code": code, "sequence": seq, "created": False})
            continue
        # Guard against overlap with any pre-existing non-generated period.
        await _ensure_no_overlap(db, workspace_id, company_id, financial_year_id, p_start, p_end)
        doc = {
            "_id": f"fp_{uuid.uuid4().hex}",
            "workspace_id": workspace_id,
            "company_id": company_id,
            "financial_year_id": financial_year_id,
            "period_code": code,
            "label": f"{_FR_MONTHS[m].capitalize()} {y}",
            "start_date": p_start,
            "end_date": p_end,
            "period_type": "month",
            "sequence": seq,
            "status": "open",
            "created_at": now,
            "created_by": user.get("id"),
            "updated_at": now,
        }
        await db.financial_periods.insert_one(doc)
        created += 1
        items.append({"period_code": code, "sequence": seq, "created": True})

    return {
        "financial_year_id": financial_year_id,
        "total_months": len(items),
        "created": created,
        "skipped": skipped,
        "periods": items,
    }


async def ensure_indexes(db) -> None:
    await db.financial_periods.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_year_id", 1), ("sequence", 1)],
        unique=True, name="uniq_financial_period_sequence_per_year",
    )
    await db.financial_periods.create_index(
        [("workspace_id", 1), ("company_id", 1), ("period_code", 1)],
        unique=True, name="uniq_financial_period_code_per_company",
    )
    await db.financial_periods.create_index(
        [("workspace_id", 1), ("company_id", 1), ("financial_year_id", 1), ("start_date", 1), ("end_date", 1)],
        name="idx_financial_period_year_dates",
    )
