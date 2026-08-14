# P1.9 — Bulk Excel company onboarding

- Adds `POST /api/companies/import/preview` and `/commit` (Admin only).
- Preview parses XLSX in memory and performs no database writes.
- Commit refuses the whole import while any validation error remains, then creates companies using the existing tenant-aware company service.
- Fiduciary workspaces may include mandate code, principal email and collaborator emails; when complete these create mandates through the existing mandate service, which synchronizes `company_access`.
- Missing mandate assignment is a warning, so a company can still be onboarded and configured later.
- Duplicate company codes (database or same workbook), invalid jurisdiction/currency/type, and unknown assigned users are blocking errors.
- Frontend P1.8 Import Excel button now opens preview/validation/commit UI.
- No financial collections are changed.
