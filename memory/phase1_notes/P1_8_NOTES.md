# P1.8 — Companies / Mandates frontend

Implemented on top of P1.7.

## Scope delivered

- New central `Companies` page driven by the authenticated workspace type.
  - Fiduciary workspace: UI labels the section `Mandats` and shows mandate assignment state.
  - Group/company workspace: UI labels it `Sociétés`.
- Standard users receive only the already-scoped `/api/companies` result and have no create/edit controls.
- Admins can create and edit companies through the P1.4 API.
- Fiduciary admins can create/update mandates and assign one principal plus multiple collaborators through the P1.5 API.
- Existing `company_access` remains the authorization source of truth because mandate writes sync access server-side.
- Search by company/code/responsible and jurisdiction filtering added.
- The bulk Excel button is intentionally visible but disabled and marked for P1.9.
- Foundation navigation added to the existing Layout without removing legacy Workforce/Accounting navigation.
- API client now exposes company CRUD and mandate CRUD methods.

## Intentionally unchanged

- Bulk Excel onboarding: P1.9.
- Legacy accounting/workforce routes and navigation.
- Financial engines, BV/ledger, reports, invoices and billing.
- Company-specific financial workspace routing; that belongs to Financial Core migration.

## Validation

- Python compile checks pass for backend/Foundation modules.
- Phase 1 focused backend suite: **34 passed** with `PYTHONPATH=backend` and a neutral pytest config.
- Frontend production build was not executed because the uploaded repository does not contain `node_modules`.
