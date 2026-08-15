import asyncio, sys
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
env={}
for l in Path("/app/backend/.env").read_text().splitlines():
    if "=" in l and not l.strip().startswith("#"):
        k,v=l.split("=",1); env[k.strip()]=v.strip().strip('"')
WS="ws_56c492936ea64c4db53a2f14a0825ef5"; CA="965f0770-8cf2-4199-a99f-819ff270436a"
FY="fy_p34"; FP="fp_p34"; IMP="imp_p34"
ACCS=[("a_p34_cash","fc_cash_and_cash_equivalents",700),("a_p34_ap","fc_accounts_payable",-200),
      ("a_p34_sc","fc_share_capital",-300),("a_p34_cyr","fc_current_year_result",-200),
      ("a_p34_rev","fc_operating_revenue",-500),("a_p34_cogs","fc_cost_of_goods_sold",300)]
async def cleanup(db):
    await db.financial_years.delete_many({"_id":FY}); await db.financial_periods.delete_many({"_id":FP})
    await db.data_imports.delete_many({"_id":IMP})
    ids=[a[0] for a in ACCS]
    await db.accounts.delete_many({"_id":{"$in":ids}})
    await db.trial_balance_lines.delete_many({"import_id":IMP})
    await db.account_mappings.delete_many({"account_id":{"$in":ids}})
    await db.report_runs.delete_many({"financial_period_id":FP})
async def main():
    c=AsyncIOMotorClient(env["MONGO_URL"]); db=c[env["DB_NAME"]]
    await cleanup(db)
    if len(sys.argv)>1 and sys.argv[1]=="cleanup": print("CLEANUP_OK"); c.close(); return
    await db.financial_years.insert_one({"_id":FY,"workspace_id":WS,"company_id":CA,"label":"2099","status":"open"})
    await db.financial_periods.insert_one({"_id":FP,"workspace_id":WS,"company_id":CA,"financial_year_id":FY,"sequence":1,"period_code":"2099-01","status":"open"})
    await db.data_imports.insert_one({"_id":IMP,"workspace_id":WS,"company_id":CA,"data_type":"trial_balance","financial_period_id":FP,"status":"completed","completed_at":"2099-02-01"})
    for aid,cid,net in ACCS:
        await db.accounts.insert_one({"_id":aid,"workspace_id":WS,"company_id":CA,"account_code":aid,"account_name":aid,"active":True})
        await db.trial_balance_lines.insert_one({"_id":f"tbl_{aid}","workspace_id":WS,"company_id":CA,"import_id":IMP,"account_id":aid,"account_code":aid,"period_net":net,"ytd_net":net,"period_debit":0,"period_credit":0,"ytd_debit":0,"ytd_credit":0})
        await db.account_mappings.insert_one({"_id":f"acm_{aid}","workspace_id":WS,"company_id":CA,"account_id":aid,"financial_concept_id":cid,"status":"confirmed","superseded":False,"effective_from_period_id":FP,"effective_from_sequence":1,"effective_to_period_id":None,"effective_to_sequence":None})
    print("SEED_OK")
    c.close()
asyncio.run(main())
