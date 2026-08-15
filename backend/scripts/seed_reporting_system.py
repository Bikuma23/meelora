"""P3.2 — Run the idempotent system reporting seed against the live DB.

System/background context (no HTTP, no user). Safe to run multiple times.
Usage: python scripts/seed_reporting_system.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from core.financial.system_seed import run_system_seed  # noqa: E402


def _env():
    env = {}
    for line in Path(__file__).resolve().parents[1].joinpath(".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


async def main():
    env = _env()
    client = AsyncIOMotorClient(env["MONGO_URL"])
    db = client[env["DB_NAME"]]
    report = await run_system_seed(db)
    print(json.dumps({"totals": report["totals"], "counts": report["counts"],
                      "errors": report["errors"]}, indent=2))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
