# Phase 1.3 — company_access & permission helpers

## Added

- `backend/core/company_access.py`: typed `CompanyAccess` domain model.
- `backend/core/permissions.py`: centralized workspace/company authorization helpers.
- `backend/scripts/migrate_phase1_company_access.py`: dry-run/`--commit` migration and index creation.
- Targeted tests for access model and permission behavior.

## Security decisions

- `company_access` is the authorization source for standard users.
- Admins may access all active companies **only inside their workspace**.
- Cross-workspace company lookups return 404 to avoid tenant enumeration.
- A standard user needs an active access assignment.
- The migration does **not** infer principal/collaborator ownership from legacy data.
- `--preserve-legacy-access` is explicit opt-in and seeds only `collaborator` rows, never principals.
- A partial unique Mongo index enforces at most one active principal per company.

## Cutover note

P1.3 introduces the schema/helpers but does not yet scope the legacy `/api/companies` route or the acct/qc9434 routes. That wiring is P1.4. Before P1.4 is enabled, standard-user assignments must exist (manually or via explicit legacy-preserve seeding), otherwise those users will correctly lose company visibility.
