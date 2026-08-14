"""Journal import adapter — delegates domain rules to core.financial.journal."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from ..base import ImportAdapter
from ...trial_balance import _resolve_financial_context
from ...journal import (
    parse_journal_file, validate_journal_rows, _check_period_open,
)


class JournalImportAdapter(ImportAdapter):
    data_type = "journal"
    source_types = None

    def parse(self, content, file_name):
        return parse_journal_file(content, file_name)

    def idempotency_key(self, workspace_id, company_id, doc_fields, checksum):
        return f"{workspace_id}:{company_id}:journal:{doc_fields.get('financial_period_id')}:{checksum}"

    async def context_fields(self, db, company_id, user, workspace_id, actx):
        fy_id = actx.get("financial_year_id")
        fp_id = actx.get("financial_period_id")
        if not fy_id or not fp_id:
            raise HTTPException(status_code=422, detail="financial_year_id et financial_period_id requis")
        _fy, fp = await _resolve_financial_context(db, company_id, workspace_id, fy_id, fp_id)
        _check_period_open(fp)  # open period only for NEW normalized journal writes
        return {"financial_year_id": fy_id, "financial_period_id": fp_id}, {"period": fp}

    async def validate(self, db, company, workspace_id, rows, actx, runtime):
        fp = runtime["period"]
        accounts = await db.accounts.find({"workspace_id": workspace_id, "company_id": actx["company_id"]}).to_list(None)
        by_code = {a.get("account_code"): a for a in accounts}
        entries_preview, warnings_flat, controls = validate_journal_rows(rows, company, by_code, fp)
        rejected = sum(1 for e in entries_preview if e["action"] == "reject")
        to_apply = [e for e in entries_preview if e["action"] == "import"]
        status = "failed" if rejected else "valid"
        return {
            "status": status, "records_received": len(rows), "records_rejected": rejected,
            "error_summary": (f"{rejected} écriture(s) en erreur" if rejected else None),
            "warnings": warnings_flat,
            "metadata": {"apply_entries": [
                {"entry_id": e["entry_id"], "entry_date": e["entry_date"], "reference": e["reference"],
                 "description": e["description"], "external_entry_id": e["external_entry_id"],
                 "lines": e["lines"]} for e in to_apply],
                "controls": controls},
            "response_extra": {
                "entries_preview": entries_preview, "controls": controls,
                "counts": {"received": len(rows), "entries_to_import": len(to_apply),
                           "rejected": rejected, "warnings": len(warnings_flat)},
            },
        }

    async def pre_commit(self, db, doc, workspace_id):
        fp = await db.financial_periods.find_one({
            "_id": doc.get("financial_period_id"), "workspace_id": workspace_id, "company_id": doc["company_id"]})
        if not fp:
            raise HTTPException(status_code=404, detail="Période introuvable")
        _check_period_open(fp)

    async def idempotency_noop(self, db, doc, workspace_id):
        existing = await db.journal_entries.find_one({
            "workspace_id": workspace_id, "company_id": doc["company_id"], "import_id": doc["_id"]})
        return {"mode": "already_committed"} if existing else None

    async def write(self, db, doc, user, workspace_id):
        now = datetime.now(timezone.utc).isoformat()
        company_id = doc["company_id"]
        entry_count = line_count = 0
        for e in (doc.get("metadata") or {}).get("apply_entries", []):
            je_id = f"je_{uuid.uuid4().hex}"
            await db.journal_entries.insert_one({
                "_id": je_id, "workspace_id": workspace_id, "company_id": company_id,
                "financial_year_id": doc.get("financial_year_id"),
                "financial_period_id": doc.get("financial_period_id"), "import_id": doc["_id"],
                "entry_date": e["entry_date"], "reference": e.get("reference"), "description": e.get("description"),
                "source_type": doc.get("source_type"), "source_system": doc.get("source_system"),
                "external_id": e.get("external_entry_id"), "status": "posted",
                "created_at": now, "created_by": user.get("id"), "updated_at": now})
            entry_count += 1
            for ln in e["lines"]:
                await db.journal_entry_lines.insert_one({
                    "_id": f"jel_{uuid.uuid4().hex}", "workspace_id": workspace_id, "company_id": company_id,
                    "journal_entry_id": je_id, "account_id": ln["account_id"], "account_code": ln["account_code"],
                    "line_number": ln["line_number"], "description": ln.get("description"),
                    "debit": ln["debit"], "credit": ln["credit"], "net": ln["net"],
                    "currency": ln["currency"], "external_line_id": ln.get("external_line_id"),
                    "source_row": ln.get("source_row"), "created_at": now, "updated_at": now})
                line_count += 1
        controls = (doc.get("metadata") or {}).get("controls", {})
        return {
            "created": entry_count, "updated": 0,
            "extra_set": {"metadata": {**(doc.get("metadata") or {}), "committed_line_count": line_count}},
            "response_extra": {"entry_count": entry_count, "line_count": line_count, "controls": controls},
        }
