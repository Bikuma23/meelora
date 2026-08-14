"""Trial Balance import adapter — delegates domain rules to core.financial.trial_balance."""
import uuid
from datetime import datetime, timezone

from ..base import ImportAdapter
from ...trial_balance import (
    parse_trial_balance_file, validate_tb_rows, _resolve_financial_context,
)


class TrialBalanceImportAdapter(ImportAdapter):
    data_type = "trial_balance"
    source_types = None  # unchanged: TB never restricted source_type

    def parse(self, content, file_name):
        return parse_trial_balance_file(content, file_name)

    def idempotency_key(self, workspace_id, company_id, doc_fields, checksum):
        return f"{workspace_id}:{company_id}:trial_balance:{doc_fields.get('financial_period_id')}:{checksum}"

    async def context_fields(self, db, company_id, user, workspace_id, actx):
        fy_id = actx.get("financial_year_id")
        fp_id = actx.get("financial_period_id")
        if not fy_id or not fp_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="financial_year_id et financial_period_id requis")
        await _resolve_financial_context(db, company_id, workspace_id, fy_id, fp_id)
        return {"financial_year_id": fy_id, "financial_period_id": fp_id}, {}

    async def validate(self, db, company, workspace_id, rows, actx, runtime):
        accounts = await db.accounts.find({"workspace_id": workspace_id, "company_id": actx["company_id"]}).to_list(None)
        by_code = {a.get("account_code"): a for a in accounts}
        preview_rows, warnings_flat, controls = validate_tb_rows(rows, company, by_code)
        rejected = sum(1 for p in preview_rows if p["action"] == "reject")
        to_apply = [p for p in preview_rows if p["action"] == "import"]
        balance_errors = []
        if not controls["period_balanced"]:
            balance_errors.append(f"Balance déséquilibrée (période): écart {controls['period_difference']}")
        if not controls["ytd_balanced"]:
            balance_errors.append(f"Balance déséquilibrée (cumul): écart {controls['ytd_difference']}")
        status = "failed" if (rejected or balance_errors) else "valid"
        error_summary = None
        if rejected or balance_errors:
            parts = ([f"{rejected} ligne(s) en erreur"] if rejected else []) + balance_errors
            error_summary = " ; ".join(parts)
        return {
            "status": status, "records_received": len(rows), "records_rejected": rejected,
            "error_summary": error_summary, "warnings": warnings_flat,
            "metadata": {"apply_rows": [p["normalized"] for p in to_apply], "controls": controls},
            "response_extra": {
                "preview_rows": preview_rows, "controls": controls, "balance_errors": balance_errors,
                "counts": {"received": len(rows), "to_import": len(to_apply),
                           "rejected": rejected, "warnings": len(warnings_flat)},
            },
        }

    async def idempotency_noop(self, db, doc, workspace_id):
        existing = await db.trial_balance_lines.find_one({
            "workspace_id": workspace_id, "company_id": doc["company_id"], "import_id": doc["_id"]})
        return {"mode": "already_committed"} if existing else None

    async def write(self, db, doc, user, workspace_id):
        now = datetime.now(timezone.utc).isoformat()
        company_id = doc["company_id"]
        created = 0
        for row in (doc.get("metadata") or {}).get("apply_rows", []):
            line = {
                "_id": f"tbl_{uuid.uuid4().hex}",
                "workspace_id": workspace_id, "company_id": company_id,
                "financial_year_id": doc.get("financial_year_id"),
                "financial_period_id": doc.get("financial_period_id"),
                "import_id": doc["_id"],
                "account_id": row["account_id"], "account_code": row["account_code"],
                "period_debit": row["period_debit"], "period_credit": row["period_credit"], "period_net": row["period_net"],
                "ytd_debit": row["ytd_debit"], "ytd_credit": row["ytd_credit"], "ytd_net": row["ytd_net"],
                "currency": row["currency"], "source_row": row["source_row"],
                "created_at": now, "updated_at": now,
            }
            await db.trial_balance_lines.insert_one(line)
            created += 1
        controls = (doc.get("metadata") or {}).get("controls", {})
        return {"created": created, "updated": 0, "response_extra": {"controls": controls}}
