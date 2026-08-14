# Phase 1.6 — Logs

## Scope

- New tenant-aware `logs` collection and service.
- `/api/logs` is read-only and Admin-only, scoped to the authenticated workspace.
- Existing `log_action()` now dual-writes to `logs` and legacy `journal` during transition.
- `/api/journal` remains a deprecated compatibility endpoint.
- `migrate_phase1_logs.py` copies legacy rows into `logs` without deleting or changing `journal`.
- Foundation company/mandate events carry company/mandate/entity identifiers.
- Frontend admin navigation is renamed from **Journal** to **Logs** and calls `/api/logs`.
- No PUT/PATCH/DELETE endpoint exists for logs.

## Migration

Dry run:

```bash
python scripts/migrate_phase1_logs.py
```

Commit:

```bash
python scripts/migrate_phase1_logs.py --commit
```

If more than one workspace exists and legacy journal rows do not carry a workspace:

```bash
python scripts/migrate_phase1_logs.py --workspace-id ws_xxx --commit
```

The migration is idempotent through `metadata.legacy_journal_id` and never deletes the legacy collection.
