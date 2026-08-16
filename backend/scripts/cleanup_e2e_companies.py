"""Remove disposable E2E company artifacts (names starting with 'ZZ ') and their
memberships/access. Idempotent; safe to run before/after the Playwright suite."""
import asyncio
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

PATTERN = re.compile(r"^ZZ ", re.IGNORECASE)


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    docs = await db.companies.find({"name": {"$regex": "^ZZ ", "$options": "i"}}).to_list(None)
    ids = [d.get("_id") or d.get("id") for d in docs]
    ids = [i for i in ids if i]
    if not ids:
        print("cleanup_e2e_companies: nothing to remove")
        return
    r = await db.companies.delete_many({"name": {"$regex": "^ZZ ", "$options": "i"}})
    for col in ("company_memberships", "company_access", "mandates"):
        await db[col].delete_many({"company_id": {"$in": ids}})
    print(f"cleanup_e2e_companies: removed {r.deleted_count} company(ies): {ids}")


if __name__ == "__main__":
    asyncio.run(main())
