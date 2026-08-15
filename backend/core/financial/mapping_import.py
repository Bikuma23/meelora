"""P3.3 — Excel/CSV mapping import (preview → validate → commit).

Preview performs NO writes. Commit defaults to creating SUGGESTED mappings
(source=excel); confirmed import is an explicit workspace-admin action that
requires every row to pass full validation and never silently supersedes a
confirmed mapping. Idempotent: re-committing identical suggested rows is a
no-op. Parsing is separated from logic so the governance rules are unit-tested
in-memory without file IO.
"""
import csv
import io
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from ..permissions import require_company_admin, require_tenant_context
from .concepts import ACTIVE as CONCEPT_ACTIVE
from .mappings import MappingCreate, create_mapping, SUGGESTED, CONFIRMED

_COLUMNS = ["account_code", "concept_code", "status", "effective_from_period",
            "effective_to_period", "confidence", "notes"]


class ImportCommit(BaseModel):
    rows: list[dict]
    as_confirmed: bool = False


def parse_rows(content: bytes, filename: str) -> list[dict]:
    name = (filename or "").lower()
    rows = []
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(text)):
            rows.append({k: (str(v).strip() if v not in (None, "") else None) for k, v in r.items()})
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        ws = wb.active
        header = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                header = [str(c).strip() if c is not None else "" for c in row]
                continue
            if all(c is None for c in row):
                continue
            d = {}
            for i, h in enumerate(header):
                v = row[i] if i < len(row) else None
                d[h] = str(v).strip() if v not in (None, "") else None
            rows.append(d)
        wb.close()
    else:
        raise HTTPException(status_code=422, detail="Format non supporté (utilisez .csv ou .xlsx)")
    return rows


async def _resolve_period_code(db, ws, cid, code, cache):
    if code in cache:
        return cache[code]
    p = await db.financial_periods.find_one({"workspace_id": ws, "company_id": cid, "period_code": code})
    cache[code] = p
    return p


async def _default_from_period(db, ws, cid):
    periods = await db.financial_periods.find({"workspace_id": ws, "company_id": cid}).to_list(None)
    if not periods:
        return None
    return min(periods, key=lambda d: d.get("sequence") or 0)


async def import_preview(db, company_id, user, rows: list[dict]) -> dict:
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    accounts = await db.accounts.find({"workspace_id": ws, "company_id": company_id, "active": True}).to_list(None)
    acc_by_code = {a.get("account_code"): a for a in accounts}
    pcache = {}
    default_from = await _default_from_period(db, ws, company_id)

    valid, warnings, errors, existing_affected = [], [], [], []
    seen_accounts = {}
    for idx, raw in enumerate(rows):
        acc_code = raw.get("account_code")
        concept_code = raw.get("concept_code")
        line = {"index": idx, "account_code": acc_code, "concept_code": concept_code}
        row_errors = []
        if not acc_code:
            row_errors.append("account_code manquant")
        if not concept_code:
            row_errors.append("concept_code manquant")
        acc = acc_by_code.get(acc_code) if acc_code else None
        if acc_code and not acc:
            row_errors.append(f"compte inconnu/inactif: {acc_code}")
        concept = None
        if concept_code:
            concept = await db.financial_concepts.find_one({"concept_code": concept_code})
            if not concept:
                row_errors.append(f"concept inconnu: {concept_code}")
            elif concept.get("status") != CONCEPT_ACTIVE:
                row_errors.append(f"concept inactif: {concept_code}")
            elif concept.get("is_aggregate"):
                row_errors.append(f"concept agrégat non mappable: {concept_code}")
        # period resolution
        from_pid = None
        fp_code = raw.get("effective_from_period")
        if fp_code:
            fp = await _resolve_period_code(db, ws, company_id, fp_code, pcache)
            if not fp:
                row_errors.append(f"période from inconnue: {fp_code}")
            else:
                from_pid = fp["_id"]
        elif default_from:
            from_pid = default_from["_id"]
        else:
            row_errors.append("aucune période disponible pour effective_from")
        to_pid = None
        tp_code = raw.get("effective_to_period")
        if tp_code:
            tp = await _resolve_period_code(db, ws, company_id, tp_code, pcache)
            if not tp:
                row_errors.append(f"période to inconnue: {tp_code}")
            else:
                to_pid = tp["_id"]
        # duplicate / conflicting account rows within the file
        if acc_code and acc_code in seen_accounts:
            if seen_accounts[acc_code] != concept_code:
                row_errors.append(f"affectation de concept conflictuelle pour {acc_code} dans le fichier")
            else:
                warnings.append({"index": idx, "warning": f"ligne dupliquée pour {acc_code}"})
        if acc_code:
            seen_accounts[acc_code] = concept_code
        # existing confirmed mapping affected (informational)
        if acc and not row_errors:
            existing_conf = await db.account_mappings.find_one({
                "workspace_id": ws, "company_id": company_id, "account_id": acc["_id"],
                "status": CONFIRMED, "superseded": {"$ne": True}})
            if existing_conf:
                existing_affected.append({"index": idx, "account_code": acc_code,
                                          "existing_mapping_id": existing_conf["_id"]})
        if row_errors:
            errors.append({**line, "errors": row_errors})
        else:
            valid.append({**line, "account_id": acc["_id"], "financial_concept_id": concept["_id"],
                          "effective_from_period_id": from_pid, "effective_to_period_id": to_pid,
                          "confidence": raw.get("confidence"), "notes": raw.get("notes")})
    return {"company_id": company_id, "summary": {"valid": len(valid), "warnings": len(warnings),
            "errors": len(errors), "existing_confirmed_affected": len(existing_affected)},
            "valid_rows": valid, "warnings": warnings, "errors": errors,
            "existing_affected": existing_affected}


async def import_commit(db, company_id, user, rows: list[dict], as_confirmed: bool = False) -> dict:
    await require_company_admin(db, company_id, user)
    ws = require_tenant_context(user)
    preview = await import_preview(db, company_id, user, rows)
    if preview["errors"]:
        raise HTTPException(status_code=422, detail={
            "message": "Import bloqué: des lignes contiennent des erreurs",
            "errors": preview["errors"]})
    target_status = CONFIRMED if as_confirmed else SUGGESTED
    created, skipped, errors = [], [], []
    for row in preview["valid_rows"]:
        try:
            if target_status == SUGGESTED:
                dup = await db.account_mappings.find_one({
                    "workspace_id": ws, "company_id": company_id, "account_id": row["account_id"],
                    "financial_concept_id": row["financial_concept_id"], "status": SUGGESTED,
                    "effective_from_period_id": row["effective_from_period_id"],
                    "source": "excel", "superseded": {"$ne": True}})
                if dup:
                    skipped.append({"account_code": row["account_code"], "mapping_id": dup["_id"]})
                    continue
            conf = None
            try:
                conf = float(row["confidence"]) if row.get("confidence") is not None else None
            except (TypeError, ValueError):
                conf = None
            rec = await create_mapping(db, company_id, user, MappingCreate(
                account_id=row["account_id"], financial_concept_id=row["financial_concept_id"],
                effective_from_period_id=row["effective_from_period_id"],
                effective_to_period_id=row["effective_to_period_id"],
                source="excel", status=target_status, confidence=conf, notes=row.get("notes")))
            created.append({"account_code": row["account_code"], "mapping_id": rec["id"],
                            "status": target_status})
        except HTTPException as e:
            errors.append({"account_code": row["account_code"], "status_code": e.status_code,
                           "reason": e.detail})
    return {"company_id": company_id, "imported_status": target_status,
            "summary": {"created": len(created), "skipped": len(skipped), "errors": len(errors)},
            "created": created, "skipped": skipped, "errors": errors}
