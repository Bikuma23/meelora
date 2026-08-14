# P1.10 — Phase 1 regression & validation

## Scope
P1.10 closes the Foundation phase without changing the financial calculation engines.
It adds a regression contract and validates P1.1–P1.9 together.

## Regression found and fixed
The P1.7 role simplification exposed a compatibility bug:
- new users are created with role `user`;
- several legacy screens still granted edit controls only to `admin|editor`;
- the global write guard also rejected `user` writes.

This would have made newly-created standard users read-only in existing operational modules.
P1.10 fixes the compatibility layer while preserving admin-only structural operations.

Changes:
- legacy DB role `editor` is normalized to public/auth role `user`;
- normal operational writes accept the unified standard `user` role;
- admin-only routes remain admin-only (`/users`, hypotheses, budget lock, years, Logs);
- existing frontend accounting/workforce edit gates now recognize `user`;
- legacy `editor` remains accepted only as a temporary compatibility value.

## Added regression contract
`backend/tests/test_phase1_regression_contract.py` validates:
- unified role compatibility;
- Foundation API routes remain present;
- legacy acct/qc9434 route surfaces remain present;
- legacy financial collections are not removed by Phase 1;
- Phase 1 migration scripts do not destructively touch acct/qc9434 collections;
- standard users retain existing operational edit capabilities;
- Logs navigation remains admin-only.

## Integration tests updated
The historical `test_admin_write_guard.py` and `test_role_matrix_editor.py` were updated to the new two-role product model. `editor` is now tested only as a legacy DB compatibility case and must be exposed by `/auth/me` as `user`.

## Local validation
- Phase 1 unit/regression suite: 44 passed.
- Backend `compileall`: passed.
- Updated integration role suites: 27 tests collected successfully.

## Environment-limited validation
The full legacy integration suite was not executed locally because it expects:
- a running deployed backend (`REACT_APP_BACKEND_URL`),
- the preview Mongo dataset and test credentials,
- `/app/frontend/.env`,
- pytest-xdist as configured by the repository,
- and frontend dependencies (`node_modules`) for a production React build.

These are deployment smoke checks, not local code failures.

## Financial-engine preservation
No P&L, balance sheet, cash-flow, BV parser, ledger calculation, invoice calculation, or qc9434 financial engine logic was changed in P1.10. `backend/server.py` changes are restricted to the role/write compatibility guard.

## Phase 1 exit status
The Foundation code is ready for deployment validation. Before Phase 2 data migration, run the deployed regression suite and manually verify one admin + two assigned standard users against the real migrated database.
