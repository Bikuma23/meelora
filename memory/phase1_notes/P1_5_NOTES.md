# Phase 1.5 — Mandates

P1.5 introduces the fiduciary-only `mandates` business layer while keeping
`company_access` as the authorization authority.

## Rules

- Mandates are available only when `workspace.organization_type == fiduciary`.
- One active mandate per company.
- One principal user, plus zero or more collaborators.
- Principal/collaborator users must be active members of the same workspace.
- Creating or changing a mandate synchronizes `company_access`.
- Deactivating a mandate revokes its active `company_access` assignments.
- Admins create/update mandates. Standard users may only list/read mandates for
  companies they can access.
- Cross-workspace reads are hidden.

## API

- `GET /api/mandates`
- `POST /api/mandates` (admin)
- `GET /api/mandates/{mandate_id}`
- `PATCH /api/mandates/{mandate_id}` (admin)

## Index preparation

From `backend/`:

```bash
python scripts/migrate_phase1_mandates.py
python scripts/migrate_phase1_mandates.py --commit
```

The migration never invents mandates from legacy data.
