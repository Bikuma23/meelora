"""Accounts import adapter — delegates domain rules to core.financial.data_imports."""
from ..base import ImportAdapter
from ...data_imports import (
    parse_accounts_file, validate_accounts_rows, _existing_indexes, _upsert_account,
)


class AccountsImportAdapter(ImportAdapter):
    data_type = "accounts"
    source_types = {"excel", "csv", "api", "manual"}

    def parse(self, content, file_name):
        return parse_accounts_file(content, file_name)

    def idempotency_key(self, workspace_id, company_id, doc_fields, checksum):
        return f"{workspace_id}:{company_id}:accounts:{checksum}"

    async def validate(self, db, company, workspace_id, rows, actx, runtime):
        source_system = actx["source_type"]
        company_id = actx["company_id"]
        by_code, by_ext = await _existing_indexes(db, workspace_id, company_id, source_system)
        preview_rows, warnings_flat = validate_accounts_rows(rows, company, by_code, by_ext)
        rejected = sum(1 for p in preview_rows if p["action"] == "reject")
        to_apply = [p for p in preview_rows if p["action"] in ("create", "update")]
        status = "failed" if rejected else "valid"
        return {
            "status": status,
            "records_received": len(rows),
            "records_rejected": rejected,
            "error_summary": (f"{rejected} ligne(s) en erreur" if rejected else None),
            "warnings": warnings_flat,
            "metadata": {"apply_rows": [p["normalized"] for p in to_apply]},
            "response_extra": {
                "preview_rows": preview_rows,
                "counts": {
                    "received": len(rows),
                    "to_create": sum(1 for p in to_apply if p["action"] == "create"),
                    "to_update": sum(1 for p in to_apply if p["action"] == "update"),
                    "rejected": rejected,
                    "warnings": len(warnings_flat),
                },
            },
        }

    async def idempotency_noop(self, db, doc, workspace_id):
        dup = await db.data_imports.find_one({
            "workspace_id": workspace_id, "company_id": doc["company_id"],
            "idempotency_key": doc.get("idempotency_key"),
            "status": {"$in": ["completed", "completed_with_warnings"]},
            "_id": {"$ne": doc["_id"]},
        })
        if dup:
            return {"mode": "terminal",
                    "warnings_add": [{"warning": f"Source identique déjà importée ({dup['_id']}) — aucune modification"}]}
        return None

    async def write(self, db, doc, user, workspace_id):
        source_system = doc.get("source_system")
        company_id = doc["company_id"]
        created = updated = 0
        for row in (doc.get("metadata") or {}).get("apply_rows", []):
            outcome = await _upsert_account(db, workspace_id, company_id, source_system, row, user.get("id"))
            if outcome == "created":
                created += 1
            else:
                updated += 1
        return {"created": created, "updated": updated}
