import asyncio, sys
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

env = {}
for line in Path("/app/backend/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"')

WS = "ws_56c492936ea64c4db53a2f14a0825ef5"
CA = "965f0770-8cf2-4199-a99f-819ff270436a"
FP1 = "fp_p33_1"; FP2 = "fp_p33_2"
ACCS = ["acc_p33_a", "acc_p33_b", "acc_p33_c"]

async def cleanup(db):
    await db.financial_periods.delete_many({"_id": {"$in": [FP1, FP2]}})
    await db.accounts.delete_many({"_id": {"$in": ACCS}})
    await db.account_mappings.delete_many({"company_id": CA, "account_id": {"$in": ACCS}})

async def main():
    c = AsyncIOMotorClient(env["MONGO_URL"]); db = c[env["DB_NAME"]]
    await cleanup(db)
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        print("CLEANUP_OK"); c.close(); return
    await db.financial_periods.insert_many([
        {"_id": FP1, "workspace_id": WS, "company_id": CA, "sequence": 1, "period_code": "2099-01", "status": "open"},
        {"_id": FP2, "workspace_id": WS, "company_id": CA, "sequence": 2, "period_code": "2099-02", "status": "open"}])
    await db.accounts.insert_many([
        {"_id": "acc_p33_a", "workspace_id": WS, "company_id": CA, "account_code": "P33-A", "account_name": "Cash", "active": True},
        {"_id": "acc_p33_b", "workspace_id": WS, "company_id": CA, "account_code": "P33-B", "account_name": "Rev", "active": True},
        {"_id": "acc_p33_c", "workspace_id": WS, "company_id": CA, "account_code": "P33-C", "account_name": "Rent", "active": True}])
    print("SEED_OK")
    c.close()

asyncio.run(main())
