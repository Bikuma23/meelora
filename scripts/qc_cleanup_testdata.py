import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    inv = await db.qc9434_invoices.find({"client_name": {"$regex": "^TEST", "$options": "i"}}).to_list(1000)
    bills = await db.qc9434_bills.find({"supplier": {"$regex": "^TEST", "$options": "i"}}).to_list(1000)
    ids = [str(d["_id"]) for d in inv] + [str(d["_id"]) for d in bills]
    entry_ids = [d.get("entry_id") for d in inv + bills if d.get("entry_id")]
    years = set()
    for d in inv + bills:
        years.add(d.get("year"))
    e1 = await db.qc9434_entries.delete_many({"_id": {"$in": entry_ids}})
    e2 = await db.qc9434_entries.delete_many({"source_id": {"$in": ids}})
    i = await db.qc9434_invoices.delete_many({"client_name": {"$regex": "^TEST", "$options": "i"}})
    b = await db.qc9434_bills.delete_many({"supplier": {"$regex": "^TEST", "$options": "i"}})
    c = await db.qc9434_external_contacts.delete_many({"name": {"$regex": "^TEST", "$options": "i"}})
    for y in years:
        if y is None:
            continue
        cnt = await db.qc9434_entries.count_documents({"year": int(y)})
        await db.qc9434_years.update_one({"_id": int(y)}, {"$set": {"entry_count": cnt}})
    print(f"entries removed: {e1.deleted_count + e2.deleted_count}, invoices: {i.deleted_count}, bills: {b.deleted_count}, contacts: {c.deleted_count}, years fixed: {years}")
    cli.close()

asyncio.run(main())
