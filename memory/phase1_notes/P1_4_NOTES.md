# P1.4 — Companies API + user scoping

## Added
- Tenant-aware `/api/companies` listing.
- `GET /api/companies/{company_id}` with centralized company authorization.
- Admin-only `POST /api/companies` and `PATCH /api/companies/{company_id}`.
- `backend/core/companies.py` application service and public serializer.
- Targeted P1.4 tests.

## Security behavior
- Admin: all active companies in their own workspace only.
- Standard user: active companies with an active `company_access` assignment only.
- Cross-workspace lookups return 404.
- Company creation/update always derives `workspace_id` from the authenticated admin; the client cannot select another tenant.

## Compatibility
`legacy_prefix` remains exposed temporarily because legacy acct/qc9434 navigation still depends on it. No financial collections or routes are migrated in P1.4.
