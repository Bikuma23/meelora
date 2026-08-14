# P1.7 — Users & Access frontend

Implemented on top of P1.6.

## Scope delivered

- Product roles simplified to `admin` and `user`.
  - Legacy `editor` rows remain readable and are surfaced as `user` until data migration is completed.
  - New/updated users can no longer select `editor`.
- `/api/users` is now workspace-scoped and includes `status` plus access counts.
- User creation writes `workspace_id`, `status`, `created_by` and tenant-aware logs.
- User update/deactivation is workspace-scoped.
- Legacy `DELETE /api/users/{id}` now performs a soft deactivation instead of a physical delete.
- New Admin-only access endpoints:
  - `GET /api/users/{id}/company-access`
  - `PUT /api/users/{id}/company-access`
- `company_access` remains the authorization source of truth.
- Principal reassignment preserves the former principal as a collaborator.
- A current principal cannot be removed/demoted from their own access dialog without first assigning a replacement.
- Existing fiduciary mandates are mirrored after access changes so mandate assignments remain synchronized.
- Users UI now shows:
  - Admin / User only
  - active/inactive status
  - number of assigned companies
  - company-access editor with `Aucun accès / Collaborateur / Responsable principal`
  - soft deactivate / reactivate controls
- Admin access is implicit to all companies and cannot be edited company by company.
- Legacy Layout role metadata now renders `editor` as `Utilisateur` during transition.

## Validation

- Python compile checks pass for the changed backend modules.
- Phase 1 focused test suite: **34 passed** using a neutral pytest config because the repository's configured `pytest-xdist` plugin is not installed in this execution environment.
- Frontend production build was not executed because the uploaded repository does not contain `node_modules` and this environment is not being used to install frontend dependencies.

## Intentionally unchanged

- Financial `acct_*` / `qc9434_*` routes and collections.
- Existing reporting/BV/ledger engines.
- P1.8 Companies/Mandates main navigation and page.
- Bulk Excel onboarding (P1.9).
