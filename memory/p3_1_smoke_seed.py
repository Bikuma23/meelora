import asyncio, sys
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

env = {}
for line in Path("/app/backend/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"')

WS = "ws_56c492936ea64c4db53a2f14a0825ef5"
CA = "965f0770-8cf2-4199-a99f-819ff270436a"
FP = "fp_p31_smoke"; ACC = "acc_p31_smoke"; FC = "fc_p31_cash"; FCA = "fc_p31_assets"

async def cleanup(db):
    await db.financial_periods.delete_many({"_id": FP})
    await db.accounts.delete_many({"_id": ACC})
    await db.financial_concepts.delete_many({"_id": {"$in": [FC, FCA]}})
    await db.account_mappings.delete_many({"company_id": CA, "account_id": ACC})
    await db.reporting_templates.delete_many({"template_code": {"$in": ["P31_CUSTOM_PL"]}})
    # template lines cleaned by template_id lookup
    tpls = ["P31_CUSTOM_PL"]
    await db.reporting_template_lines.delete_many({"template_id": {"$regex": "^rt_"}, "line_code": "P31_LINE"})

async def main():
    c = AsyncIOMotorClient(env["MONGO_URL"]); db = c[env["DB_NAME"]]
    await cleanup(db)
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        print("CLEANUP_OK"); c.close(); return
    await db.financial_periods.insert_one({"_id": FP, "workspace_id": WS, "company_id": CA, "sequence": 1, "status": "open"})
    await db.accounts.insert_one({"_id": ACC, "workspace_id": WS, "company_id": CA, "account_code": "P31-10", "account_name": "Smoke Cash", "active": True, "account_type": "asset", "normal_balance": "debit", "currency": "CAD"})
    await db.financial_concepts.insert_one({"_id": FCA, "concept_code": "P31_ASSETS", "concept_type": "asset", "statement_type": "balance_sheet", "natural_balance": "debit", "parent_concept_id": None, "cash_flow_category": "none", "is_aggregate": True, "level": 0, "sort_order": 0, "tags": [], "scope": "system", "version": 1, "status": "active", "replaced_by_concept_id": None})
    await db.financial_concepts.insert_one({"_id": FC, "concept_code": "P31_CASH", "concept_type": "asset", "statement_type": "balance_sheet", "natural_balance": "debit", "parent_concept_id": FCA, "cash_flow_category": "operating", "is_aggregate": False, "level": 1, "sort_order": 1, "tags": [], "scope": "system", "version": 1, "status": "active", "replaced_by_concept_id": None})
    print("SEED_OK", FC, ACC, FP)
    c.close()

asyncio.run(main())
