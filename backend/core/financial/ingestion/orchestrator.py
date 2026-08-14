"""Central ingestion orchestrator — the single data_import lifecycle implementation.

Handles authorization dispatch, data_import creation, status transitions,
counters and idempotency guards. Domain validation/normalization/writing is
delegated to the data-type adapter. Behaviour is functionally equivalent to the
former per-module preview/commit functions (P2.4/P2.5/P2.6).
"""
from datetime import datetime, timezone
import uuid

from fastapi import HTTPException

from .base import assert_transition
from ..data_imports import _checksum, public_import


def _now():
    return datetime.now(timezone.utc).isoformat()


async def run_preview(db, adapter, company_id, user, content, file_name, source_type, ctx=None):
    company, workspace_id = await adapter.authorize(db, company_id, user)
    adapter.validate_source_type(source_type)
    actx = {"company_id": company_id, "source_type": source_type, **(ctx or {})}
    doc_fields, runtime = await adapter.context_fields(db, company_id, user, workspace_id, actx)

    checksum = _checksum(content)
    rows = adapter.parse(content, file_name)
    result = await adapter.validate(db, company, workspace_id, rows, actx, runtime)

    now = _now()
    doc = {
        "_id": f"imp_{uuid.uuid4().hex}",
        "workspace_id": workspace_id, "company_id": company_id,
        "source_type": source_type, "data_type": adapter.data_type, "source_system": source_type,
        "file_name": file_name, "file_reference": None,
        "financial_year_id": doc_fields.get("financial_year_id"),
        "financial_period_id": doc_fields.get("financial_period_id"),
        "status": result["status"], "version": 1,
        "records_received": result["records_received"], "records_created": 0, "records_updated": 0,
        "records_rejected": result["records_rejected"],
        "checksum": checksum,
        "idempotency_key": adapter.idempotency_key(workspace_id, company_id, doc_fields, checksum),
        "started_at": now, "completed_at": None,
        "created_by": user.get("id"), "created_at": now, "updated_at": now,
        "error_summary": result.get("error_summary"), "warnings": result.get("warnings", []),
        "metadata": result.get("metadata", {}),
    }
    await db.data_imports.insert_one(doc)
    out = public_import(doc)
    out.update(result.get("response_extra", {}))
    return out


async def run_commit(db, adapter, company_id, user, import_id):
    company, workspace_id = await adapter.authorize(db, company_id, user)
    doc = await db.data_imports.find_one({
        "_id": import_id, "workspace_id": workspace_id, "company_id": company_id,
        "data_type": adapter.data_type})
    if not doc:
        raise HTTPException(status_code=404, detail="Import introuvable")

    status = doc.get("status")
    if status in ("completed", "completed_with_warnings"):
        return {"already_committed": True, **public_import(doc)}
    if status == "failed":
        raise HTTPException(status_code=409, detail="Import en échec — corriger les erreurs bloquantes avant validation")
    if status != "valid":
        raise HTTPException(status_code=409, detail=f"Statut d'import non validable: {status}")

    await adapter.pre_commit(db, doc, workspace_id)

    noop = await adapter.idempotency_noop(db, doc, workspace_id)
    now = _now()
    if noop:
        if noop.get("mode") == "already_committed":
            return {"already_committed": True, **public_import(doc)}
        if noop.get("mode") == "terminal":
            assert_transition(status, "completed_with_warnings")
            warnings = list(doc.get("warnings", [])) + noop.get("warnings_add", [])
            await db.data_imports.update_one({"_id": import_id}, {"$set": {
                "status": "completed_with_warnings", "records_created": 0, "records_updated": 0,
                "completed_at": now, "updated_at": now, "warnings": warnings}})
            doc = await db.data_imports.find_one({"_id": import_id})
            out = public_import(doc)
            out.update(noop.get("response_extra", {}))
            return out

    assert_transition(status, "importing")
    await db.data_imports.update_one({"_id": import_id}, {"$set": {"status": "importing", "updated_at": now}})

    wr = await adapter.write(db, doc, user, workspace_id)
    warnings = list(doc.get("warnings", [])) + wr.get("warnings_add", [])
    final_status = "completed_with_warnings" if warnings else "completed"
    assert_transition("importing", final_status)
    set_fields = {
        "status": final_status, "records_created": wr.get("created", 0),
        "records_updated": wr.get("updated", 0), "completed_at": now, "updated_at": now,
        "warnings": warnings,
    }
    set_fields.update(wr.get("extra_set", {}))
    await db.data_imports.update_one({"_id": import_id}, {"$set": set_fields})
    doc = await db.data_imports.find_one({"_id": import_id})
    out = public_import(doc)
    out.update(wr.get("response_extra", {}))
    return out
