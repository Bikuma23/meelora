#!/usr/bin/env python3
"""P1.6 migration: copy legacy journal rows to tenant-aware logs.

Dry-run by default. Use --commit to write. The legacy ``journal`` collection is
never modified or deleted by this script.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import re

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))


def slug(value: str) -> str:
    text = (value or "event").strip().lower()
    for src, dst in {"é":"e","è":"e","ê":"e","ë":"e","à":"a","â":"a","ä":"a","î":"i","ï":"i","ô":"o","ö":"o","ù":"u","û":"u","ü":"u","ç":"c"}.items():
        text = text.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "event"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--workspace-id", help="Workspace to assign to legacy journal rows when it cannot be inferred")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("MONGO_URL et DB_NAME sont requis")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        workspaces = await db.workspaces.find({"status": {"$ne": "inactive"}}).to_list(None)
        default_workspace = args.workspace_id
        if not default_workspace and len(workspaces) == 1:
            default_workspace = workspaces[0].get("_id")

        rows = await db.journal.find({}).to_list(None)
        existing_sources = set(await db.logs.distinct("metadata.legacy_journal_id"))
        existing_log_ids = set(await db.logs.distinct("_id"))
        planned = []
        skipped = 0
        for row in rows:
            legacy_id = str(row.get("_id"))
            dual_write_log_id = (row.get("metadata") or {}).get("p1_6_log_id")
            if legacy_id in existing_sources or (dual_write_log_id and dual_write_log_id in existing_log_ids):
                skipped += 1
                continue
            workspace_id = row.get("workspace_id") or default_workspace
            if not workspace_id:
                raise SystemExit(
                    "Impossible d'inférer workspace_id pour les anciens logs. "
                    "Relancer avec --workspace-id <id>."
                )
            action = row.get("action", "event")
            entity = row.get("entity", "event")
            planned.append({
                "workspace_id": workspace_id,
                "user_id": row.get("user_id"),
                "user_email": row.get("user_email", "système"),
                "user_name": row.get("user_name", ""),
                "company_id": row.get("company_id"),
                "mandate_id": row.get("mandate_id"),
                "event_type": f"{slug(entity)}.{slug(action)}",
                "entity_type": slug(entity),
                "entity_id": row.get("entity_id"),
                "severity": row.get("severity", "info"),
                "action": action,
                "entity": entity,
                "label": row.get("label", ""),
                "details": row.get("details", ""),
                "changes": row.get("changes") or [],
                "metadata": {**(row.get("metadata") or {}), "legacy_journal_id": legacy_id},
                "timestamp": row.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            })

        print(f"Mode: {'COMMIT' if args.commit else 'DRY-RUN'}")
        print(f"journal rows: {len(rows)}")
        print(f"already migrated: {skipped}")
        print(f"to migrate: {len(planned)}")
        print(f"workspace fallback: {default_workspace or 'none'}")
        if not args.commit:
            return

        if planned:
            await db.logs.insert_many(planned, ordered=False)
        await db.logs.create_index([("workspace_id", 1), ("timestamp", -1)], name="logs_workspace_timestamp")
        await db.logs.create_index([("workspace_id", 1), ("company_id", 1), ("timestamp", -1)], name="logs_workspace_company_timestamp")
        await db.logs.create_index([("workspace_id", 1), ("event_type", 1), ("timestamp", -1)], name="logs_workspace_event_timestamp")
        await db.logs.create_index("metadata.legacy_journal_id", unique=True, sparse=True, name="logs_legacy_journal_unique")
        print("Migration P1.6 terminée. La collection journal a été conservée intacte.")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
